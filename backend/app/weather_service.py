"""
Live weather retrieval (Open-Meteo) + deterministic hazard advisories.
Ported from the original prototype's client-side JS so the logic now lives
safely on the backend and is shared by both the chat tool and the plain
REST endpoint.
"""
import httpx
from .config import OPEN_METEO_FORECAST_URL

WEATHER_LABELS = {
    0: "Clear sky",
}


def weather_label(code: int) -> str:
    if code == 0:
        return "Clear sky"
    if code in (1, 2, 3):
        return "Partly cloudy"
    if code in (45, 48):
        return "Fog"
    if code in (51, 53, 55, 56, 57):
        return "Drizzle"
    if code in (61, 63, 65, 66, 67):
        return "Rain"
    if code in (71, 73, 75, 77):
        return "Snow"
    if code in (80, 81, 82):
        return "Rain showers"
    if code in (85, 86):
        return "Snow showers"
    if code in (95, 96, 99):
        return "Thunderstorm"
    return "Unsettled"


async def fetch_forecast(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,uv_index_max",
        "timezone": "auto",
        "forecast_days": 7,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(OPEN_METEO_FORECAST_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    daily = data["daily"]
    days = []
    for i, t in enumerate(daily["time"]):
        days.append({
            "date": t,
            "weather_code": daily["weather_code"][i],
            "weather_label": weather_label(daily["weather_code"][i]),
            "temp_max": round(daily["temperature_2m_max"][i]),
            "temp_min": round(daily["temperature_2m_min"][i]),
            "precip_prob": daily["precipitation_probability_max"][i],
            "wind_max": round(daily["wind_speed_10m_max"][i]),
            "uv_max": daily["uv_index_max"][i],
        })

    cur = data["current"]
    current = {
        "temp": round(cur["temperature_2m"]),
        "feels_like": round(cur["apparent_temperature"]),
        "humidity": cur["relative_humidity_2m"],
        "wind": round(cur["wind_speed_10m"]),
        "precip": cur["precipitation"],
        "weather_code": cur["weather_code"],
        "weather_label": weather_label(cur["weather_code"]),
    }

    return {"current": current, "days": days, "timezone": data.get("timezone")}


ADVISORY_TEXT = {
    "heavy_rain": {
        "level": "high", "icon": "🌧️",
        "en": {"title": "Heavy Rain Alert", "text": "Heavy rainfall is likely today — carry rain protection and allow extra travel time."},
        "hi": {"title": "भारी वर्षा चेतावनी", "text": "आज भारी बारिश की संभावना है — रेनकोट/छाता साथ रखें और यात्रा के लिए अतिरिक्त समय रखें।"},
        "bn": {"title": "ভারী বৃষ্টির সতর্কতা", "text": "আজ ভারী বৃষ্টির সম্ভাবনা — বৃষ্টি থেকে বাঁচার ব্যবস্থা রাখুন এবং যাতায়াতে বাড়তি সময় হাতে রাখুন।"},
    },
    "heat": {
        "level": "high", "icon": "🔥",
        "en": {"title": "Heat Advisory", "text": "Extreme heat is expected — stay hydrated and avoid prolonged sun exposure, especially at midday."},
        "hi": {"title": "गर्मी की चेतावनी", "text": "अत्यधिक गर्मी की संभावना है — पर्याप्त पानी पिएं और दोपहर में सीधी धूप से बचें।"},
        "bn": {"title": "তাপ সতর্কতা", "text": "তীব্র গরমের সম্ভাবনা — পর্যাপ্ত পানি পান করুন এবং দুপুরে সরাসরি রোদ এড়িয়ে চলুন।"},
    },
    "cold": {
        "level": "med", "icon": "❄️",
        "en": {"title": "Cold Advisory", "text": "A sharp overnight temperature drop is expected — keep warm clothing and coverings ready."},
        "hi": {"title": "ठंड की चेतावनी", "text": "रात में तापमान में तेज गिरावट की संभावना — गर्म कपड़े और ढकने का इंतज़ाम रखें।"},
        "bn": {"title": "ঠান্ডা সতর্কতা", "text": "রাতে তাপমাত্রা হঠাৎ কমে যাওয়ার সম্ভাবনা — গরম কাপড় ও ঢাকার ব্যবস্থা প্রস্তুত রাখুন।"},
    },
    "wind": {
        "level": "high", "icon": "💨",
        "en": {"title": "High Wind Advisory", "text": "Strong winds are expected — secure loose outdoor objects and avoid open, exposed areas."},
        "hi": {"title": "तेज़ हवा की चेतावनी", "text": "तेज़ हवाओं की संभावना — खुली जगह पर रखी वस्तुओं को सुरक्षित करें और खुले क्षेत्रों से बचें।"},
        "bn": {"title": "ঝড়ো হাওয়ার সতর্কতা", "text": "জোরালো হাওয়ার সম্ভাবনা — খোলা জায়গার জিনিসপত্র সুরক্ষিত করুন এবং খোলা এলাকা এড়িয়ে চলুন।"},
    },
    "uv": {
        "level": "med", "icon": "☀️",
        "en": {"title": "High UV Advisory", "text": "UV levels are high today — use sunscreen and cover up for extended time outdoors."},
        "hi": {"title": "यूवी चेतावनी", "text": "आज यूवी स्तर उच्च है — धूप में अधिक समय बिताने पर सनस्क्रीन लगाएं और शरीर ढकें।"},
        "bn": {"title": "ইউভি সতর্কতা", "text": "আজ ইউভি মাত্রা বেশি — বেশি সময় বাইরে থাকলে সানস্ক্রিন ব্যবহার করুন এবং শরীর ঢেকে রাখুন।"},
    },
}


def compute_advisories(weather_data: dict) -> list[dict]:
    days = weather_data.get("days") or []
    if not days:
        return []
    today = days[0]
    adv = []
    if today["precip_prob"] >= 70:
        adv.append(ADVISORY_TEXT["heavy_rain"])
    if today["temp_max"] >= 40:
        adv.append(ADVISORY_TEXT["heat"])
    if today["temp_min"] <= 4:
        adv.append(ADVISORY_TEXT["cold"])
    if today["wind_max"] >= 40:
        adv.append(ADVISORY_TEXT["wind"])
    if today["uv_max"] >= 8:
        adv.append(ADVISORY_TEXT["uv"])
    return adv
