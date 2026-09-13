"""
Central configuration for the WeatherGPT backend.
Reads secrets/settings from environment variables (.env file).
"""
import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
PORT = int(os.getenv("PORT", "8000"))
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
NOMINATIM_GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

if not ANTHROPIC_API_KEY:
    # The application remains usable through its local rule-based chat mode.
    print("[config] ANTHROPIC_API_KEY is not set; /api/chat will use the local fallback engine.")
