"""Step 5 (Gemini: analyze result): data -> answer text, trends, comparison, chart choice."""

import json
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


class ChartChoice(BaseModel):
    type: Literal["line", "bar"] = Field(description="line for values over time, bar for comparing averages")
    title: str
    y_label: str = Field(description="Axis label including the unit, e.g. 'PM2.5 (µg/m³)'")


class Analysis(BaseModel):
    answer_text: str = Field(description="2-4 plain sentences answering the question. Shown in the UI and read "
                                         "aloud, so no markdown, bullet points or emoji. Include the key numbers with units.")
    trends: list[str] = Field(default_factory=list, description="1-3 short observations about changes over time")
    comparison: str | None = Field(None, description="One sentence comparing recent vs historical or between "
                                                     "locations, if the data supports it")
    chart: ChartChoice


INSTRUCTIONS = """You are Ecuery, an environmental data assistant. Answer the user's question using ONLY the
data provided (series summaries, sampled points and historical baselines). Never invent numbers. If the data is
empty or doesn't cover the question, say so plainly. Round to one decimal place. Mention dates in a natural way
("June 7, 2023", "over the last three days"). For PM2.5, values above 35 µg/m³ are unhealthy for sensitive groups
and above 55 are unhealthy for everyone; say so when relevant."""


def _sample(points: list[dict], limit: int = 48) -> list[dict]:
    step = max(1, len(points) // limit)
    picked = points[::step]
    if points and picked[-1] is not points[-1]:
        picked.append(points[-1])
    return [{"time": p["time"], "avg": p["avg"], "max": p["max"]} for p in picked]


def analyze(client: genai.Client, model: str, question: str, plan: dict, series: list[dict],
            baselines: list[dict]) -> Analysis:
    payload = {
        "question": question,
        "plan": plan,
        "series": [
            {k: s[k] for k in ("metric", "location", "unit", "route", "granularity", "start", "end", "summary")}
            | {"points": _sample(s["points"])}
            for s in series
        ],
        "historical_baselines": baselines,
    }
    response = client.models.generate_content(
        model=model,
        contents=json.dumps(payload, ensure_ascii=False),
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCTIONS,
            response_mime_type="application/json",
            response_schema=Analysis,
            temperature=0.2,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    return response.parsed or Analysis.model_validate_json(response.text)
