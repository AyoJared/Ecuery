"""Ask a question in plain English, get the full answer card.

POST /ask         {"question": "...", "voice": "rachel"} -> answer card (or a clarification request)
POST /ask/voice   multipart: audio=<recording>, voice=rachel -> transcript + answer card
POST /ask/parse   {"question": "..."} -> just Gemini's structured understanding (for debugging)
GET  /ask/conversation/{id}     earlier turns remembered for follow-ups
DELETE /ask/conversation/{id}   start over
DELETE /ask/cache               drop cached answers/data (e.g. after reseeding the databases)

Send back the conversation_id from a response to ask a follow-up ("what about Philadelphia?").
"""

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field

from parser import parse_query
from shared.series import DataUnavailable

from .pipeline import MODEL, ask, ask_voice, get_gemini
from .cache import get_cache
from .memory import get_store
from .transcribe import MAX_AUDIO_BYTES, SUPPORTED, normalize_mime

router = APIRouter(prefix="/ask", tags=["ask"])

DEMO_PAGE = Path(__file__).with_name("demo.html")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    voice: str = "rachel"
    conversation_id: str | None = Field(None, description="From a previous response, to ask a follow-up")


@router.post("")
def ask_question(req: AskRequest):
    try:
        return ask(req.question, req.voice, req.conversation_id)
    except DataUnavailable as e:
        raise HTTPException(503, str(e))
    except genai_errors.APIError as e:
        raise HTTPException(502, f"Gemini error {e.code}: {e.message}")


@router.post("/voice")
def ask_by_voice(audio: UploadFile = File(..., description="Recorded question: webm, ogg, wav, mp3, m4a, ..."),
                 voice: str = Form("rachel"), conversation_id: str | None = Form(None)):
    mime = normalize_mime(audio.content_type)
    if mime is None:
        raise HTTPException(415, f"Unsupported audio type '{audio.content_type}'. Use one of: {', '.join(sorted(SUPPORTED))}")
    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise HTTPException(400, "The recording is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Recording is too long; keep questions under a minute.")
    try:
        return ask_voice(data, mime, voice, conversation_id)
    except DataUnavailable as e:
        raise HTTPException(503, str(e))
    except genai_errors.APIError as e:
        raise HTTPException(502, f"Gemini error {e.code}: {e.message}")


@router.get("/conversation/{conversation_id}")
def conversation(conversation_id: str):
    store = get_store()
    return {"conversation_id": conversation_id, "memory": store.mode, "turns": store.history(conversation_id)}


@router.delete("/conversation/{conversation_id}")
def reset_conversation(conversation_id: str):
    get_store().clear(conversation_id)
    return {"conversation_id": conversation_id, "cleared": True}


@router.delete("/cache")
def clear_cache():
    cache = get_cache()
    return {"cache": cache.mode, "cleared": cache.clear()}


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
