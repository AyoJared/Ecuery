"""Ask a question in plain English, get the full answer card.

POST /ask         {"question": "...", "voice": "rachel"} -> answer card (or a clarification request)
POST /ask/parse   {"question": "..."} -> just Gemini's structured understanding (for debugging)
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field

from parser import parse_query
from shared.series import DataUnavailable

from .pipeline import MODEL, ask, get_gemini

router = APIRouter(prefix="/ask", tags=["ask"])

DEMO_PAGE = Path(__file__).with_name("demo.html")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    voice: str = "rachel"


@router.post("")
def ask_question(req: AskRequest):
    try:
        return ask(req.question, req.voice)
    except DataUnavailable as e:
        raise HTTPException(503, str(e))
    except genai_errors.APIError as e:
        raise HTTPException(502, f"Gemini error {e.code}: {e.message}")


@router.get("/demo", response_class=HTMLResponse, include_in_schema=False)
def demo():
    """Test page: ask a question, hear the answer, see the chart and Solana badge."""
    return DEMO_PAGE.read_text(encoding="utf-8")


@router.post("/parse")
def parse_only(req: AskRequest):
    try:
        return parse_query(get_gemini(), req.question, model=MODEL).model_dump(exclude_none=True)
    except DataUnavailable as e:
        raise HTTPException(503, str(e))
    except genai_errors.APIError as e:
        raise HTTPException(502, f"Gemini error {e.code}: {e.message}")
