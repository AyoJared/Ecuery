from pydantic import BaseModel
from google import genai


class EnvironmentalQuery(BaseModel):
    # Basic request
    intent: str
    topics: list[str] = []
    locations: list[str] = []
    geographic_level: str | None = None

    # Measurements
    metrics: list[str] = []
    start_date: str | None = None
    end_date: str | None = None
    operation: str | None = None

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

    clarification_question: str | None = None

def parse_query(client: genai.Client, question: str) -> EnvironmentalQuery:

  response = client.models.generate_content(
    model="gemini-3.5-flash-lite",
      contents=question,
      config={
          "response_mime_type": "application/json",
          "response_schema": EnvironmentalQuery,
      },
  )

  return response.parsed