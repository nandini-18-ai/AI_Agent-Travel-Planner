"""Helpers that turn a plan dictionary into readable text.

``report_text`` follows the output format shown in the project brief:
"Your 3-Day Trip to Goa (Feb 12-14)", Flight Selected, Hotel Booked,
Weather, Itinerary, Estimated Total Budget.
"""

from __future__ import annotations

from datetime import date
from typing import Any


def to_number(value: Any, default: float = 0) -> float:
    """Convert a value to float without raising (the LLM may return strings)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def inr(value: Any) -> str:
    return f"₹{to_number(value):,.0f}"


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def date_range(start: Any, end: Any) -> str:
    """Format a date span like 'Feb 12–14' or 'Feb 28–Mar 2'."""
    try:
        first, last = _as_date(start), _as_date(end)
    except (TypeError, ValueError):
        return ""
    if (first.year, first.month) == (last.year, last.month):
        return f"{first:%b} {first.day}–{last.day}"
    return f"{first:%b} {first.day}–{last:%b} {last.day}"


def trip_title(summary: dict[str, Any]) -> str:
    """Build the headline, e.g. 'Your 3-Day Trip to Goa (Feb 12–14)'."""
    days, destination = summary.get("days"), summary.get("destination")
    if not days or not destination:
        return summary.get("title") or "Your trip"
    span = date_range(summary.get("start_date"), summary.get("end_date"))
    return f"Your {days}-Day Trip to {destination}" + (f" ({span})" if span else "")


def flight_lines(route: dict[str, Any] | None, prefix: str = "") -> list[str]:
    """One line per flight leg: '- IndiGo (₹4,800) – Departs Delhi at 14:00'."""
    if not route:
        return [f"- {prefix}No flight found in the dataset"]
    return [
        f"- {prefix}{leg.get('airline')} ({inr(leg.get('price'))}) – "
        f"Departs {leg.get('from')} at {leg.get('departure_time')}"
        for leg in route.get("legs", [])
    ]


def report_text(plan: dict[str, Any]) -> str:
    """Human-readable trip report in the format given in the project brief."""
    summary = plan.get("trip_summary") or {}
    flight = plan.get("flight") or {}
    hotel = plan.get("hotel")
    budget = plan.get("budget") or {}

    lines = [trip_title(summary), "", "Flight Selected:"]
    lines += flight_lines(flight.get("outbound"))
    lines += flight_lines(flight.get("return"), prefix="Return: ")

    lines += ["", "Hotel Booked:"]
    if hotel:
        lines.append(f"- {hotel.get('name')} ({inr(hotel.get('price_per_night'))}/night, "
                     f"{hotel.get('stars')}-star)")
    else:
        lines.append("- No hotel found for the chosen filters")

    lines += ["", "Weather:"]
    for number, day in enumerate(plan.get("weather") or [], start=1):
        high = day.get("temp_max")
        temp = "" if high is None else f" ({to_number(high):.0f}°C)"
        lines.append(f"- Day {number}: {day.get('condition')}{temp}")

    lines += ["", "Itinerary:"]
    for day in plan.get("itinerary") or []:
        places = ", ".join(str(a.get("place")) for a in day.get("activities", []))
        lines.append(f"Day {day.get('day')}: {places}")

    lines += [
        "", "Estimated Total Budget:",
        f"- Flight: {inr(budget.get('flights'))}",
        f"- Hotel: {inr(budget.get('hotel'))}",
        f"- Food & Travel: {inr(budget.get('food_and_local'))}",
        "-" * 37,
        f"Total Cost: {inr(budget.get('total'))}",
    ]
    return "\n".join(lines)


def plan_to_text(plan: dict[str, Any]) -> str:
    """Downloadable text: the report plus the reasoning behind each choice."""
    text = report_text(plan)
    reasons = plan.get("reasoning") or []
    if reasons:
        text += "\n\nWhy we selected this:\n" + "\n".join(f"- {reason}" for reason in reasons)
    return text
