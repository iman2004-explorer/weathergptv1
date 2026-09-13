"""
Loads the trained WeatherGPT Risk Index model and scores live forecast
data with it. This runs alongside (not instead of) the deterministic
advisory rules in weather_service.py — the ML score is an extra "AI risk
index" signal shown in the UI.
"""
import json
from pathlib import Path
import joblib
import numpy as np

MODELS_DIR = Path(__file__).parent.parent / "models"
_model = None
_meta = None


def _load():
    global _model, _meta
    if _model is None:
        _model = joblib.load(MODELS_DIR / "weather_risk_model.pkl")
        with open(MODELS_DIR / "model_meta.json") as f:
            _meta = json.load(f)
    return _model, _meta


def score_risk(month: int, latitude: float, day: dict, humidity: float) -> dict:
    """day: one entry from weather_service.fetch_forecast()['days']"""
    try:
        model, meta = _load()
    except Exception as exc:
        # The deterministic weather/advisory response must remain available
        # if a hosted runtime cannot load the optional model artifact.
        return {"available": False, "message": f"Risk model unavailable: {type(exc).__name__}"}

    features = np.array([[
        month,
        latitude,
        day["temp_max"],
        day["temp_min"],
        humidity,
        day["precip_prob"],
        day["wind_max"],
        day["uv_max"],
    ]])
    pred = model.predict(features)[0]
    proba = model.predict_proba(features)[0]
    label = meta["labels"][pred]
    return {
        "available": True,
        "level": label,
        "confidence": round(float(proba[pred]) * 100, 1),
        "trained_on": meta.get("trained_on"),
    }
