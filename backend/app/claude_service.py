"""
All calls to the Anthropic API happen here, on the server, so the API key
never reaches the browser (the original prototype called api.anthropic.com
directly from client-side JS, which both leaks the key and gets blocked by
CORS in a real deployment).
"""
import httpx
from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

WEATHER_TOOL = {
    "name": "get_weather",
    "description": (
        "Get live current conditions and a 7-day forecast for a place. "
        "If the place name is ambiguous (multiple places in India/the world "
        "share that name), this tool returns status='need_state' or "
        "status='need_district' with a list of options instead of weather "
        "data — when that happens, ask the user to pick one in plain "
        "language, then call this tool again including the 'state' and/or "
        "'district' argument once you know it. Never guess a state or "
        "district on the user's behalf."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City, town, or village name, e.g. 'Springfield' or 'Kolkata'"},
            "state": {"type": "string", "description": "State/province, only if already known or the tool asked for it"},
            "district": {"type": "string", "description": "District, only if already known or the tool asked for it"},
        },
        "required": ["location"],
    },
}


def system_prompt(language: str = "en") -> str:
    lang_line = {
        "hi": "Respond in Hindi (Devanagari script).",
        "bn": "Respond in Bangla (Bengali script).",
    }.get(language, "Respond in English.")

    return f"""You are WeatherGPT, a multilingual conversational weather assistant for India's Ministry of Earth Sciences / India Meteorological Department.
Talk the way a good general-purpose assistant would: warm, natural, and willing to give a complete, well-organized answer rather than a clipped one-liner. Use short paragraphs, or a few bullet points when that genuinely makes an answer clearer, but never sound robotic or like a form response.

Answer weather, forecast, and climate questions helpfully, like a knowledgeable local weather presenter.
When the user asks about current conditions, a forecast, rain chance, or alerts for a specific place, ALWAYS call the get_weather tool rather than guessing — never invent numbers.

LOCATION DISAMBIGUATION: many places share the same name. If get_weather returns status='need_state', ask the user which state the place is in (list the given options) and wait for their answer before calling the tool again with the state filled in. If it returns status='need_district', do the same for district. If it returns status='need_choice', show the short list of exact matches (with their state/district) and ask the user to confirm which one. Never silently assume one option.

When the fetched data shows hazardous conditions (heavy rain, extreme heat, high wind, extreme cold, high UV), call these out plainly as advisories, state the severity (high or moderate) clearly, and give one or two short practical safety tips. If a "risk_index" field is present in the tool result, you may mention it as an additional AI-modeled risk signal, but the deterministic advisories are the primary source of truth.

Farmer advisory feature: if the user asks what crop to plant, how to care for a crop, or anything about farming/agriculture for a place, call get_weather for that place first, then use the crop_advisory data returned (season, tip, and crop list) to give concrete, short care instructions: sowing timing, irrigation, pest watch, and harvest timing. Keep it practical and specific enough for a smallholder farmer to act on.

For general climate or meteorology education questions that are not tied to one place's live data, answer directly from your own knowledge without calling the tool.
{lang_line}"""


async def call_claude(messages: list, language: str = "en") -> dict:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured on the server.")

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 900,
        "system": system_prompt(language),
        "tools": [WEATHER_TOOL],
        "messages": messages,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(ANTHROPIC_URL, headers=headers, json=body)
        if resp.status_code >= 400:
            raise RuntimeError(f"Anthropic API error {resp.status_code}: {resp.text[:300]}")
        return resp.json()
