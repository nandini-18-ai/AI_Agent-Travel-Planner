"""LangChain tool-calling travel agent.

Two stages (this works reliably on free models such as Groq's):
  1. The agent decides which tools to call (flights, hotels, places, weather,
     budget) and collects the data.
  2. A final model call, with no tools attached, turns the collected data into
     the structured JSON plan that the Streamlit UI renders.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import core
from config import LLM_PROVIDERS, get_secret
from planner import trip_length
from tools import ALL_TOOLS

MAX_TOOL_ATTEMPTS = 3

AGENT_PROMPT = """You are an expert travel planner agent for Indian domestic trips.

Collect the data needed for the trip by calling the tools:
1. flight_search_tool for the OUTBOUND route, and again for the RETURN route (swap the cities).
2. hotel_recommendation_tool for the destination, using the traveller's star, price and amenity limits.
3. weather_lookup_tool for the destination and the exact trip dates.
4. places_discovery_tool for the destination, first with the traveller's interests as place_types. If that returns fewer places than the trip needs (2 per day), call it a second time with an empty place_types to get the best-rated places of any type.
5. budget_estimation_tool with: flight total per person (outbound total_price + return total_price; if no return flight exists reuse the outbound price), the chosen hotel price per night, nights, travellers, daily expense and the budget limit.

Rules:
- Use ONLY data returned by the tools. Never invent flights, hotels, places, prices, temperatures or ratings.
- Pass tool arguments as plain strings and numbers only (for example place_types "temple,beach").
- When all tool calls are finished, reply with one short plain sentence such as "All data collected." Do not write the itinerary and do not write any JSON.
"""

COMPOSE_PROMPT = """You turn collected travel data into a final trip plan.

You receive the traveller's request and the results of the tools that were called.

Rules:
- Use ONLY the tool results provided. Never invent flights, hotels, places, prices, temperatures or ratings. Copy values exactly.
- Choose the first (selected) flight option for each direction and the selected hotel, unless the request says otherwise.
- Build a day-wise itinerary: 2 attractions per day (fewer if the city has few places), best rated first, no place repeated. Put places matching the traveller's interests first, then fill remaining slots with the best-rated other places so that every day has at least one activity whenever unused places exist. Use time_of_day values Morning / Afternoon / Evening.
- If a tool result has a note (relaxed filters, connecting flights, estimated weather), mention it in "reasoning".
- Explain every key decision briefly in "reasoning" (why this flight, why this hotel, how the itinerary was built).
- Reply with ONLY one valid JSON object. No markdown, no code fences, no text before or after.

JSON schema:
{
  "trip_summary": {"title": str, "origin": str, "destination": str, "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "days": int, "nights": int, "travelers": int, "overview": str},
  "flight": {"outbound": ROUTE or null, "return": ROUTE or null, "total_price_per_person": number, "reason": str},
  "hotel": {"name": str, "city": str, "stars": int, "price_per_night": number, "amenities": [str], "reason": str} or null,
  "weather": [{"date": "YYYY-MM-DD", "condition": str, "temp_max": number, "temp_min": number, "rain_info": str}],
  "itinerary": [{"day": int, "date": "YYYY-MM-DD", "title": str, "activities": [{"time_of_day": str, "place": str, "type": str, "rating": number, "note": str}]}],
  "budget": {"flights": number, "hotel": number, "food_and_local": number, "total": number, "rooms": int, "travelers": int, "nights": int, "days": int, "budget_limit": number or null, "within_budget": bool or null, "note": str},
  "reasoning": [str],
  "data_note": str
}
ROUTE = {"date": "YYYY-MM-DD", "stops": int, "total_price": number, "total_duration_hours": number, "legs": [{"airline": str, "from": str, "to": str, "departure_time": "HH:MM", "arrival_time": "HH:MM", "price": number}]}
"""


# --------------------------------------------------------------------------- #
# LLM factory
# --------------------------------------------------------------------------- #
def get_llm(provider_name: str, api_key: str | None = None, model: str | None = None):
    """Create a chat model for the chosen provider."""
    provider = LLM_PROVIDERS[provider_name]
    key = api_key or get_secret(provider["env_key"])
    if not key:
        raise ValueError(f"No API key found. Set {provider['env_key']} in .env or Streamlit Secrets.")
    model_name = model or provider["default_model"]

    if provider["id"] == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=key, temperature=0.2, max_retries=3)
    if provider["id"] == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model_name, api_key=key, temperature=0.2, max_retries=3)
    if provider["id"] == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model_name, api_key=key, temperature=0.2, max_retries=3)
    raise ValueError(f"Unsupported provider: {provider_name}")


def build_agent(llm):
    """Create the tool-calling agent (LangChain 1.x ``create_agent``)."""
    from langchain.agents import create_agent

    return create_agent(model=llm, tools=ALL_TOOLS, system_prompt=AGENT_PROMPT)


# --------------------------------------------------------------------------- #
# Prompt, parsing and trace helpers
# --------------------------------------------------------------------------- #
def build_user_prompt(params: dict[str, Any]) -> str:
    """Turn the form values into the request the agent receives."""
    days, nights = trip_length(params["start_date"], params["end_date"])
    lines = [
        f"Plan a {days}-day trip from {params['origin']} to {params['destination']}.",
        f"Dates: {params['start_date'].isoformat()} to {params['end_date'].isoformat()} "
        f"({days} days, {nights} nights).",
        f"Travellers: {params['travelers']}.",
        f"Flight preference: {params['flight_preference']}.",
        f"Hotel: minimum {params['min_stars']} stars"
        + (f", maximum ₹{params['max_hotel_price']} per night." if params.get("max_hotel_price") else "."),
        f"Interests (place types): {', '.join(params['interests']) if params.get('interests') else 'any'}.",
        f"Daily food and local travel expense per person: ₹{params['daily_expense']}.",
        f"Total budget limit: ₹{params['budget_limit']}." if params.get("budget_limit")
        else "No total budget limit.",
    ]
    if params.get("amenities"):
        lines.append(f"Required hotel amenities: {', '.join(params['amenities'])}.")
    if params.get("notes"):
        lines.append(f"Extra requests from the traveller: {params['notes']}")
    return "\n".join(lines)


def _message_text(content: Any) -> str:
    """Flatten model output (string or list of content blocks) into text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


def extract_json(text: str) -> dict[str, Any] | None:
    """Parse the JSON object from the model's final answer."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _build_trace(messages: list) -> list[dict[str, str]]:
    """List the tool calls the agent made (shown in the UI as 'Agent steps')."""
    trace = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            trace.append({"type": "call", "tool": call["name"],
                          "detail": json.dumps(call.get("args", {}), ensure_ascii=False)})
        if message.__class__.__name__ == "ToolMessage":
            text = _message_text(message.content)
            trace.append({"type": "result", "tool": getattr(message, "name", "tool"),
                          "detail": text[:600] + ("..." if len(text) > 600 else "")})
    return trace


def _collect_tool_results(messages: list) -> str:
    """Join every tool call (with its arguments) and result into one text block."""
    arguments: dict[str, str] = {}
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            arguments[call.get("id", "")] = json.dumps(call.get("args", {}), ensure_ascii=False)

    sections = []
    for message in messages:
        if message.__class__.__name__ == "ToolMessage":
            name = getattr(message, "name", "tool")
            args = arguments.get(getattr(message, "tool_call_id", ""), "")
            sections.append(f"### {name}({args})\n{_message_text(message.content)}")
    return "\n\n".join(sections)


def fill_empty_days(plan: dict[str, Any], destination: str) -> dict[str, Any]:
    """Give empty itinerary days the best-rated places the AI left unused.

    Models sometimes keep only places that match the interests and leave days
    blank. This keeps the plan complete without changing the AI's own picks.
    """
    days = plan.get("itinerary")
    if not isinstance(days, list):
        return plan
    used = {str(a.get("place")) for d in days for a in d.get("activities", [])}
    pool = [p for p in core.discover_places(destination, 0, None, 50)["places"]
            if p["name"] not in used]
    filled = False
    for day in days:
        if day.get("activities") or not pool:
            continue
        place = pool.pop(0)
        day["activities"] = [{
            "time_of_day": "Morning", "place": place["name"], "type": place["type"],
            "rating": place["rating"], "note": "Best-rated remaining attraction in the city.",
        }]
        filled = True
    if filled:
        plan.setdefault("reasoning", []).append(
            "Days with no matching attraction were filled with the best-rated remaining places.")
    return plan


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def run_agent(params: dict[str, Any], provider_name: str, api_key: str | None = None,
              model: str | None = None) -> dict[str, Any]:
    """Run the agent and return ``{"plan", "raw", "trace"}``.

    ``plan`` is None when the model's answer could not be parsed as JSON; the
    UI then shows ``raw`` instead.
    """
    llm = get_llm(provider_name, api_key, model)
    request = build_user_prompt(params)

    # Stage 1: the agent calls the tools. Small free models sometimes produce a malformed
    # tool call (Groq error "tool_use_failed"), so that specific error is retried.
    agent = build_agent(llm)
    messages = None
    for attempt in range(1, MAX_TOOL_ATTEMPTS + 1):
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": request}]},
                config={"recursion_limit": 30},
            )
            messages = result["messages"]
            break
        except Exception as error:  # noqa: BLE001 - re-raised unless it is the known tool-call glitch
            retryable = "tool_use_failed" in str(error) or "Failed to parse tool call" in str(error)
            if not retryable or attempt == MAX_TOOL_ATTEMPTS:
                raise
            time.sleep(1)
    facts = _collect_tool_results(messages)
    if not facts:
        raise ValueError("The AI did not call any tools.")

    # Stage 2: compose the structured plan (no tools attached).
    reply = llm.invoke([
        ("system", COMPOSE_PROMPT),
        ("human", f"REQUEST:\n{request}\n\nTOOL RESULTS:\n{facts}"),
    ])
    raw_text = _message_text(reply.content)
    plan = extract_json(raw_text)
    if plan:
        plan = fill_empty_days(plan, params["destination"])
    return {"plan": plan, "raw": raw_text, "trace": _build_trace(messages)}
