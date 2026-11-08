"""Loads the flights, hotels and places datasets from ``data/``."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from config import DATA_DIR


@lru_cache(maxsize=None)
def _load_json(filename: str) -> list[dict[str, Any]]:
    """Read a JSON file from the data folder (cached after the first read)."""
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Missing dataset: {path}. Copy flights.json, hotels.json and "
            f"places.json into the 'data' folder."
        )
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def load_flights() -> list[dict[str, Any]]:
    return _load_json("flights.json")


def load_hotels() -> list[dict[str, Any]]:
    return _load_json("hotels.json")


def load_places() -> list[dict[str, Any]]:
    """Places from places.json plus the optional places_extra.json (extra attractions)."""
    places = list(_load_json("places.json"))
    if (DATA_DIR / "places_extra.json").exists():
        places += _load_json("places_extra.json")
    return places


def available_cities() -> list[str]:
    """Cities that appear in the hotels dataset (every city has stays)."""
    return sorted({hotel["city"] for hotel in load_hotels()})


def available_place_types() -> list[str]:
    """All attraction types found in places.json (used for the interest filter)."""
    return sorted({place["type"] for place in load_places()})
