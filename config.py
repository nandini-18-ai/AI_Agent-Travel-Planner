"""Central configuration for the AI Travel Planner.

Holds file paths, city coordinates (for the weather API), LLM provider
settings and a helper that reads secrets from the environment, a local
``.env`` file, or Streamlit's secrets store (used on Streamlit Cloud).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# Load variables from a local .env file (ignored if the file does not exist).
load_dotenv(BASE_DIR / ".env")

# --------------------------------------------------------------------------- #
# Cities supported by the datasets, with coordinates for Open-Meteo.
# --------------------------------------------------------------------------- #
CITY_COORDS: dict[str, tuple[float, float]] = {
    "Delhi": (28.6139, 77.2090),
    "Mumbai": (19.0760, 72.8777),
    "Goa": (15.2993, 74.1240),
    "Bangalore": (12.9716, 77.5946),
    "Chennai": (13.0827, 80.2707),
    "Hyderabad": (17.3850, 78.4867),
    "Kolkata": (22.5726, 88.3639),
    "Jaipur": (26.9124, 75.7873),
}

# --------------------------------------------------------------------------- #
# Weather API (Open-Meteo, no key required)
# --------------------------------------------------------------------------- #
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_WINDOW_DAYS = 15  # Open-Meteo forecasts reach ~16 days ahead.

# --------------------------------------------------------------------------- #
# LLM providers. Model names can be overridden with environment variables if
# a provider retires a model.
# --------------------------------------------------------------------------- #
LLM_PROVIDERS: dict[str, dict[str, str]] = {
    "Google Gemini": {
        "id": "gemini",
        "env_key": "GOOGLE_API_KEY",
        "default_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "key_url": "https://aistudio.google.com/apikey",
    },
    "Groq": {
        "id": "groq",
        "env_key": "GROQ_API_KEY",
        "default_model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        "key_url": "https://console.groq.com/keys",
    },
    "OpenAI": {
        "id": "openai",
        "env_key": "OPENAI_API_KEY",
        "default_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "key_url": "https://platform.openai.com/api-keys",
    },
}

# Trip rules from the project brief.
MIN_TRIP_DAYS = 3
MAX_TRIP_DAYS = 7
DEFAULT_DAILY_EXPENSE = 1500  # INR per person per day (food + local travel)


def get_secret(name: str, default: str | None = None) -> str | None:
    """Return a secret from env vars, ``.env`` or ``st.secrets`` (in that order)."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:  # no secrets file / streamlit not running
        return default
