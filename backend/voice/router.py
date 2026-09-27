"""Step 7 API: turn answer text into streamed speech.

GET  /voice/voices  available voices + whether we're live or mocked
POST /voice/speak   {text, voice} -> streamed audio
GET  /voice/speak   ?text=&voice= -> streamed audio (works as <audio src=...>)
POST /voice/converse  multipart: audio=<recording>, voice, conversation_id -> Research Assistant turn:
                      transcript + short spoken reply + speech_url (+ the full answer card when answered)
"""

import itertools

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field

from ask.router import gemini_error
from ask.transcribe import MAX_AUDIO_BYTES, SUPPORTED, normalize_mime
from shared.series import DataUnavailable

from .assistant import converse
from .tts_client import TTSClient, get_client
from .voices import DEFAULT_VOICE, VOICES, resolve_voice

router = APIRouter(prefix="/voice", tags=["voice"])

MAX_CHARS = 2500

# Tell OpenAPI/Swagger these routes return audio, not JSON, so /docs plays them.
AUDIO_RESPONSE = {
    200: {
        "content": {"audio/mpeg": {}, "audio/wav": {}},
        "description": "Streamed speech (mp3 from ElevenLabs, wav in mock mode)",
    }
}


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_CHARS)
    voice: str = DEFAULT_VOICE


@router.get("/voices")
def list_voices(client: TTSClient = Depends(get_client)):
    return {
        "mode": client.mode,
        "default": DEFAULT_VOICE,
        "voices": [{"key": v.key, "name": v.name, "description": v.description} for v in VOICES.values()],
    }


@router.post("/speak", response_class=StreamingResponse, responses=AUDIO_RESPONSE)
def speak(req: SpeakRequest, client: TTSClient = Depends(get_client)):
    return _stream_speech(req.text, req.voice, client)


@router.get("/speak", response_class=StreamingResponse, responses=AUDIO_RESPONSE)
def speak_get(
    text: str = Query(min_length=1, max_length=MAX_CHARS),
    voice: str = DEFAULT_VOICE,
    client: TTSClient = Depends(get_client),
):
    return _stream_speech(text, voice, client)


@router.post("/converse")
def converse_turn(audio: UploadFile = File(..., description="Recorded speech: webm, ogg, wav, mp3, m4a, ..."),
                  voice: str = Form(DEFAULT_VOICE), conversation_id: str | None = Form(None)):
    if resolve_voice(voice) is None:
        raise HTTPException(400, f"Unknown voice '{voice}'. Options: {', '.join(VOICES)}")
    mime = normalize_mime(audio.content_type)
    if mime is None:
        raise HTTPException(415, f"Unsupported audio type '{audio.content_type}'. Use one of: {', '.join(sorted(SUPPORTED))}")
    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise HTTPException(400, "The recording is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Recording is too long; keep questions under a minute.")
    try:
        return converse(data, mime, voice, conversation_id)
    except DataUnavailable as e:
        raise HTTPException(503, str(e))
    except genai_errors.APIError as e:
        raise gemini_error(e)


def _stream_speech(text: str, voice_key: str, client: TTSClient) -> StreamingResponse:
    voice = resolve_voice(voice_key)
    if voice is None:
        raise HTTPException(400, f"Unknown voice '{voice_key}'. Options: {', '.join(VOICES)}")

    chunks = client.stream(text, voice.voice_id)
    # Pull the first chunk now so upstream errors become a proper HTTP error
    # instead of a silently empty audio stream.
    try:
        first = next(chunks, b"")
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"ElevenLabs error {e.response.status_code}")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Could not reach ElevenLabs: {e}")

    return StreamingResponse(
        itertools.chain([first], chunks),
        media_type=client.media_type,
        headers={"X-Voice-Mode": client.mode, "X-Voice": voice.key},
    )
