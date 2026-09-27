"""Step 2 (Gemini: understand question): natural language -> structured query.

Extracts the metric, location and time range the rest of the flow routes on.
Metrics are limited to what Tiger/Snowflake store, locations come back in the
same snake_case the databases use, and dates are resolved to ISO against
today's date so "last 3 days" or "this week" can be routed by time range.
"""

from datetime import date, datetime, timezone
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from shared.catalog import CITIES, METRICS

Metric = Literal["pm25", "o3", "no2", "co2", "temperature", "humidity", "streamflow", "water_temperature"]
assert set(Metric.__args__) == set(METRICS), "keep Metric in sync with shared/catalog.py"
Operation = Literal["latest", "summary", "trend", "peak", "compare_history", "compare_locations"]


class EnvironmentalQuery(BaseModel):
    # Basic request
    intent: str = Field(description="Short snake_case label for what the user wants, e.g. check_air_quality")
    topics: list[str] = []
    locations: list[str] = Field(
        default_factory=list,
        description="Cities as lowercase snake_case, e.g. philadelphia, new_york. Empty if none mentioned.")
    geographic_level: str | None = None

    # Measurements
    metrics: list[Metric] = Field(
        default_factory=list,
        description="Measured quantities the question is about, using only the allowed codes.")
    start_date: str | None = Field(None, description="ISO date YYYY-MM-DD for the start of the period, resolved from today's date")
    end_date: str | None = Field(None, description="ISO date YYYY-MM-DD for the end of the period (inclusive)")
    operation: Operation | None = Field(
        None,
        description="latest = current value; summary = how was it; trend = how it changed over time; "
                    "peak = when was it highest/worst; compare_history = vs normal / usual / previous years; "
                    "compare_locations = between cities")

    # Actions and decisions
    proposed_action: str | None = None
    desired_outcomes: list[str] = []
    constraints: list[str] = []
    selection_criteria: list[str] = []

    # Explanations and hypotheticals
    cause: str | None = None
    scenario: str | None = None
    forecast_horizon: str | None = None

    # People, organizations, participation
    entity_type: str | None = None
    activity: str | None = None
    audience: str | None = None

    clarification_question: str | None = Field(
        None, description="Only if the question is too vague to answer: what to ask the user.")


def _instructions(today: date) -> str:
    metrics = "\n".join(f"- {m.code} ({m.unit}): {m.hint}" for m in METRICS.values())
    return f"""You turn environmental questions into a structured query for a database of sensor readings.
Today is {today.isoformat()} ({today.strftime('%A')}). Resolve relative dates ("last 3 days", "this week",
"since 2019", "June 2023") into ISO start_date / end_date. "Since X" ends today. "This week" is the last 7 days.
If no time is mentioned, leave both dates empty.

Allowed metric codes:
{metrics}

Locations with data: {', '.join(sorted(CITIES))}. Write any location in lowercase snake_case even if it is
not in that list. Map "NYC"/"New York City" to new_york and "Philly" to philadelphia.
CO2 concentration is only measured globally (NOAA Mauna Loa): for CO2-only questions no city is needed.
Only set clarification_question when the metric or location truly can't be inferred.

Follow-ups: if earlier turns of the conversation are given, the new question may depend on them
("what about Philadelphia?", "and last month?", "is that normal?", or just "Philadelphia" answering
a clarification). Carry over the metric, location and time range from the most recent turn unless
the new question replaces them, and set operation from the new question."""


def _with_history(question: str, history: list[dict] | None) -> str:
    if not history:
        return question
    lines = ["Earlier in this conversation (oldest first):"]
    for i, turn in enumerate(history, 1):
        understood = ", ".join(f"{k}={v}" for k, v in (turn.get("understood") or {}).items())
        lines.append(f"{i}. User: {turn['question']}\n   Understood: {understood or 'nothing'}"
                     f"\n   Reply: {turn.get('reply', '')[:200]}")
    return "\n".join(lines) + f"\n\nNew question: {question}"


def parse_query(client: genai.Client, question: str, today: date | None = None,
                model: str = "gemini-3.5-flash-lite", history: list[dict] | None = None) -> EnvironmentalQuery:
    today = today or datetime.now(timezone.utc).date()
    response = client.models.generate_content(
        model=model,
        contents=_with_history(question, history),
        config=types.GenerateContentConfig(
            system_instruction=_instructions(today),
            response_mime_type="application/json",
            response_schema=EnvironmentalQuery,
            temperature=0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    if response.parsed is None:
        return EnvironmentalQuery.model_validate_json(response.text)
    return response.parsed
