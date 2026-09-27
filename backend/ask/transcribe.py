"""Step 1 -> 2: the recorded question (audio) -> text, via Gemini's audio understanding."""

from google import genai
from google.genai import types
from pydantic import BaseModel

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # Gemini allows 20 MB per request; a spoken question is far smaller

# What browsers send -> what Gemini accepts. Chrome/Edge record webm, Firefox ogg, Safari mp4 (AAC).
MIME_ALIASES = {
    "audio/x-wav": "audio/wav", "audio/wave": "audio/wav", "audio/vnd.wave": "audio/wav",
    "audio/mp4": "audio/m4a", "audio/x-m4a": "audio/m4a", "video/webm": "audio/webm",
    "audio/x-flac": "audio/flac", "audio/mpeg3": "audio/mp3",
}
SUPPORTED = {"audio/wav", "audio/mp3", "audio/mpeg", "audio/aiff", "audio/aac", "audio/ogg", "audio/flac",
             "audio/m4a", "audio/opus", "audio/webm"}


class Transcript(BaseModel):
    text: str


def normalize_mime(content_type: str | None) -> str | None:
    base = (content_type or "").split(";")[0].strip().lower()
    base = MIME_ALIASES.get(base, base)
    return base if base in SUPPORTED else None


def transcribe(client: genai.Client, model: str, audio: bytes, mime_type: str) -> str:
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=audio, mime_type=mime_type),
            "Transcribe the spoken question exactly as said. Return only the words spoken. "
            "If there is no intelligible speech, return an empty string.",
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Transcript,
            temperature=0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    parsed = response.parsed or Transcript.model_validate_json(response.text)
    return parsed.text.strip()
