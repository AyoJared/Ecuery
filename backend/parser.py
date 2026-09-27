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

from shared.catalog import METRICS

Metric = Literal["pm25", "o3", "no2", "co2", "temperature", "humidity", "streamflow", "water_temperature",
                 "precipitation", "dust", "burned_area", "global_temperature", "arctic_sea_ice", "antarctic_sea_ice",
                 "sea_level"]
assert set(Metric.__args__) == set(METRICS), "keep Metric in sync with shared/catalog.py"
Operation = Literal["latest", "summary", "trend", "peak", "compare_history", "compare_locations", "count", "list",
                    "forecast"]
EventType = Literal["tornado", "hail", "thunderstorm_wind", "flood", "hurricane", "winter_storm", "heat", "wildfire",
                    "drought", "earthquake", "volcano", "landslide", "severe_storm"]


class EnvironmentalQuery(BaseModel):
    # Basic request
    intent: str = Field(description="Short snake_case label for what the user wants, e.g. check_air_quality")
    topics: list[str] = []
    locations: list[str] = Field(
        default_factory=list,
        description="Places as proper names with country/state when known, e.g. 'Delhi, India'. Empty if none mentioned.")
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
                    "peak = when was it highest/worst (or the biggest event); compare_history = vs normal / usual / "
                    "previous years; compare_locations = between places; count = how many events; list = which events; "
                    "forecast = anything about the future (will it, next week, tomorrow, in 2040, chance of)")

    # Natural disasters and other events (instead of metrics)
    event_types: list[EventType] = Field(
        default_factory=list,
        description="Disasters / events the question is about (tornadoes, earthquakes, wildfires, hurricanes, ...). "
                    "Use this instead of metrics for event questions.")
    radius_km: float | None = Field(None, description="Only if the user gives a distance ('within 100 miles'), in km.")
    min_magnitude: float | None = Field(
        None, description="Only if the user gives a threshold: earthquake magnitude ('M6+'), tornado EF rating "
                          "('EF3 or stronger' -> 3), hail size in inches, hurricane wind in knots "
                          "('Category 4+' -> 113, 'major hurricanes' -> 96).")
    basin: str | None = Field(
        None, description="Ocean basin for tropical cyclone questions, e.g. 'North Atlantic', 'Western Pacific', "
                          "'Eastern Pacific', 'North Indian Ocean', 'South Pacific'. Not a location.")
    event_name: str | None = Field(
        None, description="A named event, e.g. 'Katrina' for Hurricane Katrina, 'Haiyan' for Typhoon Haiyan.")
    rank_by: Literal["magnitude", "intensification", "duration", "deaths", "damage"] | None = Field(
        None, description="What 'biggest/worst' means: magnitude (strongest, default); intensification (fastest "
                          "strengthening / rapid intensification); duration (longest-lived); deaths (deadliest); "
                          "damage (costliest).")

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

    unsupported_topic: str | None = Field(
        None, description="If the question is about something outside the allowed metrics and event types "
                          "(e.g. 'glaciers', 'coral bleaching', 'bird migration'), "
                          "name it here in a few words; otherwise leave empty.")

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

Locations: any place on Earth. Write each as its proper name, adding the country (or US state) when the user
gives it or it's needed to disambiguate, e.g. "Delhi, India", "Paris, France", "Paris, Texas", "Lagos, Nigeria".
Expand nicknames ("NYC" -> "New York City", "Philly" -> "Philadelphia", "LA" -> "Los Angeles").
Keep a location key from an earlier turn (like delhi_in or new_york) exactly as given.
CO2 concentration is only measured globally (NOAA Mauna Loa): for CO2-only questions no place is needed.

Events: questions about natural disasters or weather events (tornadoes, earthquakes, wildfires, hurricanes /
tropical storms / typhoons, floods, hail, damaging wind, blizzards / winter storms, heat waves, droughts, volcanic
eruptions, landslides) set event_types and leave metrics empty. "How many" -> operation count; "which / list" ->
list; "biggest / strongest / worst" -> peak. A place is optional for events ("biggest earthquakes in 2025").
If no time is given for an event question, leave the dates empty, except for "ever" / "on record" / "since
records began" / trend questions ("are hurricanes getting stronger", "each year"): set start_date to 1850-01-01.
Tropical cyclones (hurricanes, typhoons, cyclones) are event type hurricane worldwide. An ocean basin ("Western
Pacific typhoons", "Atlantic hurricanes") goes in basin, not locations. A named storm ("Hurricane Katrina") goes in
event_name with its year as the dates, if known. "Deadliest" -> rank_by deaths; "costliest" -> damage; "fastest
intensifying" / "rapid intensification" -> intensification; "longest-lasting" -> duration.

Future: questions about what WILL happen ("will it rain", "forecast", "tomorrow", "next week", "this weekend",
"next summer", "in 2040", "chance of a tornado next year") set operation to forecast and resolve the dates forward
from today: tomorrow = the next day; next week = the next 7 days; this weekend = the coming Saturday-Sunday;
next summer = June 1-August 31 of the next summer; "in 2040" = 2040-01-01 to 2040-12-31. "Hot" / "cold" / "weather"
map to temperature. "Rain" or "snow" are not available: if that's all they ask about, set clarification_question.
If the question is about a topic none of the metric codes or event types cover, set unsupported_topic to that
topic (e.g. "glaciers", "coral bleaching") and do not force it onto an unrelated metric.
"How much rain/snow" is metric precipitation even when a storm is named; for a named storm, set the location to
the place it hit hardest if you know it (e.g. Storm Daniel 2023 -> "Derna, Libya") and the dates of the storm.
"Each year", "how often", "per year", "per decade" or "how fast is X changing" with no dates means the whole record:
set start_date to 1850-01-01 and operation to trend.
Comparing specific periods with each other ("2023 vs 2024") is operation summary covering both periods;
compare_history is only for "vs usual / normal / average / past years".
"On record" / "ever" / "all time" means the whole record: set start_date to 1850-01-01 (it is clipped to the
earliest data available). Drought, dry spells and monsoons are precipitation questions (use metric precipitation,
yearly), not events, unless the user asks about specific drought events or declarations.
Only set clarification_question when the metric/event or location truly can't be inferred.

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
