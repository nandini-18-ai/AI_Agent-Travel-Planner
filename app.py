"""Wayfinder: AI travel planner (Streamlit UI).

Run with:  streamlit run app.py
"""

from __future__ import annotations

import html
import json
import time
from datetime import date, timedelta

import streamlit as st

from config import (
    DEFAULT_DAILY_EXPENSE,
    LLM_PROVIDERS,
    MAX_TRIP_DAYS,
    MIN_TRIP_DAYS,
    get_secret,
)
from data_loader import available_cities, available_place_types
from formatters import inr, plan_to_text, report_text, to_number, trip_title
from planner import build_plan, trip_length

st.set_page_config(page_title="Wayfinder | AI Travel Planner", page_icon="✈️", layout="wide")

AMENITY_OPTIONS = ["wifi", "pool", "gym", "spa", "breakfast", "parking"]

# --------------------------------------------------------------------------- #
# Styling: white page, navy ink, teal accent, one dark banner as the focal point
# --------------------------------------------------------------------------- #
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stApp, button, input, textarea, select {
    font-family: 'Manrope', 'Segoe UI', sans-serif !important;
}
.stApp, [data-testid="stAppViewContainer"] { background: #ffffff; color: #12263A; }
[data-testid="stSidebar"] { background: #F6F9FA; border-right: 1px solid #E1E9EC; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"], #MainMenu, footer { display: none !important; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1160px; }

h1, h2, h3 { color: #12263A; letter-spacing: -0.01em; }
.brandbar { display: flex; align-items: center; justify-content: space-between;
    padding-bottom: 1rem; border-bottom: 1px solid #E1E9EC; margin-bottom: 1.8rem; }
.brand { display: flex; align-items: center; gap: .7rem; font-weight: 800; font-size: 1.25rem; color: #12263A; }
.brand-mark { width: 38px; height: 38px; border-radius: 10px; background: #0E7C86; color: #fff;
    display: flex; align-items: center; justify-content: center; font-size: 1.15rem; }
.brand-tag { color: #6B7F92; font-size: .9rem; font-weight: 600; }
.hero-title { font-size: 2.3rem; font-weight: 800; line-height: 1.15; margin: 0 0 .4rem 0; color: #12263A; }
.hero-sub { font-size: 1.05rem; color: #52667A; margin-bottom: 1.4rem; max-width: 640px; }
.section-title { font-size: 1.15rem; font-weight: 700; margin: 2rem 0 .8rem 0; color: #12263A; }
.muted { color: #6B7F92; font-size: .88rem; }

/* Form */
[data-testid="stForm"] { border: 1px solid #DCE5E8; border-radius: 16px;
    padding: 1.4rem 1.4rem .6rem 1.4rem; background: #fff; }
.form-group { font-weight: 700; color: #12263A; font-size: .95rem; margin: .3rem 0 .6rem 0;
    padding-bottom: .35rem; border-bottom: 1px solid #EEF3F5; }
[data-testid="stFormSubmitButton"] button {
    width: 100%; background: #0E7C86; color: #fff; border: none; border-radius: 10px;
    padding: .75rem 1rem; font-weight: 700; font-size: 1rem;
}
[data-testid="stFormSubmitButton"] button:hover { background: #0B646D; color: #fff; }
[data-testid="stFormSubmitButton"] button:focus-visible { outline: 3px solid #9ADCE2; }
.stTabs [data-baseweb="tab"] { font-weight: 700; padding: .6rem 1.1rem; }
.stTabs [aria-selected="true"] { color: #0E7C86; }

/* Summary banner (the focal block) */
.banner { display: flex; justify-content: space-between; align-items: flex-end; gap: 2rem; flex-wrap: wrap;
    background: #12263A; color: #fff; border-radius: 18px; padding: 1.8rem 2rem; }
.banner-title { color: #8FB4C8; font-weight: 700; font-size: .95rem; margin-bottom: .5rem; }
.banner-route { font-size: 2.1rem; font-weight: 800; line-height: 1.1; }
.banner-route span { font-weight: 500; color: #8FB4C8; font-size: 1.2rem; margin: 0 .35rem; }
.banner-meta { margin-top: .6rem; color: #C9DAE5; font-weight: 600; }
.banner-text { margin-top: .5rem; color: #9DB6C6; max-width: 520px; font-size: .95rem; }
.banner-total { text-align: right; }
.banner-total-label { color: #8FB4C8; font-size: .9rem; font-weight: 600; }
.banner-total-value { font-size: 2.4rem; font-weight: 800; line-height: 1.1; }
.banner-total-note { color: #7FD6A8; font-size: .88rem; font-weight: 600; margin-top: .2rem; }
.banner-total-note.over { color: #FFB4A8; }

/* Cards and tiles */
.card { border: 1px solid #DCE5E8; border-radius: 14px; padding: 1.2rem 1.3rem; background: #fff; height: 100%; }
.card-title { font-size: 1rem; font-weight: 700; margin-bottom: .8rem; color: #12263A; }
.tile { border: 1px solid #DCE5E8; border-radius: 12px; padding: 1rem 1.1rem; background: #fff; height: 100%; }
.tile-label { color: #6B7F92; font-size: .85rem; font-weight: 600; }
.tile-value { font-size: 1.45rem; font-weight: 800; margin-top: .15rem; }
.tile-sub { color: #6B7F92; font-size: .8rem; font-weight: 500; }
.tile.total { background: #E3F2F3; border-color: #BFE0E3; }
.route-head { font-weight: 700; color: #0E7C86; font-size: .9rem; margin: .2rem 0 .4rem 0; }
.leg { padding: .55rem .75rem; background: #F4F8F9; border-radius: 10px; margin-bottom: .45rem; }
.leg b { color: #12263A; }
.pill { display: inline-block; background: #E3F2F3; color: #0B646D; border-radius: 999px; padding: .1rem .6rem;
    font-size: .78rem; font-weight: 700; margin-right: .4rem; }
.chip { display: inline-block; border: 1px solid #CFDDE1; border-radius: 8px; padding: .12rem .55rem;
    font-size: .8rem; color: #3B5167; margin: 0 .35rem .35rem 0; background: #fff; }
.hotel-name { font-size: 1.35rem; font-weight: 800; margin-bottom: .1rem; }
.stars { color: #D98E04; letter-spacing: 2px; }
.hotel-price { font-size: 1.1rem; font-weight: 700; margin: .5rem 0; }

/* Weather */
.wx { border: 1px solid #DCE5E8; border-radius: 12px; padding: .9rem .8rem; text-align: center; background: #fff; }
.wx-date { font-weight: 700; font-size: .85rem; color: #52667A; }
.wx-icon { font-size: 1.8rem; margin: .25rem 0; }
.wx-temp { font-size: 1.15rem; font-weight: 800; }
.wx-low { color: #6B7F92; font-weight: 600; font-size: .85rem; }
.wx-cond { font-size: .85rem; font-weight: 600; margin-top: .15rem; }
.wx-rain { font-size: .78rem; color: #6B7F92; }

/* Itinerary */
.day-head { display: flex; align-items: center; gap: .8rem; margin: 1.6rem 0 .7rem 0; }
.day-badge { background: #12263A; color: #fff; border-radius: 8px; padding: .25rem .75rem;
    font-weight: 700; font-size: .9rem; }
.day-name { font-weight: 700; font-size: 1.08rem; }
.day-date { color: #6B7F92; font-size: .9rem; font-weight: 600; }
.act { display: flex; gap: 1rem; border: 1px solid #DCE5E8; border-left: 4px solid #0E7C86; border-radius: 10px;
    padding: .8rem 1rem; margin-bottom: .6rem; background: #fff; }
.act-time { min-width: 86px; font-weight: 700; color: #0E7C86; font-size: .9rem; }
.act-name { font-weight: 700; }
.act-meta { color: #6B7F92; font-size: .85rem; }
.rating { color: #D98E04; font-weight: 700; }

/* Budget */
.split { display: flex; height: 12px; border-radius: 999px; overflow: hidden;
    margin: 1.2rem 0 .4rem 0; background: #EEF3F5; }
.split div { height: 100%; }
.legend { color: #52667A; font-size: .85rem; font-weight: 600; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin: 0 .3rem 0 .9rem; }
.cost-row { display: flex; justify-content: space-between; align-items: center; gap: 1rem;
    padding: .85rem 0; border-bottom: 1px solid #EEF3F5; }
.cost-what { font-weight: 700; }
.cost-how { color: #6B7F92; font-size: .85rem; }
.cost-amt { font-weight: 800; font-size: 1.05rem; }
.cost-total { display: flex; justify-content: space-between; padding: 1rem 1.2rem; margin-top: .9rem;
    background: #E3F2F3; border-radius: 12px; font-weight: 800; font-size: 1.2rem; }

/* Empty state */
.info { border: 1px solid #DCE5E8; border-radius: 14px; padding: 1.1rem 1.2rem; background: #F9FBFC; height: 100%; }
.info b { display: block; margin-bottom: .25rem; }
</style>
"""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def esc(value) -> str:
    """HTML-escape any value (None becomes an empty string)."""
    return "" if value is None else html.escape(str(value))


def show_html(markup: str) -> None:
    """Render HTML; lines are stripped so Markdown never treats them as code."""
    st.markdown(" ".join(line.strip() for line in markup.splitlines() if line.strip()),
                unsafe_allow_html=True)


def weather_icon(condition: str) -> str:
    text = (condition or "").lower()
    for keyword, icon in [("thunder", "⛈️"), ("snow", "❄️"), ("rain", "🌧️"), ("shower", "🌦️"),
                          ("drizzle", "🌦️"), ("fog", "🌫️"), ("overcast", "☁️"),
                          ("partly", "⛅"), ("mainly clear", "🌤️"), ("clear", "☀️")]:
        if keyword in text:
            return icon
    return "🌡️"


def short_date(iso_date: str) -> str:
    try:
        return date.fromisoformat(iso_date).strftime("%a, %d %b")
    except (TypeError, ValueError):
        return str(iso_date or "")


def temperature(value) -> str:
    return "–" if value is None else f"{to_number(value):.0f}°"


def group_heading(text: str) -> None:
    st.markdown(f'<div class="form-group">{text}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def render_sidebar() -> dict:
    """Planner settings. API keys are read from the server (.env or Streamlit Secrets), never typed here."""
    available = {name: info for name, info in LLM_PROVIDERS.items() if get_secret(info["env_key"])}
    settings = {"mode": "quick", "provider": None, "api_key": None, "model": None}

    with st.sidebar:
        st.markdown("### Planner settings")
        mode_label = st.radio(
            "Planning mode",
            ["AI agent (LangChain)", "Quick plan (no API key)"],
            index=0 if available else 1,
            help="The AI agent decides which tools to call and explains its choices. "
                 "Quick plan uses the same tools with fixed rules.",
        )
        if mode_label.startswith("AI"):
            if not available:
                st.warning("No LLM API key is configured, so Quick plan will be used. "
                           "Add GOOGLE_API_KEY to the .env file (local) or to Streamlit Secrets (deployed).")
            else:
                names = list(available)
                provider = names[0] if len(names) == 1 else st.selectbox("LLM provider", names)
                settings.update(mode="agent", provider=provider)
                st.success(f"AI agent powered by {provider}.")

        st.markdown("---")
        st.caption("Weather comes from Open-Meteo (free, no key). Flights, hotels and places come "
                   "from the JSON datasets in the data folder.")
    return settings


# --------------------------------------------------------------------------- #
# Input form
# --------------------------------------------------------------------------- #
def render_form():
    """Show the trip form. Returns (params, submitted)."""
    cities = available_cities()
    today = date.today()

    def index_of(city: str) -> int:
        return cities.index(city) if city in cities else 0

    with st.form("trip_form"):
        group_heading("Trip")
        c1, c2, c3, c4 = st.columns(4)
        origin = c1.selectbox("From", cities, index=index_of("Hyderabad"))
        destination = c2.selectbox("To", cities, index=index_of("Goa"))
        start_date = c3.date_input("Start date", value=today + timedelta(days=7), min_value=today)
        end_date = c4.date_input("End date", value=today + timedelta(days=9), min_value=today)

        group_heading("Travellers and costs")
        c1, c2, c3, c4 = st.columns(4)
        travelers = c1.number_input("Travellers", min_value=1, max_value=8, value=2)
        flight_preference = c2.selectbox("Flight preference", ["Cheapest", "Fastest"])
        daily_expense = c3.number_input("Food and local per day (₹)", min_value=0,
                                        value=DEFAULT_DAILY_EXPENSE, step=100)
        budget_limit = c4.number_input("Total budget (₹, 0 = no limit)", min_value=0, value=0, step=1000)

        group_heading("Hotel")
        c1, c2, c3 = st.columns([1, 1, 2])
        min_stars = c1.select_slider("Minimum stars", options=[1, 2, 3, 4, 5], value=3)
        max_hotel_price = c2.slider("Max price per night (₹)", 1000, 7000, 7000, step=250)
        amenities = c3.multiselect("Amenities", AMENITY_OPTIONS, placeholder="Any")

        group_heading("Interests")
        c1, c2 = st.columns(2)
        interests = c1.multiselect("Attraction types", available_place_types(), placeholder="Any type")
        notes = c2.text_area("Anything else? (used by the AI agent)", height=68,
                             placeholder="e.g. I prefer a quiet stay and want at least one beach day.")

        submitted = st.form_submit_button("Plan my trip")

    params = {
        "origin": origin, "destination": destination, "start_date": start_date, "end_date": end_date,
        "travelers": int(travelers), "flight_preference": flight_preference.lower(),
        "min_stars": int(min_stars), "max_hotel_price": int(max_hotel_price),
        "interests": interests, "amenities": amenities, "daily_expense": int(daily_expense),
        "budget_limit": int(budget_limit), "notes": notes.strip(),
    }
    return params, submitted


def validate(params: dict) -> str | None:
    """Return an error message, or None if the inputs are valid."""
    if params["origin"] == params["destination"]:
        return "Choose different cities for 'From' and 'To'."
    if params["end_date"] < params["start_date"]:
        return "The end date must be on or after the start date."
    days, _ = trip_length(params["start_date"], params["end_date"])
    if not MIN_TRIP_DAYS <= days <= MAX_TRIP_DAYS:
        return f"Trips must be {MIN_TRIP_DAYS} to {MAX_TRIP_DAYS} days long (you chose {days})."
    return None


# --------------------------------------------------------------------------- #
# Plan generation
# --------------------------------------------------------------------------- #
def generate(params: dict, settings: dict) -> dict:
    """Create the plan with the AI agent, falling back to the quick planner."""
    started = time.perf_counter()
    result = None
    if settings["mode"] == "agent":
        try:
            from agent import run_agent  # lazy import so Quick mode needs no LLM packages

            output = run_agent(params, settings["provider"], settings["api_key"], settings["model"])
            if output["plan"]:
                result = {"plan": output["plan"], "trace": output["trace"], "source": "AI agent",
                          "warning": None}
            else:
                warning = "The AI answer could not be read as a structured plan, so the quick planner was used."
        except Exception as error:  # noqa: BLE001 - show any provider/network error to the user
            warning = f"The AI agent could not finish ({str(error)[:200]}). The quick planner was used instead."
        if result is None:
            result = {"plan": build_plan(params), "trace": [], "source": "Quick plan", "warning": warning}
    else:
        result = {"plan": build_plan(params), "trace": [], "source": "Quick plan", "warning": None}
    result["seconds"] = time.perf_counter() - started
    return result


# --------------------------------------------------------------------------- #
# Result sections
# --------------------------------------------------------------------------- #
def render_summary(plan: dict) -> None:
    summary, budget = plan.get("trip_summary") or {}, plan.get("budget") or {}
    over = budget.get("within_budget") is False
    note_class = "banner-total-note over" if over else "banner-total-note"
    meta = (f"{short_date(summary.get('start_date'))} to {short_date(summary.get('end_date'))}"
            f" | {summary.get('days')} days, {summary.get('nights')} nights"
            f" | {summary.get('travelers')} traveller(s)")
    show_html(f"""
    <div class="banner">
      <div>
        <div class="banner-title">{esc(trip_title(summary))}</div>
        <div class="banner-route">{esc(summary.get('origin'))} <span>to</span> {esc(summary.get('destination'))}</div>
        <div class="banner-meta">{esc(meta)}</div>
        <div class="banner-text">{esc(summary.get('overview'))}</div>
      </div>
      <div class="banner-total">
        <div class="banner-total-label">Estimated total</div>
        <div class="banner-total-value">{inr(budget.get('total'))}</div>
        <div class="{note_class}">{esc(budget.get('note'))}</div>
      </div>
    </div>""")


def render_key_facts(plan: dict) -> None:
    summary = plan.get("trip_summary") or {}
    flight = plan.get("flight") or {}
    hotel = plan.get("hotel") or {}
    facts = [
        ("Duration", f"{summary.get('days')} days", f"{summary.get('nights')} nights"),
        ("Travellers", str(summary.get("travelers")), "two share a room"),
        ("Flights per person", inr(flight.get("total_price_per_person")), "round trip"),
        ("Hotel per night", inr(hotel.get("price_per_night")),
         f"{hotel.get('stars')}-star" if hotel else "no hotel found"),
    ]
    for column, (label, value, sub) in zip(st.columns(4), facts):
        with column:
            show_html(f'<div class="tile"><div class="tile-label">{esc(label)}</div>'
                      f'<div class="tile-value">{esc(value)}</div><div class="tile-sub">{esc(sub)}</div></div>')


def route_html(label: str, route: dict | None) -> str:
    if not route:
        return f'<div class="route-head">{esc(label)}</div><div class="muted">No flight found in the dataset.</div>'
    stops = int(to_number(route.get("stops")))
    stop_text = "Direct" if not stops else f"{stops} stop{'s' if stops > 1 else ''}"
    legs = "".join(
        f'<div class="leg"><span class="pill">{esc(leg.get("airline"))}</span>'
        f'<b>{esc(leg.get("from"))}</b> to <b>{esc(leg.get("to"))}</b><br>'
        f'<span class="muted">Departs {esc(leg.get("departure_time"))}, arrives {esc(leg.get("arrival_time"))}'
        f' | {inr(leg.get("price"))}</span></div>'
        for leg in route.get("legs", [])
    )
    when = f" on {esc(short_date(route.get('date')))}" if route.get("date") else ""
    return (f'<div class="route-head">{esc(label)}{when} | {stop_text}, '
            f'{esc(route.get("total_duration_hours"))} h flying | {inr(route.get("total_price"))}</div>{legs}')


def render_flight_and_hotel(plan: dict) -> None:
    flight, hotel = plan.get("flight") or {}, plan.get("hotel")
    left, right = st.columns(2)

    with left:
        show_html(f"""
        <div class="card"><div class="card-title">Flights</div>
        {route_html('Outbound', flight.get('outbound'))}
        {route_html('Return', flight.get('return'))}
        <div class="muted" style="margin-top:.6rem">{esc(flight.get('reason'))}</div></div>""")

    with right:
        if hotel:
            stars = int(to_number(hotel.get("stars")))
            chips = "".join(f'<span class="chip">{esc(a)}</span>' for a in hotel.get("amenities", []))
            budget = plan.get("budget") or {}
            stay = f"{budget.get('nights')} nights, {budget.get('rooms', 1)} room(s)"
            show_html(f"""
            <div class="card"><div class="card-title">Where you will stay</div>
            <div class="hotel-name">{esc(hotel.get('name'))}</div>
            <div class="stars">{'★' * stars}{'☆' * (5 - stars)}</div>
            <div class="hotel-price">{inr(hotel.get('price_per_night'))} per night
              <span class="muted">| {esc(stay)}</span></div>
            <div>{chips}</div>
            <div class="muted" style="margin-top:.5rem">{esc(hotel.get('reason'))}</div></div>""")
        else:
            show_html('<div class="card"><div class="card-title">Where you will stay</div>'
                      '<div class="muted">No hotel found for these filters.</div></div>')


def render_weather(plan: dict) -> None:
    days = plan.get("weather") or []
    if not days:
        return
    st.markdown('<div class="section-title">Weather during your trip</div>', unsafe_allow_html=True)
    for column, day in zip(st.columns(min(len(days), 7)), days):
        with column:
            show_html(f"""
            <div class="wx"><div class="wx-date">{esc(short_date(day.get('date')))}</div>
            <div class="wx-icon">{weather_icon(day.get('condition'))}</div>
            <div class="wx-temp">{temperature(day.get('temp_max'))}
              <span class="wx-low">{temperature(day.get('temp_min'))}</span></div>
            <div class="wx-cond">{esc(day.get('condition'))}</div>
            <div class="wx-rain">{esc(day.get('rain_info'))}</div></div>""")
    if plan.get("data_note"):
        st.caption(plan["data_note"])


def render_itinerary(plan: dict) -> None:
    days = plan.get("itinerary") or []
    if not days:
        st.info("No itinerary was generated.")
        return
    for day in days:
        show_html(f"""
        <div class="day-head"><span class="day-badge">Day {esc(day.get('day'))}</span>
        <span class="day-name">{esc(day.get('title'))}</span>
        <span class="day-date">{esc(short_date(day.get('date')))}</span></div>""")
        for activity in day.get("activities", []):
            rating = activity.get("rating")
            rating_html = f' <span class="rating">★ {esc(rating)}</span>' if rating is not None else ""
            kind = str(activity.get("type", "")).title()
            note = f" | {esc(activity.get('note'))}" if activity.get("note") else ""
            show_html(f"""
            <div class="act"><div class="act-time">{esc(activity.get('time_of_day'))}</div>
            <div><div class="act-name">{esc(activity.get('place'))}{rating_html}</div>
            <div class="act-meta">{esc(kind)}{note}</div></div></div>""")


def render_budget(plan: dict) -> None:
    budget = plan.get("budget") or {}
    hotel = plan.get("hotel") or {}
    flight = plan.get("flight") or {}
    travelers = max(int(to_number(budget.get("travelers"), 1)), 1)
    nights = int(to_number(budget.get("nights")))
    days = int(to_number(budget.get("days"), nights + 1)) or 1
    rooms = int(to_number(budget.get("rooms"), 1))
    daily = to_number(budget.get("food_and_local")) / (days * travelers)

    rows = [
        ("Flights", to_number(budget.get("flights")), "#12263A",
         f"{inr(flight.get('total_price_per_person'))} per person x {travelers} traveller(s)"),
        ("Hotel", to_number(budget.get("hotel")), "#0E7C86",
         f"{inr(hotel.get('price_per_night'))} x {nights} nights x {rooms} room(s)"),
        ("Food and local travel", to_number(budget.get("food_and_local")), "#D98E04",
         f"{inr(daily)} per person per day x {days} days x {travelers} traveller(s)"),
    ]
    total = sum(value for _, value, _, _ in rows) or 1

    bar = "".join(f'<div style="width:{value / total * 100:.1f}%;background:{color}"></div>'
                  for _, value, color, _ in rows)
    legend = "".join(f'<span class="dot" style="background:{color}"></span>{esc(label)} {value / total * 100:.0f}%'
                     for label, value, color, _ in rows)
    show_html(f'<div class="split">{bar}</div><div class="legend">{legend}</div>')

    lines = "".join(
        f'<div class="cost-row"><div><div class="cost-what">{esc(label)}</div>'
        f'<div class="cost-how">{esc(how)}</div></div><div class="cost-amt">{inr(value)}</div></div>'
        for label, value, _, how in rows
    )
    show_html(f'{lines}<div class="cost-total"><span>Total cost</span><span>{inr(budget.get("total"))}</span></div>')
    if budget.get("note"):
        st.caption(budget["note"])


def render_report(plan: dict) -> None:
    """Trip report in the format given in the project brief, plus downloads."""
    st.caption("Human-readable version of your plan. Use the copy icon at the top right of the box.")
    st.code(report_text(plan), language="text")
    left, right, _ = st.columns([1, 1, 3])
    left.download_button("Download report (.txt)", plan_to_text(plan),
                         file_name="trip_itinerary.txt", mime="text/plain")
    right.download_button("Download JSON", json.dumps(plan, indent=2, ensure_ascii=False),
                          file_name="trip_plan.json", mime="application/json")


def render_reasoning(plan: dict, result: dict) -> None:
    reasoning = plan.get("reasoning") or []
    st.markdown("#### Why we selected this")
    if reasoning:
        for reason in reasoning:
            st.markdown(f"- {reason}")
    else:
        st.caption("No reasoning was returned.")
    if result["trace"]:
        with st.expander("Agent steps (tools the AI called)"):
            for step in result["trace"]:
                prefix = "Called" if step["type"] == "call" else "Returned"
                st.markdown(f"**{prefix} `{step['tool']}`**")
                st.code(step["detail"], language="json")
    with st.expander("Raw JSON output"):
        st.json(plan)


def render_result(result: dict) -> None:
    plan = result["plan"]
    if result.get("warning"):
        st.warning(result["warning"])

    overview, itinerary, budget, report, why = st.tabs(
        ["Overview", "Itinerary", "Budget", "Trip report", "Why this plan"])
    with overview:
        render_summary(plan)
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        render_key_facts(plan)
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        render_flight_and_hotel(plan)
        render_weather(plan)
    with itinerary:
        render_itinerary(plan)
    with budget:
        st.markdown('<div class="section-title" style="margin-top:1rem">Budget breakdown</div>',
                    unsafe_allow_html=True)
        render_budget(plan)
    with report:
        render_report(plan)
    with why:
        render_reasoning(plan, result)

    st.caption(f"Generated by: {result['source']} in {result.get('seconds', 0):.1f} s. Flight schedules and "
               "prices come from the sample dataset and are indicative.")


def render_empty_state() -> None:
    blocks = [("Your data, used properly", "Flights, hotels and attractions are read from your JSON datasets."),
              ("Live weather", "Day-by-day forecasts from Open-Meteo, with typical weather for later dates."),
              ("Choices explained", "Every pick comes with the reason behind it, so you can trust the plan.")]
    for column, (title, text) in zip(st.columns(3), blocks):
        with column:
            show_html(f'<div class="info"><b>{title}</b><span class="muted">{text}</span></div>')


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    settings = render_sidebar()

    st.markdown('<div class="brandbar"><div class="brand"><div class="brand-mark">✈</div>Wayfinder</div>'
                '<div class="brand-tag">AI travel planner</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-title">Plan your next trip in a minute</div>'
                '<div class="hero-sub">Tell us where you are going. Our AI agent finds flights and a hotel, '
                'checks the weather, builds your day-wise itinerary and totals the cost.</div>',
                unsafe_allow_html=True)

    try:
        params, submitted = render_form()
    except FileNotFoundError as error:
        st.error(str(error))
        st.stop()

    if submitted:
        problem = validate(params)
        if problem:
            st.error(problem)
        else:
            spinner_text = ("The AI agent is searching flights, hotels, places and weather..."
                            if settings["mode"] == "agent" else "Building your plan...")
            with st.spinner(spinner_text):
                st.session_state["result"] = generate(params, settings)

    st.markdown("<div style='height:1.4rem'></div>", unsafe_allow_html=True)
    if "result" in st.session_state:
        render_result(st.session_state["result"])
    else:
        render_empty_state()


main()
