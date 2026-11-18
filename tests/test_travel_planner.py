"""Unit tests for the travel planner.

Run from the project folder with:  python -m pytest

The tests use the provided sample datasets in ``data/`` and need no internet
(weather calls are replaced by a fake) and no API key.
"""

from datetime import date, timedelta

import pytest

import core
import formatters
import planner


# --------------------------------------------------------------------------- #
# Flights
# --------------------------------------------------------------------------- #
def test_direct_flight_is_found():
    result = core.search_flights("Hyderabad", "Goa")
    assert result["found"]
    assert result["route_type"] == "direct"
    assert result["selected"]["legs"][0]["flight_id"] == "FL0016"


def test_cheapest_and_fastest_choose_different_flights():
    cheapest = core.search_flights("Bangalore", "Goa", "cheapest")["selected"]["legs"][0]
    fastest = core.search_flights("Bangalore", "Goa", "fastest")["selected"]["legs"][0]
    assert cheapest["flight_id"] == "FL0021"  # Rs 5,356
    assert fastest["flight_id"] == "FL0020"   # 1 hour


def test_connecting_route_when_no_direct_flight():
    result = core.search_flights("Goa", "Delhi")
    assert result["route_type"] == "1-stop"
    assert len(result["selected"]["legs"]) == 2
    assert result["selected"]["total_price"] == 9499


def test_long_connection_is_found():
    result = core.search_flights("Delhi", "Goa")
    assert result["found"]
    assert result["selected"]["stops"] == 3
    assert result["selected"]["total_price"] == 20255


def test_connecting_legs_are_chained():
    legs = core.search_flights("Delhi", "Goa")["selected"]["legs"]
    for current, following in zip(legs, legs[1:]):
        assert current["to"] == following["from"]
    assert legs[0]["from"] == "Delhi"
    assert legs[-1]["to"] == "Goa"


def test_same_city_has_no_flight():
    assert not core.search_flights("Goa", "Goa")["found"]


# --------------------------------------------------------------------------- #
# Hotels
# --------------------------------------------------------------------------- #
def test_best_value_hotel():
    result = core.recommend_hotels("Goa", min_stars=3, max_price_per_night=3000)
    assert result["selected"]["hotel_id"] == "HOT0014"


def test_amenity_filter():
    result = core.recommend_hotels("Goa", 3, 3000, ["spa"])
    assert result["selected"]["hotel_id"] == "HOT0015"
    assert all("spa" in hotel["amenities"] for hotel in result["options"])


def test_minimum_stars_are_respected():
    result = core.recommend_hotels("Goa", min_stars=4)
    assert result["options"]
    assert all(hotel["stars"] >= 4 for hotel in result["options"])


def test_sort_by_price():
    result = core.recommend_hotels("Goa", sort_by="price")
    assert result["selected"]["hotel_id"] == "HOT0014"


def test_filters_are_relaxed_when_nothing_matches():
    result = core.recommend_hotels("Goa", min_stars=5, max_price_per_night=1000)
    assert result["found"]
    assert "Price limit relaxed" in result["note"]
    assert result["selected"]["stars"] == 5


def test_unknown_city_has_no_hotels():
    assert not core.recommend_hotels("Atlantis")["found"]


# --------------------------------------------------------------------------- #
# Places
# --------------------------------------------------------------------------- #
def test_places_sorted_by_rating():
    ratings = [p["rating"] for p in core.discover_places("Goa")["places"]]
    assert ratings == sorted(ratings, reverse=True)


def test_places_type_filter():
    places = core.discover_places("Goa", place_types=["market"])["places"]
    assert places
    assert all(place["type"] == "market" for place in places)


def test_places_limit():
    assert len(core.discover_places("Goa", limit=3)["places"]) == 3


def test_unknown_city_has_no_places():
    assert not core.discover_places("Atlantis")["found"]


# --------------------------------------------------------------------------- #
# Budget
# --------------------------------------------------------------------------- #
def test_budget_formula():
    budget = core.estimate_budget(10000, 2000, nights=2, travelers=3,
                                  daily_local_expense_per_person=1500)
    assert budget["rooms"] == 2            # two travellers share a room
    assert budget["flights"] == 30000      # 10,000 x 3
    assert budget["hotel"] == 8000         # 2,000 x 2 nights x 2 rooms
    assert budget["food_and_local"] == 13500  # 1,500 x 3 days x 3 travellers
    assert budget["total"] == 51500
    assert budget["within_budget"] is None


def test_budget_limit_messages():
    over = core.estimate_budget(10000, 2000, 2, 3, 1500, budget_limit=40000)
    under = core.estimate_budget(10000, 2000, 2, 3, 1500, budget_limit=60000)
    assert over["within_budget"] is False and "over your budget" in over["note"]
    assert under["within_budget"] is True and "under your budget" in under["note"]


# --------------------------------------------------------------------------- #
# Weather (offline checks only)
# --------------------------------------------------------------------------- #
def test_weather_unknown_city():
    assert not core.get_weather("Atlantis", "2026-12-01", "2026-12-03")["found"]


def test_weather_bad_date_format():
    assert not core.get_weather("Goa", "not-a-date", "2026-12-03")["found"]


def test_leap_day_shift_does_not_crash():
    assert core._shift_years_back(date(2024, 2, 29), 1) == date(2023, 2, 28)


# --------------------------------------------------------------------------- #
# Formatters
# --------------------------------------------------------------------------- #
def test_inr_and_to_number():
    assert formatters.inr(7299) == "₹7,299"
    assert formatters.to_number("abc", 5) == 5


def test_date_range():
    assert formatters.date_range("2026-11-14", "2026-11-16") == "Nov 14–16"
    assert formatters.date_range("2026-02-28", "2026-03-02") == "Feb 28–Mar 2"


def test_trip_title_matches_project_brief_format():
    summary = {"days": 3, "destination": "Goa",
               "start_date": "2026-02-12", "end_date": "2026-02-14"}
    assert formatters.trip_title(summary) == "Your 3-Day Trip to Goa (Feb 12–14)"


# --------------------------------------------------------------------------- #
# Quick planner (weather is faked so no internet is needed)
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_weather(monkeypatch):
    def fake(city, start, end):
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        days = [{"date": (first + timedelta(days=i)).isoformat(), "condition": "Clear sky",
                 "temp_max": 31, "temp_min": 24, "rain_info": "0% chance of rain"}
                for i in range((last - first).days + 1)]
        return {"found": True, "days": days, "source": "test data", "note": ""}

    monkeypatch.setattr(core, "get_weather", fake)


def make_params(days=3, **overrides):
    start = date(2026, 12, 1)
    params = {
        "origin": "Hyderabad", "destination": "Goa", "start_date": start,
        "end_date": start + timedelta(days=days - 1), "travelers": 2,
        "flight_preference": "cheapest", "min_stars": 3, "max_hotel_price": 7000,
        "interests": [], "amenities": [], "daily_expense": 1500, "budget_limit": 0,
    }
    params.update(overrides)
    return params


def test_plan_has_every_required_section(fake_weather):
    plan = planner.build_plan(make_params())
    for key in ("trip_summary", "flight", "hotel", "weather", "itinerary", "budget", "reasoning"):
        assert plan[key]
    assert plan["trip_summary"]["title"].startswith("Your 3-Day Trip to Goa")
    assert len(plan["itinerary"]) == 3
    assert len(plan["weather"]) == 3


def test_plan_budget_adds_up(fake_weather):
    budget = planner.build_plan(make_params())["budget"]
    assert budget["flights"] == (7299 + 6592) * 2
    assert budget["hotel"] == 1232 * 2
    assert budget["food_and_local"] == 1500 * 3 * 2
    assert budget["total"] == budget["flights"] + budget["hotel"] + budget["food_and_local"]


def test_plan_flags_budget_overrun(fake_weather):
    budget = planner.build_plan(make_params(budget_limit=10000))["budget"]
    assert budget["within_budget"] is False


def test_seven_day_plan_has_no_repeated_places(fake_weather):
    plan = planner.build_plan(make_params(days=7))
    assert len(plan["itinerary"]) == 7
    names = [a["place"] for day in plan["itinerary"] for a in day["activities"]
             if a["type"] != "leisure"]
    assert len(names) == len(set(names))


def test_report_text_follows_project_brief(fake_weather):
    text = formatters.report_text(planner.build_plan(make_params()))
    for heading in ("Flight Selected:", "Hotel Booked:", "Weather:", "Itinerary:",
                    "Estimated Total Budget:", "Total Cost:"):
        assert heading in text


# --------------------------------------------------------------------------- #
# Agent helpers (skipped automatically if LangChain is not installed)
# --------------------------------------------------------------------------- #
def test_extract_json_handles_common_model_formats():
    pytest.importorskip("langchain_core")
    import agent

    assert agent.extract_json('{"a": 1}') == {"a": 1}
    assert agent.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert agent.extract_json('Here is the plan: {"a": 1} Enjoy!') == {"a": 1}
    assert agent.extract_json("not json at all") is None


def test_fill_empty_days_uses_unused_places():
    pytest.importorskip("langchain_core")
    import agent

    plan = {"itinerary": [{"day": 1, "activities": []},
                          {"day": 2, "activities": [{"place": "Existing Place"}]}],
            "reasoning": []}
    result = agent.fill_empty_days(plan, "Goa")
    assert result["itinerary"][0]["activities"]
    assert result["itinerary"][0]["activities"][0]["place"] != "Existing Place"
    assert result["reasoning"]
