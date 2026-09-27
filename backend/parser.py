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

from tiger.sample_data import LOCATIONS, METRICS

Metric = Literal["pm25", "o3", "no2", "co2", "temperature", "humidity"]
Operation = Literal["latest", "summary", "trend", "peak", "compare_history", "compare_locations"]

METRIC_HINTS = {
    "pm25": "fine particulate matter PM2.5, smoke, haze, soot, 'air quality' / AQI in general",
    "o3": "ozone, smog",
    "no2": "nitrogen dioxide, traffic / vehicle exhaust pollution",
    "co2": "carbon dioxide, CO2 levels",
    "temperature": "temperature, heat, cold, weather",
    "humidity": "humidity, moisture",
}


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
    metrics = "\n".join(f"- {code} ({METRICS[code][0]}): {hint}" for code, hint in METRIC_HINTS.items())
    return f"""You turn environmental questions into a structured query for a database of sensor readings.
Today is {today.isoformat()} ({today.strftime('%A')}). Resolve relative dates ("last 3 days", "this week",
"since 2019", "June 2023") into ISO start_date / end_date. "Since X" ends today. "This week" is the last 7 days.
If no time is mentioned, leave both dates empty.

Allowed metric codes:
{metrics}

Locations with data: {', '.join(sorted(LOCATIONS))}. Write any location in lowercase snake_case even if it is
not in that list. Map "NYC"/"New York City" to new_york and "Philly" to philadelphia.
Only set clarification_question when the metric or location truly can't be inferred."""


def parse_query(client: genai.Client, question: str, today: date | None = None,
                model: str = "gemini-3.5-flash-lite") -> EnvironmentalQuery:
    today = today or datetime.now(timezone.utc).date()
    response = client.models.generate_content(
        model=model,
        contents=question,
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
