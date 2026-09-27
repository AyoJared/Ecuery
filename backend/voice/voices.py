"""Step 7b: the voices users can pick from (ElevenLabs premade voice IDs)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Voice:
    key: str
    name: str
    voice_id: str
    description: str


VOICES: dict[str, Voice] = {
    v.key: v
    for v in [
        Voice("rachel", "Rachel", "21m00Tcm4TlvDq8ikWAM", "Calm, clear narrator"),
        Voice("adam", "Adam", "pNInz6obpgDQGcFmaJgB", "Deep, steady"),
        Voice("bella", "Bella", "EXAVITQu4vr4xnSDxMaL", "Soft, friendly"),
        Voice("antoni", "Antoni", "ErXwobaYiN019PkySvjV", "Warm, conversational"),
    ]
}

DEFAULT_VOICE = "rachel"


def resolve_voice(key: str | None) -> Voice | None:
    return VOICES.get((key or DEFAULT_VOICE).lower())
