"""Core travel logic used by both the LangChain tools and the quick planner.

Every function here is plain Python (no LLM, no LangChain) so it can be tested
on its own. ``tools.py`` wraps these functions as LangChain tools.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Optional

import requests

from config import (
    ARCHIVE_URL,
    CITY_COORDS,
    FORECAST_URL,
    FORECAST_WINDOW_DAYS,
)
from data_loader import load_flights, load_hotels, load_places

REQUEST_TIMEOUT_SECONDS = 15


def _norm(text: str) -> str:
    return (text or "").strip().lower()


# =========================================================================== #
# FLIGHTS
# =========================================================================== #
def _to_leg(flight: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw flight record into a display-friendly leg."""
    departure = datetime.fromisoformat(flight["departure_time"])
    arrival = datetime.fromisoformat(flight["arrival_time"])
    hours = round((arrival - departure).total_seconds() / 3600, 1)
    return {
        "flight_id": flight["flight_id"],
        "airline": flight["airline"],
        "from": flight["from"],
        "to": flight["to"],
        "departure_time": departure.strftime("%H:%M"),
        "arrival_time": arrival.strftime("%H:%M"),
        "duration_hours": hours,
        "price": flight["price"],
    }


def _find_routes(origin: str, destination: str, max_legs: int = 4) -> dict[int, list[list[dict]]]:
    """Depth-first search for flight chains origin -> ... -> destination."""
    by_origin: dict[str, list[dict]] = {}
    for flight in load_flights():
        by_origin.setdefault(_norm(flight["from"]), []).append(flight)

    target = _norm(destination)
    routes: dict[int, list[list[dict]]] = {n: [] for n in range(1, max_legs + 1)}

    def walk(city: str, path: list[dict], visited: set[str]) -> None:
        if len(path) >= max_legs:
            return
        for flight in by_origin.get(city, []):
            next_city = _norm(flight["to"])
            if next_city in visited:
                continue
            new_path = path + [flight]
            if next_city == target:
                routes[len(new_path)].append(new_path)
            else:
                walk(next_city, new_path, visited | {next_city})

    walk(_norm(origin), [], {_norm(origin)})
    return routes


def search_flights(origin: str, destination: str, preference: str = "cheapest") -> dict[str, Any]:
    """Find flights from ``origin`` to ``destination``.

    The dataset has fixed schedules, so the travel date is not used for
    filtering. If no direct flight exists the search falls back to routes with
    connections (up to 3 stops, since the sample data is sparse). ``preference`` is ``cheapest`` or ``fastest``.
    """
    if _norm(origin) == _norm(destination):
        return {"found": False, "options": [], "selected": None,
                "note": "Origin and destination are the same city."}

    routes = _find_routes(origin, destination)
    for leg_count in sorted(routes):
        if not routes[leg_count]:
            continue
        options = []
        for path in routes[leg_count]:
            legs = [_to_leg(f) for f in path]
            options.append({
                "legs": legs,
                "stops": leg_count - 1,
                "total_price": sum(leg["price"] for leg in legs),
                "total_duration_hours": round(sum(leg["duration_hours"] for leg in legs), 1),
            })
        if preference == "fastest":
            options.sort(key=lambda o: (o["total_duration_hours"], o["total_price"]))
        else:
            options.sort(key=lambda o: (o["total_price"], o["total_duration_hours"]))

        route_type = "direct" if leg_count == 1 else f"{leg_count - 1}-stop"
        note = "Dataset schedules are fixed; times and prices are indicative for your dates."
        if leg_count > 1:
            note = (f"No direct flight in the dataset, so a route with {leg_count - 1} "
                    f"connection{'s' if leg_count > 2 else ''} was used. Connection timings are indicative.")
        return {
            "found": True,
            "route_type": route_type,
            "options": options[:5],
            "selected": options[0],
            "note": note,
        }

    return {"found": False, "options": [], "selected": None,
            "note": f"No route from {origin} to {destination} (even with connections) in the dataset."}


# =========================================================================== #
# HOTELS
# =========================================================================== #
def recommend_hotels(
    city: str,
    min_stars: int = 1,
    max_price_per_night: Optional[int] = None,
    required_amenities: Optional[list[str]] = None,
    sort_by: str = "best_value",
) -> dict[str, Any]:
    """Filter hotels in ``city`` and rank them.

    ``sort_by`` is ``best_value`` (stars per rupee), ``price`` or ``stars``.
    If nothing matches, filters are relaxed step by step and a note explains it.
    """
    amenities = [a.strip().lower() for a in (required_amenities or []) if a.strip()]
    in_city = [h for h in load_hotels() if _norm(h["city"]) == _norm(city)]
    if not in_city:
        return {"found": False, "options": [], "selected": None,
                "note": f"No hotels listed for {city}."}

    def apply(stars: int, price: Optional[int], needed: list[str]) -> list[dict]:
        return [
            h for h in in_city
            if h["stars"] >= stars
            and (not price or h["price_per_night"] <= price)
            and all(a in [x.lower() for x in h["amenities"]] for a in needed)
        ]

    attempts = [
        (min_stars, max_price_per_night, amenities, ""),
        (min_stars, max_price_per_night, [], "Amenity filter relaxed because no hotel matched all of them."),
        (min_stars, None, [], "Price limit relaxed because no hotel matched it."),
        (1, None, [], "Star and price filters relaxed because no hotel matched them."),
    ]
    candidates, note = [], ""
    for stars, price, needed, message in attempts:
        candidates = apply(stars, price, needed)
        if candidates:
            note = message
            break

    enriched = [
        {**h, "value_score": round(h["stars"] / (h["price_per_night"] / 1000), 2)}
        for h in candidates
    ]
    if sort_by == "price":
        enriched.sort(key=lambda h: h["price_per_night"])
    elif sort_by == "stars":
        enriched.sort(key=lambda h: (-h["stars"], h["price_per_night"]))
    else:
        enriched.sort(key=lambda h: (-h["value_score"], h["price_per_night"]))

    return {"found": bool(enriched), "match_count": len(enriched),
            "options": enriched[:5], "selected": enriched[0] if enriched else None,
            "note": note}


# =========================================================================== #
# PLACES
# =========================================================================== #
def discover_places(
    city: str,
    min_rating: float = 0.0,
    place_types: Optional[list[str]] = None,
    limit: int = 8,
) -> dict[str, Any]:
    """Return attractions in ``city`` sorted by rating (highest first)."""
    types = {t.strip().lower() for t in (place_types or []) if t.strip()}
    places = [
        p for p in load_places()
        if _norm(p["city"]) == _norm(city)
        and p["rating"] >= min_rating
        and (not types or p["type"].lower() in types)
    ]
    places.sort(key=lambda p: -p["rating"])
    return {"found": bool(places), "places": places[:limit]}


# =========================================================================== #
# WEATHER (Open-Meteo)
# =========================================================================== #
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain",
    65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain", 71: "Light snow",
    73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Light showers",
    81: "Showers", 82: "Heavy showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}


def _shift_years_back(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 Feb
        return day.replace(year=day.year - years, day=28)


def get_weather(city: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Daily weather for a city between two ISO dates (YYYY-MM-DD).

    Uses the live forecast when the dates fall inside Open-Meteo's ~16-day
    window; otherwise uses historical data for the same dates in a past year
    as a typical-weather estimate.
    """
    coords = {k.lower(): v for k, v in CITY_COORDS.items()}.get(_norm(city))
    if coords is None:
        return {"found": False, "days": [], "source": "unavailable",
                "note": f"No coordinates configured for {city}."}
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except ValueError:
        return {"found": False, "days": [], "source": "unavailable",
                "note": "Dates must be in YYYY-MM-DD format."}

    latitude, longitude = coords
    today = date.today()
    use_forecast = start >= today and end <= today + timedelta(days=FORECAST_WINDOW_DAYS)

    try:
        if use_forecast:
            response = requests.get(FORECAST_URL, params={
                "latitude": latitude, "longitude": longitude, "timezone": "auto",
                "start_date": start.isoformat(), "end_date": end.isoformat(),
                "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            }, timeout=REQUEST_TIMEOUT_SECONDS)
            source = "Open-Meteo live forecast"
        else:
            shift = 1
            while _shift_years_back(end, shift) >= today - timedelta(days=7):
                shift += 1
            past_start, past_end = _shift_years_back(start, shift), _shift_years_back(end, shift)
            response = requests.get(ARCHIVE_URL, params={
                "latitude": latitude, "longitude": longitude, "timezone": "auto",
                "start_date": past_start.isoformat(), "end_date": past_end.isoformat(),
                "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum",
            }, timeout=REQUEST_TIMEOUT_SECONDS)
            source = (f"Typical weather based on Open-Meteo data for the same dates in "
                      f"{past_start.year} (live forecasts cover only the next 16 days)")
        response.raise_for_status()
        daily = response.json()["daily"]
    except (requests.RequestException, KeyError, ValueError) as error:
        return {"found": False, "days": [], "source": "unavailable",
                "note": f"Weather service error: {error}"}

    def pick(key: str, index: int):
        values = daily.get(key) or []
        return values[index] if index < len(values) else None

    days = []
    trip_length = (end - start).days + 1
    for index in range(min(trip_length, len(daily.get("time", [])))):
        if use_forecast:
            chance = pick("precipitation_probability_max", index)
            rain_info = f"{chance}% chance of rain" if chance is not None else "Rain chance n/a"
        else:
            rain = pick("precipitation_sum", index)
            rain_info = f"{rain} mm rain" if rain is not None else "Rainfall n/a"
        days.append({
            "date": (start + timedelta(days=index)).isoformat(),
            "condition": WMO_CODES.get(pick("weathercode", index), "Mixed conditions"),
            "temp_max": pick("temperature_2m_max", index),
            "temp_min": pick("temperature_2m_min", index),
            "rain_info": rain_info,
        })
    return {"found": bool(days), "days": days, "source": source, "note": ""}


# =========================================================================== #
# BUDGET
# =========================================================================== #
def estimate_budget(
    flight_total_per_person: float,
    hotel_price_per_night: float,
    nights: int,
    travelers: int = 1,
    daily_local_expense_per_person: float = 1500,
    budget_limit: Optional[float] = None,
) -> dict[str, Any]:
    """Sum flights + hotel + local expenses.

    Flights are per traveller (round trip). Hotel rooms are shared by two
    travellers. Local expenses cover food and transport for every trip day.
    """
    days = nights + 1
    rooms = math.ceil(travelers / 2)
    flights = flight_total_per_person * travelers
    hotel = hotel_price_per_night * nights * rooms
    local = daily_local_expense_per_person * days * travelers
    total = flights + hotel + local

    within = None
    note = ""
    if budget_limit:
        within = total <= budget_limit
        difference = abs(budget_limit - total)
        note = (f"₹{difference:,.0f} under your budget." if within
                else f"₹{difference:,.0f} over your budget.")
    return {
        "flights": round(flights), "hotel": round(hotel), "food_and_local": round(local),
        "total": round(total), "rooms": rooms, "travelers": travelers, "nights": nights,
        "days": days, "budget_limit": budget_limit or None,
        "within_budget": within, "note": note,
    }
