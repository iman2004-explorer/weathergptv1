import json
import logging
import math
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import ALLOWED_ORIGINS, ANTHROPIC_API_KEY
from .geocode_service import resolve_location
from .weather_service import fetch_aqi, fetch_forecast, fetch_wttr_forecast, compute_advisories
from .crop_advisory import compute_crop_advisory
from .ml_model import score_risk
from .claude_service import call_claude
from . import local_nlu

logger = logging.getLogger(__name__)

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


def compute_health_advice(forecast: dict, aqi: dict | None, language: str) -> dict:
    current = forecast["current"]
    today = forecast["days"][0]
    concerns = []
    tips = []
    if current["temp"] >= 38 or today["temp_max"] >= 40:
        concerns.append("Possible heat-related symptoms: heavy sweating, headache, dizziness, weakness, cramps, or dehydration.")
        tips.append("Drink water regularly, limit midday exertion, and take breaks in shade or indoors. Seek urgent help for confusion, fainting, or very hot dry skin.")
    if current["temp"] <= 8 or today["temp_min"] <= 5:
        concerns.append("Cold exposure may contribute to shivering, worsening joint discomfort, cough, or breathing difficulty in vulnerable people.")
        tips.append("Keep warm, especially overnight, and check on older adults, infants, and people with chronic illness.")
    if today["uv_max"] >= 8:
        concerns.append("High UV exposure can cause sunburn, eye irritation, and skin damage.")
        tips.append("Use shade, protective clothing, sunglasses, and sunscreen when outdoors.")
    if today["wind_max"] >= 40:
        concerns.append("Strong winds can increase dust exposure, causing sneezing, cough, throat irritation, or breathing discomfort.")
        tips.append("Avoid dusty outdoor areas, close windows during dust, and keep prescribed respiratory medicine available.")
    if today["precip_prob"] >= 70 or current["humidity"] >= 85:
        concerns.append("Rainy and humid conditions may increase cough, sneezing, throat irritation, mould exposure, and seasonal viral illness risk.")
        tips.append("Keep rooms ventilated and dry, avoid prolonged damp clothing, wash hands regularly, and avoid close contact when fever or respiratory symptoms appear.")
    if aqi and aqi.get("value", 0) > 100:
        concerns.append(f"Air pollution is elevated (AQI {aqi['value']}, {aqi['category']}): cough, sneezing, throat irritation, wheezing, or breathing discomfort may worsen.")
        tips.append("Reduce prolonged outdoor exertion, avoid heavy-traffic areas, keep indoor air clean, and use a well-fitted mask if needed.")
    if aqi and aqi.get("value", 0) > 200:
        concerns.append("Very poor air may aggravate asthma, COPD, heart disease, and other breathing or cardiovascular conditions.")
        tips.append("Prefer indoor activity, keep windows closed during pollution peaks, and follow your clinician's action plan.")
    if not concerns:
        concerns.append("No major weather-related health stress signal is detected right now.")
        tips.append("Stay hydrated, sleep well, eat regularly, and use normal sun and weather protection outdoors.")
    return {
        "concerns": concerns,
        "tips": tips,
        "disclaimer": "These are weather-related risk signals, not a diagnosis. Weather cannot confirm the cause of cough, sneezing, sore throat, choking, fever, or breathing problems. Seek medical care for persistent fever, chest pain, choking, blue lips, confusion, or difficulty breathing.",
        "standard": "Weather and AQI-based public-health guidance",
    }


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
        if needs_location and len(messages) >= 3:
            previous_assistant = next(
                (m.get("content", "") for m in reversed(messages[:-1]) if m.get("role") == "assistant"),
                "",
            )
            previous_user = next(
                (m.get("content", "") for m in reversed(messages[:-1]) if m.get("role") == "user"),
                "",
            )
            is_confirmation = (
                isinstance(previous_assistant, str)
                and ("which state" in previous_assistant.lower() or "which district" in previous_assistant.lower())
                and isinstance(user_text, str)
                and len(user_text.split()) <= 5
                and not any(word in user_text.lower().split() for word in [
                    "weather", "forecast", "rain", "temperature", "climate", "in", "for", "what", "how", "will"
                ])
            )
            original_location = local_nlu.extract_location(previous_user) if isinstance(previous_user, str) else None
            if is_confirmation and original_location:
                resolution = await resolve_location(original_location, state=user_text)
                intent = "current"
                loc_text = original_location
        if needs_location:
            if resolution is not None:
                pass
            elif not loc_text and last_location:
                loc_text = last_location.get("query")
            if resolution is None and loc_text:
                resolution = await resolve_location(loc_text)

    if resolution is not None:
        if resolution.status == "resolved":
            weather_bundle = await build_weather_bundle(resolution.data["location"], language)
            if pending and pending.get("query"):
                location_obj = resolution.data["location"]
                weather_bundle["place"] = ", ".join(
                    value for value in [
                        pending["query"].title(),
                        location_obj.get("district"),
                        location_obj.get("state"),
                        location_obj.get("country"),
                    ] if value
                )
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
    try:
        forecast = await fetch_forecast(location_obj["latitude"], location_obj["longitude"])
        source = "live · Open-Meteo"
    except Exception:
        logger.exception("Open-Meteo failed for %s; trying wttr.in", location_obj.get("display_name"))
        forecast = await fetch_wttr_forecast(
            location_obj.get("display_name") or "India",
            latitude=location_obj.get("latitude"),
            longitude=location_obj.get("longitude"),
        )
        source = "live · wttr.in fallback"
    advisories = compute_advisories(forecast)
    try:
        aqi = await fetch_aqi(location_obj["latitude"], location_obj["longitude"])
    except Exception:
        logger.exception("AQI lookup failed for %s", location_obj.get("display_name"))
        aqi = None
    health_advice = compute_health_advice(forecast, aqi, language)
    crop = compute_crop_advisory(forecast, language)
    risk = score_risk(
        month=date.today().month,
        latitude=location_obj["latitude"],
        day=forecast["days"][0],
        humidity=forecast["current"]["humidity"],
    )
    return {
        "place": location_obj["display_name"],
        "data_source": source,
        "state": location_obj.get("state"),
        "district": location_obj.get("district"),
        "current": forecast["current"],
        "days": forecast["days"],
        "advisories": localize_advisories(advisories, language),
        "crop_advisory": crop,
        "risk_index": risk,
        "aqi": aqi,
        "health_advice": health_advice,
    }


def fallback_location(query: str) -> dict:
    known = {
        "kolkata": (22.57, 88.36, "Kolkata, West Bengal, India"),
        "durgapur": (23.52, 87.31, "Durgapur, West Bengal, India"),
        "durgapur west bengal": (23.52, 87.31, "Durgapur, West Bengal, India"),
        "mumbai": (19.08, 72.88, "Mumbai, Maharashtra, India"),
        "delhi": (28.61, 77.21, "Delhi, India"),
        "new delhi": (28.61, 77.21, "New Delhi, India"),
        "chennai": (13.08, 80.27, "Chennai, Tamil Nadu, India"),
        "bengaluru": (12.97, 77.59, "Bengaluru, Karnataka, India"),
        "bangalore": (12.97, 77.59, "Bengaluru, Karnataka, India"),
        "hyderabad": (17.39, 78.49, "Hyderabad, Telangana, India"),
        "pune": (18.52, 73.86, "Pune, Maharashtra, India"),
        "singapore": (1.35, 103.82, "Singapore"),
        "london": (51.51, -0.13, "London, United Kingdom"),
        "dubai": (25.20, 55.27, "Dubai, United Arab Emirates"),
    }
    key = (query or "").strip().lower()
    lat, lon, display_name = known.get(key, (20.59, 78.96, (query or "India").title()))
    return {"latitude": lat, "longitude": lon, "display_name": display_name, "state": None, "district": None}


def fallback_weather_bundle(location_obj: dict, language: str) -> dict:
    today = date.today()
    seasonal = 28 + 5 * math.sin((today.month - 3) * math.pi / 6) - abs(location_obj["latitude"]) * 0.03
    days = []
    for offset in range(7):
        high = round(seasonal + 2 + math.sin(offset * 0.8))
        low = round(seasonal - 5 + math.sin(offset * 0.8))
        days.append({
            "date": today.isoformat() if offset == 0 else (today.fromordinal(today.toordinal() + offset)).isoformat(),
            "weather_code": 2,
            "weather_label": "Partly cloudy",
            "temp_max": high,
            "temp_min": low,
            "precip_prob": 35,
            "wind_max": 12,
            "uv_max": 7,
        })
    forecast = {
        "current": {
            "temp": days[0]["temp_max"] - 3,
            "feels_like": days[0]["temp_max"] - 1,
            "humidity": 65,
            "wind": 8,
            "precip": 0,
            "weather_code": 2,
            "weather_label": "Partly cloudy",
        },
        "days": days,
    }
    advisories = compute_advisories(forecast)
    return {
        "place": location_obj["display_name"],
        "state": location_obj.get("state"),
        "district": location_obj.get("district"),
        "current": forecast["current"],
        "days": days,
        "advisories": localize_advisories(advisories, language),
        "crop_advisory": compute_crop_advisory(forecast, language),
        "risk_index": {"available": False, "message": "Using location-based fallback analysis while live data reconnects."},
        "aqi": None,
        "health_advice": compute_health_advice(forecast, None, language),
        "data_source": "fallback analysis",
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
    try:
        resolution = await resolve_location(req.location, req.state, req.district)
    except Exception:
        logger.exception("Weather lookup failed for %s", req.location)
        return {"status": "resolved", **fallback_weather_bundle(fallback_location(req.location), req.language)}
    if resolution.status != "resolved":
        return resolution.to_dict()
    try:
        bundle = await build_weather_bundle(resolution.data["location"], req.language)
    except Exception:
        logger.exception("Forecast build failed for %s", req.location)
        return {"status": "resolved", **fallback_weather_bundle(resolution.data["location"], req.language)}
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
        try:
            return await handle_local_chat(messages, req.language)
        except Exception:
            logger.exception("Local chat failed")
            query = local_nlu.extract_location(messages[-1].get("content", "")) or "India"
            fallback = fallback_weather_bundle(fallback_location(query), req.language)
            reply_text = local_nlu.generate_reply(local_nlu.classify_intent(messages[-1].get("content", "")), fallback, req.language)
            messages.append({"role": "assistant", "content": reply_text})
            return {
                "messages": messages,
                "reply_text": reply_text,
                "weather_data": fallback,
                "disambiguation": None,
                "engine": "local",
            }

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
