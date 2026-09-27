"""Step 5 (Gemini: analyze result): data -> answer text, trends, comparison, chart choice."""

import json
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


ABSOLUTE_METRICS = {"temperature", "water_temperature", "humidity"}


class ChartChoice(BaseModel):
    type: Literal["line", "bar"] = Field(description="line for values over time, bar for comparing averages")
    title: str
    y_label: str = Field(description="Axis label including the unit, e.g. 'PM2.5 (µg/m³)'")


class Analysis(BaseModel):
    answer_text: str = Field(description="2-4 plain sentences answering the question. Shown in the UI and read "
                                         "aloud, so no markdown, bullet points or emoji. Write numbers as digits, not words. Include the key numbers with units.")
    trends: list[str] = Field(default_factory=list, description="1-3 short observations about changes over time")
    comparison: str | None = Field(None, description="One sentence comparing recent vs historical or between "
                                                     "locations, if the data supports it")
    chart: ChartChoice


INSTRUCTIONS = """You are Ecuery, an environmental data assistant. Answer the user's question using ONLY the
data provided (series summaries, sampled points and historical baselines). Never invent numbers. If the data is
empty or doesn't cover the question, say so plainly. Round to one decimal place. Mention dates in a natural way
("June 7, 2023", "over the last three days"). For PM2.5, values above 35 µg/m³ are unhealthy for sensitive groups
and above 55 are unhealthy for everyone; say so when relevant.
When "comparisons_to_history" is present, the question is about what is normal: always state the recent
average, the historical baseline and the change: a percent for pollutants and river flow, but for
temperature and humidity the absolute difference (e.g. "2.1 °C warmer than usual"), never a percent.
plan.data_notes says where the data comes from. Mention it in a short clause when it changes the meaning
(for example that CO2 is a global Mauna Loa measurement, not the city's). If a series has no points, say that
data isn't available for that period rather than guessing."""


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
    comparisons = []
    for b in baselines:
        current = next((s for s in series if s["metric"] == b["metric"] and s["location"] == b["location"]), None)
        if current and current["summary"] and b["baseline_avg"]:
            recent = current["summary"]["avg"]
            absolute = b["metric"] in ABSOLUTE_METRICS  # a percent of °C or of %RH means nothing
            comparisons.append({"metric": b["metric"], "location": b["location"], "unit": b["unit"],
                                "recent_avg": recent, "baseline_avg": b["baseline_avg"],
                                "difference": round(recent - b["baseline_avg"], 1),
                                "change_pct": None if absolute else round((recent - b["baseline_avg"]) / b["baseline_avg"] * 100, 1),
                                "baseline_years": [y["year"] for y in b["by_year"]]})
    if comparisons:
        payload["comparisons_to_history"] = comparisons
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
    result = response.parsed or Analysis.model_validate_json(response.text)

    # Safety net: a "vs usual" answer must state the baseline. The model occasionally skips it,
    # so add the sentence from the real numbers rather than show an answer that dodges the question.
    for c in comparisons:
        b, text = c["baseline_avg"], result.answer_text
        # Count it as stated if the baseline (allowing either rounding) or the change appears.
        change = abs(c["change_pct"]) if c["change_pct"] is not None else abs(c["difference"])
        mentioned = {f"{b:.1f}", f"{b + 0.05:.1f}", f"{b - 0.05:.1f}", f"{change:.1f}"}
        if not any(m in text for m in mentioned):
            years = f"{min(c['baseline_years'])}–{max(c['baseline_years'])}"
            if c["change_pct"] is None:
                word = ("warmer" if c["difference"] > 0 else "cooler") if "temperature" in c["metric"] else \
                       ("higher" if c["difference"] > 0 else "lower")
                result.answer_text += (f" That is {abs(c['difference']):.1f} {c['unit']} {word} than the {years} average "
                                       f"of {b:.1f} {c['unit']} for the same dates.")
            else:
                word = "higher" if c["change_pct"] > 0 else "lower"
                result.answer_text += (f" That is {change}% {word} than the {years} average "
                                       f"of {b:.1f} {c['unit']} for the same dates.")
    return result
