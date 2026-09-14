"""Location-aware activity and hydration guidance derived from live weather."""


def _location_context(location: dict | None) -> dict:
    location = location or {}
    return {
        "place": location.get("display_name"),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "state": location.get("state"),
        "district": location.get("district"),
    }


def _weather_flags(forecast: dict, aqi: dict | None) -> dict:
    current = forecast.get("current", {})
    today = (forecast.get("days") or [{}])[0]
    code = current.get("weather_code", today.get("weather_code"))
    return {
        "temp": float(current.get("feels_like", current.get("temp", 25))),
        "humidity": float(current.get("humidity", 60)),
        "wind": float(current.get("wind", today.get("wind_max", 0))),
        "rain_probability": float(today.get("precip_prob", 0)),
        "uv": float(today.get("uv_max", 0)),
        "weather_code": code,
        "storm": code in (95, 96, 99),
        "fog": code in (45, 48),
        "snow": code in (71, 73, 75, 77, 85, 86),
        "aqi": float(aqi.get("value", 0)) if aqi else None,
    }


def compute_activity_advice(forecast: dict, aqi: dict | None, location: dict | None = None) -> dict:
    """Return conservative activity suitability for the resolved location.

    Thresholds are public-health style screening rules, not a fitness or
    emergency assessment. AQI is treated as an additional location-specific
    exposure signal when available.
    """
    w = _weather_flags(forecast, aqi)
    unsafe_weather = w["storm"] or w["snow"] or w["fog"]
    air = w["aqi"]
    air_ok = air is None or air <= 100
    air_moderate = air is None or air <= 200
    rain_ok = w["rain_probability"] < 40
    activities = [
        {
            "id": "walking", "name": "Walking", "icon": "🚶",
            "suitable": not unsafe_weather and w["temp"] <= 35 and w["temp"] >= 5 and rain_ok and air_moderate,
            "reason": "Comfortable for a walk; use shade and water if it feels warm." if not unsafe_weather and w["temp"] <= 35 and w["temp"] >= 5 and rain_ok and air_moderate else "Prefer a shorter route or indoors because of weather or air quality.",
        },
        {
            "id": "running", "name": "Running", "icon": "🏃",
            "suitable": not unsafe_weather and 8 <= w["temp"] <= 30 and w["rain_probability"] < 30 and w["wind"] < 30 and air_ok,
            "reason": "Good conditions for an easy run; warm up and carry water." if not unsafe_weather and 8 <= w["temp"] <= 30 and w["rain_probability"] < 30 and w["wind"] < 30 and air_ok else "Reduce intensity or move indoors; heat, rain, wind, or air quality raises strain.",
        },
        {
            "id": "cycling", "name": "Cycling", "icon": "🚴",
            "suitable": not unsafe_weather and w["temp"] <= 32 and w["temp"] >= 8 and w["rain_probability"] < 35 and w["wind"] < 30 and air_ok,
            "reason": "Suitable for cycling with sun and rain protection." if not unsafe_weather and w["temp"] <= 32 and w["temp"] >= 8 and w["rain_probability"] < 35 and w["wind"] < 30 and air_ok else "Avoid exposed roads today; rain, wind, heat, or pollution can make cycling risky.",
        },
        {
            "id": "light_exercise", "name": "Light exercise", "icon": "🧘",
            "suitable": not w["storm"] and not w["snow"] and w["temp"] <= 35 and air_moderate,
            "reason": "Light exercise such as stretching or an easy session is reasonable." if not w["storm"] and not w["snow"] and w["temp"] <= 35 and air_moderate else "Choose an indoor, low-effort session and stop if you feel unwell.",
        },
        {
            "id": "travelling", "name": "Travelling", "icon": "🧳",
            "suitable": not w["storm"] and not w["fog"] and w["rain_probability"] < 60 and w["wind"] < 40,
            "reason": "Travel conditions look broadly manageable; allow normal weather-related margin." if not w["storm"] and not w["fog"] and w["rain_probability"] < 60 and w["wind"] < 40 else "Delay non-essential travel or allow extra time for reduced visibility, rain, or wind.",
        },
        {
            "id": "heavy_exercise", "name": "Heavy exercise", "icon": "🏋️",
            "suitable": not unsafe_weather and 10 <= w["temp"] <= 28 and w["rain_probability"] < 20 and w["wind"] < 20 and air_ok,
            "reason": "Conditions are relatively favorable for a hard session; hydrate and take breaks." if not unsafe_weather and 10 <= w["temp"] <= 28 and w["rain_probability"] < 20 and w["wind"] < 20 and air_ok else "Skip hard outdoor training; use a cooler, cleaner indoor setting or rest.",
        },
        {
            "id": "photography", "name": "Photography", "icon": "📷",
            "suitable": not w["storm"] and not w["fog"] and w["rain_probability"] < 40 and w["wind"] < 35 and air_moderate,
            "reason": "Good visibility for an outdoor photo walk; protect equipment from any showers." if not w["storm"] and not w["fog"] and w["rain_probability"] < 40 and w["wind"] < 35 and air_moderate else "Visibility or equipment exposure may be poor; consider an indoor or sheltered shoot.",
        },
    ]
    return {
        "location_analysis": _location_context(location),
        "conditions": {
            "feels_like": round(w["temp"], 1),
            "humidity": round(w["humidity"]),
            "wind_kmh": round(w["wind"]),
            "rain_probability": round(w["rain_probability"]),
            "uv_index": round(w["uv"], 1),
            "aqi": round(w["aqi"]) if w["aqi"] is not None else None,
        },
        "activities": activities,
        "standard": "Location-resolved weather and air-quality screening",
    }


def compute_hydration_advice(forecast: dict, aqi: dict | None, location: dict | None = None) -> dict:
    """Estimate adult daily beverage needs with explicit guideline inputs.

    The estimate starts with National Academies adequate-intake references for
    total water and applies a conservative weather/exercise adjustment. It is
    not a patient-specific prescription.
    """
    w = _weather_flags(forecast, aqi)
    weather_extra = 0.0
    if w["temp"] >= 33:
        weather_extra += 0.6
    elif w["temp"] >= 27:
        weather_extra += 0.3
    if w["humidity"] >= 80:
        weather_extra += 0.2
    if w["wind"] >= 30:
        weather_extra += 0.2
    exercise_extra = 0.4 if any(activity["suitable"] for activity in compute_activity_advice(forecast, aqi, location)["activities"] if activity["id"] in {"running", "cycling", "heavy_exercise"}) else 0.0
    total_extra = round(weather_extra + exercise_extra, 1)
    low = round(2.2 + total_extra, 1)
    high = round(3.0 + total_extra, 1)
    return {
        "location_analysis": _location_context(location),
        "daily_beverage_target_litres": {"low": low, "high": high},
        "weather_adjustment_litres": round(weather_extra, 1),
        "exercise_adjustment_litres_per_hour": "0.4-0.8",
        "guidance": [
            f"A practical adult beverage starting range here is {low}-{high} L today; drink steadily rather than waiting for intense thirst.",
            "For exercise lasting over an hour, use about 0.4-0.8 L per hour, adjusted for sweat rate; small frequent sips are easier to tolerate.",
            "Do not force fluids quickly. Avoid exceeding about 1 L per hour, and consider electrolytes for prolonged, very sweaty exercise.",
        ],
        "standard": "National Academies water adequate intake + ACSM exercise hydration guidance",
        "disclaimer": "General adult guidance, not a medical prescription. People with kidney, heart, liver, endocrine conditions, fluid restrictions, pregnancy, or medicines affecting fluid balance should ask a clinician for a personal target.",
    }
