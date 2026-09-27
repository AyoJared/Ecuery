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

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field

from parser import parse_query
from shared.series import DataUnavailable
from shared.source_links import with_source_links

from .pipeline import MODEL, ask, ask_voice, get_gemini
from .cache import get_cache
from .memory import get_store
from .transcribe import MAX_AUDIO_BYTES, SUPPORTED, normalize_mime

router = APIRouter(prefix="/ask", tags=["ask"])


def gemini_error(e: genai_errors.APIError) -> HTTPException:
    """A message people can act on, instead of Google's raw error text."""
    if e.code == 429:
        return HTTPException(429, "Ecuery is getting a lot of questions right now. Please try again in about 30 seconds.")
    if e.code in (500, 502, 503, 504):
        return HTTPException(503, "Ecuery's language model is busy right now. Please try again in a moment.")
    return HTTPException(502, f"Ecuery couldn't process that question (Gemini error {e.code}).")

DEMO_PAGE = Path(__file__).with_name("demo.html")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    voice: str = "rachel"
    conversation_id: str | None = Field(None, description="From a previous response, to ask a follow-up")


def upstream_error(e: httpx.HTTPError) -> HTTPException:
    """A data agency (Open-Meteo, NOAA, USGS, ...) was down or rate-limited us even after retries."""
    host = e.request.url.host if getattr(e, "_request", None) is not None else "a data source"
    busy = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
    return HTTPException(503, f"{host} is {'rate-limiting requests' if busy else 'not responding'} right now, "
                              "so the data couldn't be loaded. Please try again in a minute.")


@router.post("")
def ask_question(req: AskRequest):
    try:
        return with_source_links(ask(req.question, req.voice, req.conversation_id))
    except DataUnavailable as e:
        raise HTTPException(503, str(e))
    except genai_errors.APIError as e:
        raise gemini_error(e)
    except httpx.HTTPError as e:
        raise upstream_error(e)


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
        return with_source_links(ask_voice(data, mime, voice, conversation_id))
    except DataUnavailable as e:
        raise HTTPException(503, str(e))
    except genai_errors.APIError as e:
        raise gemini_error(e)
    except httpx.HTTPError as e:
        raise upstream_error(e)


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
        raise gemini_error(e)
