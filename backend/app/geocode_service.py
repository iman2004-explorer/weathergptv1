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
import unicodedata
from typing import Optional
import httpx
from .config import NOMINATIM_GEOCODE_URL, OPEN_METEO_GEOCODE_URL

WB_ALIASES = {
    "burdwan": "Purba Bardhaman, West Bengal",
    "east burdwan": "Purba Bardhaman, West Bengal",
    "west burdwan": "Paschim Bardhaman, West Bengal",
    "bengal": "West Bengal",
    "24 parganas": "West Bengal",
    "north 24 parganas": "North 24 Parganas, West Bengal",
    "south 24 parganas": "South 24 Parganas, West Bengal",
    "midnapore": "Paschim Medinipur, West Bengal",
    "west midnapore": "Paschim Medinipur, West Bengal",
    "east midnapore": "Purba Medinipur, West Bengal",
    "midnapur": "Paschim Medinipur, West Bengal",
}

WB_DISTRICTS = {
    "alipurduar", "bankura", "birbhum", "cooch behar", "coochbehar", "dakshin dinajpur",
    "darjeeling", "hooghly", "howrah", "jalpaiguri", "jhargram", "kalimpong", "kolkata",
    "maldah", "malda", "murshidabad", "nadia", "north 24 parganas", "south 24 parganas",
    "paschim bardhaman", "purba bardhaman", "bardhaman", "burdwan", "paschim medinipur",
    "purba medinipur", "medinipur", "purulia", "siliguri", "uttar dinajpur",
}


def _region_query(query: str) -> str:
    lowered = query.strip().lower()
    for alias, region in WB_ALIASES.items():
        if alias in lowered:
            return f"{query}, {region}"
    return query


def _fold(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(char)
    ).lower().strip()


async def _nominatim_search(query: str, count: int = 20) -> list[dict]:
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


def _display_with_original_query(candidate: dict, query: str) -> dict:
    original = query.strip()
    if not original:
        return candidate
    candidate = {**candidate}
    parts = [original.title()]
    for value in [candidate.get("district"), candidate.get("state"), candidate.get("country")]:
        if value and value not in parts:
            parts.append(value)
    candidate["display_name"] = ", ".join(parts)
    return candidate


async def _raw_search(query: str, count: int = 20) -> list[dict]:
    search_query = _region_query(query)
    params = {"name": search_query, "count": count, "language": "en", "format": "json"}
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
                    "q": f"{search_query}, India",
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
    # Village names often have weak or missing Open-Meteo matches. A second
    # region-aware OSM search gives the whole of West Bengal, including small
    # settlements, a real coordinate without a hard-coded village database.
    if not results:
        results = await _nominatim_search(_region_query(query), count=20)
    if not results:
        return LocationResolution("not_found", message=f'No place found matching "{query}".')

    candidates = [_candidate(r) for r in results]

    # Geocoders can return duplicate records for the same visible place
    # (Darjeeling is commonly returned twice with nearly identical points).
    # Keep the most useful record instead of asking the user to choose between
    # indistinguishable options.
    unique_candidates = {}
    for candidate in candidates:
        key = (
            (candidate.get("name") or "").strip().lower(),
            (candidate.get("district") or "").strip().lower(),
            (candidate.get("state") or "").strip().lower(),
            (candidate.get("country") or "").strip().lower(),
        )
        previous = unique_candidates.get(key)
        if previous is None or (candidate.get("population") or 0) > (previous.get("population") or 0):
            unique_candidates[key] = candidate
    candidates = list(unique_candidates.values())

    # Keep only candidates whose name actually matches what the user typed
    # (Open-Meteo sometimes returns loosely related results).
    q_lower = _fold(query)
    preferred_candidates = candidates
    if q_lower in WB_DISTRICTS:
        preferred_candidates = [c for c in candidates if c["state"] and "west bengal" in c["state"].lower()] or candidates
    exact_name_matches = [c for c in preferred_candidates if c["name"] and _fold(c["name"]) == q_lower]
    pool = exact_name_matches if exact_name_matches else preferred_candidates

    if state:
        state_lower = state.lower()
        pool = [c for c in pool if c["state"] and state_lower in c["state"].lower()] or pool
    elif _fold(query) in WB_DISTRICTS:
        west_bengal_pool = [c for c in pool if c["state"] and "west bengal" in c["state"].lower()]
        if west_bengal_pool:
            pool = west_bengal_pool

    if _fold(query) in WB_DISTRICTS and len(pool) > 1:
        pool = [max(pool, key=lambda c: (c.get("population") or 0, bool(c.get("district"))))]

    if district:
        district_lower = district.lower()
        pool = [c for c in pool if c["district"] and district_lower in c["district"].lower()] or pool

    if len(pool) == 1:
        return LocationResolution("resolved", location=_display_with_original_query(pool[0], query))

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
