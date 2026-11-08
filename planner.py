"""Quick planner: builds a full itinerary with plain Python (no LLM).

It produces exactly the same JSON structure as the AI agent, so the UI can
render either one. It is also the safety net when no API key is available or
the LLM service fails during a demo.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import core
from config import DEFAULT_DAILY_EXPENSE
from formatters import trip_title

TIME_SLOTS = ["Morning", "Afternoon", "Evening"]


def trip_length(start: date, end: date) -> tuple[int, int]:
    """Return (days, nights) for an inclusive date range."""
    days = (end - start).days + 1
    return days, max(days - 1, 0)


def _with_date(route: dict[str, Any] | None, day: date) -> dict[str, Any] | None:
    return {**route, "date": day.isoformat()} if route else None


def _split_places_by_day(places: list[dict], days: int) -> list[list[dict]]:
    """Spread places over the days (max 3 per day); extra days stay free."""
    base, extra = divmod(len(places), days)
    chunks, cursor = [], 0
    for index in range(days):
        count = min(base + (1 if index < extra else 0), 3)
        chunks.append(places[cursor:cursor + count])
        cursor += count
    return chunks


def build_plan(params: dict[str, Any]) -> dict[str, Any]:
    """Create a trip plan from the form parameters.

    Expected keys: origin, destination, start_date, end_date (date objects),
    travelers, min_stars, max_hotel_price, flight_preference, interests (list),
    daily_expense, budget_limit.
    """
    origin, destination = params["origin"], params["destination"]
    start, end = params["start_date"], params["end_date"]
    travelers = params.get("travelers", 1)
    days, nights = trip_length(start, end)
    preference = params.get("flight_preference", "cheapest")
    interests = params.get("interests") or []
    daily_expense = params.get("daily_expense", DEFAULT_DAILY_EXPENSE)
    reasoning: list[str] = []

    # ---- Flights --------------------------------------------------------- #
    outbound_result = core.search_flights(origin, destination, preference)
    return_result = core.search_flights(destination, origin, preference)
    outbound = outbound_result["selected"]
    inbound = return_result["selected"]

    if outbound:
        flight_cost = outbound["total_price"] + (inbound["total_price"] if inbound else outbound["total_price"])
        reasoning.append(
            f"Outbound: chose the {preference} {outbound_result['route_type']} option "
            f"({core_price(outbound['total_price'])}) out of {len(outbound_result['options'])} found. "
            f"{outbound_result['note']}"
        )
        if inbound:
            reasoning.append(f"Return: chose the {preference} {return_result['route_type']} option "
                             f"({core_price(inbound['total_price'])}).")
        else:
            reasoning.append("No return flight exists in the dataset, so the return fare is assumed "
                             "equal to the outbound fare.")
    else:
        flight_cost = 0
        reasoning.append(outbound_result["note"] + " Flights are excluded from the budget.")

    # ---- Hotel ----------------------------------------------------------- #
    hotel_result = core.recommend_hotels(
        destination, params.get("min_stars", 1), params.get("max_hotel_price") or None,
        params.get("amenities"), "best_value",
    )
    hotel = hotel_result["selected"]
    if hotel:
        reasoning.append(
            f"Hotel: {hotel['name']} gives the best value (stars per rupee) among "
            f"{hotel_result['match_count']} matching hotels. {hotel_result['note']}".strip()
        )

    # ---- Weather --------------------------------------------------------- #
    weather_result = core.get_weather(destination, start.isoformat(), end.isoformat())
    weather = weather_result["days"] or [
        {"date": (start + timedelta(days=i)).isoformat(), "condition": "Forecast unavailable",
         "temp_max": None, "temp_min": None, "rain_info": ""}
        for i in range(days)
    ]
    reasoning.append(f"Weather source: {weather_result['source']}.")

    # ---- Places & itinerary --------------------------------------------- #
    wanted = days * 2
    chosen = core.discover_places(destination, 0, interests, wanted)["places"]
    if len(chosen) < wanted:
        chosen_ids = {p["place_id"] for p in chosen}
        extras = [p for p in core.discover_places(destination, 0, None, 50)["places"]
                  if p["place_id"] not in chosen_ids]
        chosen += extras[: wanted - len(chosen)]
    reasoning.append(f"Places: picked the highest rated attractions"
                     f"{' matching ' + ', '.join(interests) if interests else ''}.")

    itinerary = []
    for index, day_places in enumerate(_split_places_by_day(chosen, days)):
        current_day = start + timedelta(days=index)
        if index == 0:
            title = f"Arrive in {destination}"
        elif index == days - 1:
            title = "Final highlights and departure"
        else:
            title = f"Discover {destination}"
        activities = [
            {"time_of_day": TIME_SLOTS[slot], "place": f"{p['name']}", "type": p["type"],
             "rating": p["rating"], "note": f"A {p['type']} rated {p['rating']}/5."}
            for slot, p in enumerate(day_places)
        ]
        if not activities:
            activities = [{"time_of_day": "All day", "place": f"Free day in {destination}",
                           "type": "leisure", "rating": None,
                           "note": "No more attractions in the dataset. Explore local cafes and markets."}]
        itinerary.append({"day": index + 1, "date": current_day.isoformat(),
                          "title": title, "activities": activities})

    # ---- Budget ---------------------------------------------------------- #
    budget = core.estimate_budget(
        flight_cost, hotel["price_per_night"] if hotel else 0, nights, travelers,
        daily_expense, params.get("budget_limit") or None,
    )

    summary = {
        "origin": origin, "destination": destination,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "days": days, "nights": nights, "travelers": travelers,
        "overview": (f"{days} days and {nights} nights in {destination} for {travelers} "
                     f"traveller{'s' if travelers != 1 else ''}, flying from {origin}."),
    }
    summary["title"] = trip_title(summary)

    return {
        "trip_summary": summary,
        "flight": {
            "outbound": _with_date(outbound, start),
            "return": _with_date(inbound, end),
            "total_price_per_person": flight_cost,
            "reason": (f"Selected the {preference} {outbound_result['route_type']} option out of "
                       f"{len(outbound_result['options'])} found. {outbound_result['note']}"
                       if outbound else outbound_result["note"]),
        },
        "hotel": ({**hotel, "reason": f"Best value among {hotel_result['match_count']} matching hotels."}
                  if hotel else None),
        "weather": weather,
        "itinerary": itinerary,
        "budget": budget,
        "reasoning": reasoning,
        "data_note": weather_result["source"],
    }


def core_price(value: float) -> str:
    return f"₹{value:,.0f}"
