"""LangChain tools exposed to the travel agent.

Each tool is a thin wrapper around a function in ``core.py`` that returns a JSON
string, which is what the LLM reads. The docstrings matter: the agent uses
them to decide *when* to call each tool.
"""

from __future__ import annotations

import json

from langchain_core.tools import tool

import core


def _split(csv_text: str) -> list[str]:
    return [item.strip() for item in (csv_text or "").split(",") if item.strip()]


@tool
def flight_search_tool(origin: str, destination: str, preference: str = "cheapest") -> str:
    """Find flights from the flights dataset between two cities.

    Args:
        origin: Departure city, e.g. "Goa".
        destination: Arrival city, e.g. "Bangalore".
        preference: "cheapest" or "fastest".
    Call it once for the outbound route and once more (swapped cities) for the
    return route. Returns the selected option (with legs, price, duration) and
    alternatives. Connecting routes are used when no direct flight exists.
    """
    return json.dumps(core.search_flights(origin, destination, preference))


@tool
def hotel_recommendation_tool(
    city: str,
    min_stars: int = 1,
    max_price_per_night: int = 0,
    required_amenities: str = "",
    sort_by: str = "best_value",
) -> str:
    """Recommend hotels in a city from the hotels dataset.

    Args:
        city: City name.
        min_stars: Minimum star rating (1-5).
        max_price_per_night: Max price per night in INR; 0 means no limit.
        required_amenities: Comma separated, e.g. "wifi,pool". Empty for none.
        sort_by: "best_value", "price" or "stars".
    Returns ranked options plus the selected hotel.
    """
    result = core.recommend_hotels(
        city, min_stars, max_price_per_night or None, _split(required_amenities), sort_by
    )
    return json.dumps(result)


@tool
def places_discovery_tool(city: str, place_types: str = "") -> str:
    """Find attractions (points of interest) in a city, best rated first.

    Args:
        city: City name, e.g. "Goa".
        place_types: Comma separated types such as "temple,museum,beach,park,
            fort,lake,market,monument". Use an empty string for all types.
    Returns up to 20 places with their type and rating.
    """
    return json.dumps(core.discover_places(city, 0.0, _split(place_types), 20))


@tool
def weather_lookup_tool(city: str, start_date: str, end_date: str) -> str:
    """Get daily weather (condition, max/min temperature in °C, rain) for a city.

    Args:
        city: City name.
        start_date: First trip day, YYYY-MM-DD.
        end_date: Last trip day, YYYY-MM-DD.
    Uses the live Open-Meteo forecast for the next 16 days, otherwise typical
    weather for the same dates in a past year.
    """
    return json.dumps(core.get_weather(city, start_date, end_date))


@tool
def budget_estimation_tool(
    flight_total_per_person: float,
    hotel_price_per_night: float,
    nights: int,
    travelers: int = 1,
    daily_local_expense_per_person: float = 1500,
    budget_limit: float = 0,
) -> str:
    """Estimate the total trip cost in INR.

    Args:
        flight_total_per_person: Round-trip flight cost for ONE traveller.
        hotel_price_per_night: Price of one room per night.
        nights: Number of nights (trip days minus one).
        travelers: Number of travellers.
        daily_local_expense_per_person: Food and local transport per person per day.
        budget_limit: The user's maximum total budget; 0 if none.
    """
    result = core.estimate_budget(
        flight_total_per_person, hotel_price_per_night, nights, travelers,
        daily_local_expense_per_person, budget_limit or None,
    )
    return json.dumps(result)


ALL_TOOLS = [
    flight_search_tool,
    hotel_recommendation_tool,
    places_discovery_tool,
    weather_lookup_tool,
    budget_estimation_tool,
]
