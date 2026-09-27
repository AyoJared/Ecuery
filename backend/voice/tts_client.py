"""Step 7a/7c: send answer text to ElevenLabs and stream audio chunks back.

ElevenLabsClient calls the real streaming endpoint when ELEVENLABS_API_KEY is
set. Otherwise MockTTSClient streams a generated chime (WAV) so the whole
speak -> stream -> play path can be demoed without a key.
"""

import io
import math
import os
import struct
import wave
from typing import Iterator, Protocol

import httpx

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
CHUNK_SIZE = 4096


class TTSClient(Protocol):
    mode: str
    media_type: str

    def stream(self, text: str, voice_id: str) -> Iterator[bytes]: ...


class ElevenLabsClient:
    mode = "elevenlabs"
    media_type = "audio/mpeg"

    def __init__(self, api_key: str, model_id: str = "eleven_flash_v2_5"):
        self.api_key = api_key
        self.model_id = model_id

    def stream(self, text: str, voice_id: str) -> Iterator[bytes]:
        with httpx.stream(
            "POST",
            f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}/stream",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": self.api_key, "accept": "audio/mpeg"},
            json={"text": text, "model_id": self.model_id},
            timeout=30,
        ) as resp:
            resp.raise_for_status()
            yield from resp.iter_bytes(CHUNK_SIZE)


class MockTTSClient:
    mode = "mock"
    media_type = "audio/wav"
    sample_rate = 22050

    def stream(self, text: str, voice_id: str) -> Iterator[bytes]:
        audio = self._chime(seconds=min(0.6 + len(text) / 200, 3.0))
        for i in range(0, len(audio), CHUNK_SIZE):
            yield audio[i:i + CHUNK_SIZE]

    def _chime(self, seconds: float) -> bytes:
        n = int(self.sample_rate * seconds)
        frames = bytearray()
        for i in range(n):
            t = i / self.sample_rate
            freq = 523.25 if t < seconds / 2 else 659.25  # C5 then E5
            fade = min(1.0, (n - i) / (self.sample_rate * 0.05), i / (self.sample_rate * 0.01))
            frames += struct.pack("<h", int(0.3 * 32767 * fade * math.sin(2 * math.pi * freq * t)))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            w.writeframes(bytes(frames))
        return buf.getvalue()


_client: TTSClient | None = None


def get_client() -> TTSClient:
    global _client
    if _client is None:
        key = os.getenv("ELEVENLABS_API_KEY")
        _client = ElevenLabsClient(key) if key else MockTTSClient()
    return _client
