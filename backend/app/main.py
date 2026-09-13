import json
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import ALLOWED_ORIGINS, ANTHROPIC_API_KEY
from .geocode_service import resolve_location
from .weather_service import fetch_forecast, compute_advisories
from .crop_advisory import compute_crop_advisory
from .ml_model import score_risk
from .claude_service import call_claude
from . import local_nlu

app = FastAPI(title="WeatherGPT API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # no cookies/auth used; keeps "*" origin valid for local dev
    allow_methods=["*"],
    allow_headers=["*"],
)

# The deployed app serves the frontend and API from one origin. The static
# mount is added after the API routes, so it cannot intercept /api/* requests.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


# ---------------------------------------------------------------- schemas --
class GeocodeRequest(BaseModel):
    location: str
    state: Optional[str] = None
    district: Optional[str] = None


class WeatherRequest(BaseModel):
    location: str
    state: Optional[str] = None
    district: Optional[str] = None
    language: str = "en"


class ChatRequest(BaseModel):
    messages: list
    language: str = "en"


# --------------------------------------------------------------- helpers --
def localize_advisories(advisories: list, language: str) -> list:
    return [
        {"level": a["level"], "icon": a["icon"], "title": a[language]["title"], "text": a[language]["text"]}
        for a in advisories
    ]


def get_last_meta(messages: list) -> dict:
    for m in reversed(messages):
        if m.get("role") == "meta":
            try:
                return json.loads(m["content"])
            except Exception:
                return {}
    return {}


async def handle_local_chat(messages: list, language: str) -> dict:
    """Zero-setup fallback: rule-based intent classification + real live
    weather data, no external AI call needed. Used automatically whenever
    ANTHROPIC_API_KEY isn't configured (or a Claude call fails), so the app
    is always usable."""
    user_text = messages[-1]["content"]
    if not isinstance(user_text, str):
        # tolerate Claude-style content blocks if a prior turn used them
        user_text = next((b.get("text", "") for b in user_text if isinstance(b, dict)), "")

    prev_meta = get_last_meta(messages[:-1])
    pending = prev_meta.get("pending")
    last_location = prev_meta.get("last_location")

    weather_bundle = None
    disambiguation = None
    new_meta = {"last_location": last_location}
    resolution = None
    intent = None
    loc_text = None

    if pending:
        intent = pending.get("intent", "current")
        if pending["type"] == "need_state":
            resolution = await resolve_location(pending["query"], state=user_text)
        else:
            resolution = await resolve_location(pending["query"], state=pending.get("state"), district=user_text)
    else:
        intent = local_nlu.classify_intent(user_text)
        loc_text = local_nlu.extract_location(user_text)
        needs_location = not intent.startswith("climate:") and intent not in ("greeting", "thanks")
        if needs_location:
            if not loc_text and last_location:
                loc_text = last_location.get("query")
            if loc_text:
                resolution = await resolve_location(loc_text)

    if resolution is not None:
        if resolution.status == "resolved":
            weather_bundle = await build_weather_bundle(resolution.data["location"], language)
            new_meta["last_location"] = {"query": weather_bundle["place"]}
            reply_text = local_nlu.generate_reply(intent, weather_bundle, language)
        elif resolution.status == "not_found":
            reply_text = local_nlu.not_found_reply(pending["query"] if pending else (loc_text or user_text), language)
        else:  # need_state / need_district / need_choice
            d = resolution.to_dict()
            new_meta["pending"] = {
                "type": resolution.status,
                "query": d.get("query", loc_text),
                "state": d.get("state"),
                "intent": intent,
            }
            disambiguation = {
                "status": resolution.status,
                "query": d.get("query", loc_text),
                "state": d.get("state"),
                "options": d.get("options", []),
            }
            reply_text = d["message"]
    else:
        reply_text = local_nlu.generate_reply(intent, None, language)

    messages.append({"role": "assistant", "content": reply_text})
    messages.append({"role": "meta", "content": json.dumps(new_meta)})
    return {
        "messages": messages,
        "reply_text": reply_text,
        "weather_data": weather_bundle,
        "disambiguation": disambiguation,
        "engine": "local",
    }


async def build_weather_bundle(location_obj: dict, language: str) -> dict:
    forecast = await fetch_forecast(location_obj["latitude"], location_obj["longitude"])
    advisories = compute_advisories(forecast)
    crop = compute_crop_advisory(forecast, language)
    risk = score_risk(
        month=date.today().month,
        latitude=location_obj["latitude"],
        day=forecast["days"][0],
        humidity=forecast["current"]["humidity"],
    )
    return {
        "place": location_obj["display_name"],
        "state": location_obj.get("state"),
        "district": location_obj.get("district"),
        "current": forecast["current"],
        "days": forecast["days"],
        "advisories": localize_advisories(advisories, language),
        "crop_advisory": crop,
        "risk_index": risk,
    }


# ---------------------------------------------------------------- routes --
@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/geocode")
async def geocode(req: GeocodeRequest):
    """Direct location resolution endpoint — lets the frontend build its own
    state -> district picker UI outside of the chat flow (e.g. a plain
    search box)."""
    resolution = await resolve_location(req.location, req.state, req.district)
    return resolution.to_dict()


@app.post("/api/weather")
async def weather(req: WeatherRequest):
    """Resolve a location and return live weather + advisories + crop advice
    + ML risk index in one call. Returns a disambiguation payload instead if
    the place name is ambiguous."""
    resolution = await resolve_location(req.location, req.state, req.district)
    if resolution.status != "resolved":
        return resolution.to_dict()
    bundle = await build_weather_bundle(resolution.data["location"], req.language)
    return {"status": "resolved", **bundle}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Runs the Claude tool-calling loop server-side:
    1. Send conversation to Claude with the get_weather tool available.
    2. If Claude calls the tool, resolve the location (possibly asking for
       state/district back to the user via Claude's own reply), fetch the
       weather bundle, and feed the result back to Claude.
    3. Return the final assistant text plus the updated message history
       (the frontend just stores this array and sends it back next turn)
       plus any weather bundle fetched this turn, for the side panel.
    """
    messages = req.messages

    # Zero-setup mode: no key configured yet -> use the local rule-based
    # engine so the app is fully usable without any signup step.
    if not ANTHROPIC_API_KEY:
        return await handle_local_chat(messages, req.language)

    weather_bundle_for_ui = None
    disambiguation_for_ui = None

    for _ in range(3):  # a turn should resolve in 1-2 round trips; 3 is a safety cap
        try:
            data = await call_claude(messages, req.language)
        except RuntimeError:
            # Claude unreachable/misconfigured mid-session — fall back to the
            # local engine for this turn rather than showing an error.
            return await handle_local_chat(messages, req.language)

        content = data.get("content", [])
        tool_use = next((b for b in content if b.get("type") == "tool_use"), None)

        if not tool_use:
            messages.append({"role": "assistant", "content": content})
            text_block = next((b for b in content if b.get("type") == "text"), None)
            reply_text = text_block["text"] if text_block else ""
            return {
                "messages": messages,
                "reply_text": reply_text,
                "weather_data": weather_bundle_for_ui,
                "disambiguation": disambiguation_for_ui,
                "engine": "cloud",
            }

        messages.append({"role": "assistant", "content": content})

        location = tool_use["input"].get("location", "")
        state = tool_use["input"].get("state")
        district = tool_use["input"].get("district")
        resolution = await resolve_location(location, state, district)

        if resolution.status == "resolved":
            weather_bundle_for_ui = await build_weather_bundle(resolution.data["location"], req.language)
            disambiguation_for_ui = None
            tool_result_payload = {
                "status": "resolved",
                "place": weather_bundle_for_ui["place"],
                "current": weather_bundle_for_ui["current"],
                "next_7_days": weather_bundle_for_ui["days"],
                "advisories": weather_bundle_for_ui["advisories"],
                "crop_advisory": weather_bundle_for_ui["crop_advisory"],
                "risk_index": weather_bundle_for_ui["risk_index"],
            }
        else:
            tool_result_payload = resolution.to_dict()
            # Surface the raw options to the frontend too, so it can render
            # clickable state/district chips alongside Claude's own question
            # instead of forcing the user to type the answer.
            disambiguation_for_ui = {
                "status": resolution.status,
                "query": tool_result_payload.get("query", location),
                "state": tool_result_payload.get("state"),
                "options": tool_result_payload.get("options", []),
            }

        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use["id"],
                "content": json.dumps(tool_result_payload),
            }],
        })

    # Safety fallback if we somehow looped 3 times without a plain text reply
    return {
        "messages": messages,
        "reply_text": "Sorry, I had trouble finishing that — could you try rephrasing?",
        "weather_data": weather_bundle_for_ui,
        "disambiguation": disambiguation_for_ui,
        "engine": "cloud",
    }


# Keep this last: a root static mount would otherwise match API routes first.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
