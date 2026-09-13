"""
Location resolution with disambiguation.

Problem this solves: India (and the world) has many places that share the
same name (e.g. there are multiple "Hodal"s, multiple "Bilaspur"s, multiple
"Gurgaon" spellings, several villages called "Rampur" etc). If we blindly
take the first geocoding result, WeatherGPT can silently give the weather
for the wrong place.

Strategy:
1. Query Open-Meteo's geocoding API for the raw place name (broad match).
2. If there's exactly one match -> resolved immediately.
3. If there are multiple matches:
      a. If the caller hasn't told us the STATE yet, and the candidates
         span more than one state (admin1), we ask for the state.
      b. Once a state is chosen (or all candidates already share one state)
         but there are still multiple candidates, we ask for the DISTRICT
         (admin2).
      c. Once state + district narrows it to one, we resolve.
4. If, after state + district, more than one candidate remains (rare —
   e.g. same name twice in one district), we just return the full list of
   remaining candidates so the frontend can let the user pick the exact one.
"""
import asyncio
from typing import Optional
import httpx
from .config import NOMINATIM_GEOCODE_URL, OPEN_METEO_GEOCODE_URL


class LocationResolution:
    def __init__(self, status: str, **kwargs):
        self.status = status  # "resolved" | "need_state" | "need_district" | "need_choice" | "not_found"
        self.data = kwargs

    def to_dict(self):
        return {"status": self.status, **self.data}


def _candidate(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "state": r.get("admin1"),
        "district": r.get("admin2"),
        "country": r.get("country"),
        "country_code": r.get("country_code"),
        "latitude": r.get("latitude"),
        "longitude": r.get("longitude"),
        "population": r.get("population"),
        "display_name": ", ".join(
            [p for p in [r.get("name"), r.get("admin2"), r.get("admin1"), r.get("country")] if p]
        ),
    }


async def _raw_search(query: str, count: int = 20) -> list[dict]:
    params = {"name": query, "count": count, "language": "en", "format": "json"}
    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
                resp = await client.get(OPEN_METEO_GEOCODE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                return data.get("results") or []
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < 2:
                await asyncio.sleep(1)
    try:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            resp = await client.get(
                NOMINATIM_GEOCODE_URL,
                params={
                    "q": f"{query}, India",
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "limit": count,
                },
                headers={"User-Agent": "WeatherGPT/1.0 weather education project"},
            )
            resp.raise_for_status()
            results = []
            for item in resp.json():
                address = item.get("address", {})
                results.append({
                    "id": item.get("osm_id"),
                    "name": address.get("city") or address.get("town") or address.get("village") or item.get("name") or query,
                    "admin1": address.get("state"),
                    "admin2": address.get("state_district") or address.get("county"),
                    "country": address.get("country", "India"),
                    "country_code": address.get("country_code", "in"),
                    "latitude": float(item["lat"]),
                    "longitude": float(item["lon"]),
                    "population": 0,
                })
            return results
    except httpx.HTTPError:
        if last_error:
            raise last_error
        raise


async def resolve_location(
    query: str,
    state: Optional[str] = None,
    district: Optional[str] = None,
) -> LocationResolution:
    query = (query or "").strip()
    if not query:
        return LocationResolution("not_found", message="No location text provided.")

    results = await _raw_search(query)
    if not results:
        return LocationResolution("not_found", message=f'No place found matching "{query}".')

    candidates = [_candidate(r) for r in results]

    # Keep only candidates whose name actually matches what the user typed
    # (Open-Meteo sometimes returns loosely related results).
    q_lower = query.lower()
    exact_name_matches = [c for c in candidates if c["name"] and c["name"].lower() == q_lower]
    pool = exact_name_matches if exact_name_matches else candidates

    if state:
        state_lower = state.lower()
        pool = [c for c in pool if c["state"] and state_lower in c["state"].lower()] or pool

    if district:
        district_lower = district.lower()
        pool = [c for c in pool if c["district"] and district_lower in c["district"].lower()] or pool

    if len(pool) == 1:
        return LocationResolution("resolved", location=pool[0])

    if len(pool) == 0:
        return LocationResolution("not_found", message=f'No place found matching "{query}" with the given state/district.')

    # More than one candidate remains.
    distinct_states = sorted({c["state"] for c in pool if c["state"]})
    if not state and len(distinct_states) > 1:
        return LocationResolution(
            "need_state",
            message=f'There are multiple places named "{query}". Which state is it in?',
            options=distinct_states,
            query=query,
        )

    distinct_districts = sorted({c["district"] for c in pool if c["district"]})
    if not district and len(distinct_districts) > 1:
        return LocationResolution(
            "need_district",
            message=f'There are multiple places named "{query}" in that state. Which district?',
            options=distinct_districts,
            query=query,
            state=state,
        )

    # Still ambiguous even after state + district (e.g. two villages, same
    # name, same district) — let the caller pick from the short remaining list.
    return LocationResolution(
        "need_choice",
        message=f'Please pick the exact "{query}" you mean.',
        options=pool[:10],
        query=query,
    )
