"""Research Assistant mode: a spoken back-and-forth on top of the normal ask pipeline.

A recorded question goes through ask_voice (transcribe -> answer card, same conversation memory
as typed follow-ups). The card's answer_text is written to be read, so for speech we rewrite it
into a short conversational reply, and every turn -- clarifications included -- gets audio.
"""

import re
from urllib.parse import urlencode

from google.genai import types

from ask.pipeline import MODEL, ask_voice, get_gemini
from shared.source_links import with_source_links

# Spoken replies stay short: long answers are tiring to listen to, and the full card is on screen.
MAX_SPOKEN_WORDS = 70

SPOKEN_PROMPT = """You are Ecuery's research assistant, answering out loud in a voice conversation.
Rewrite the written answer below as a spoken reply.

Rules:
- One to three short, conversational sentences, at most {max_words} words.
- Lead with the direct answer to the question.
- Use only facts and numbers from the written answer. Never add or change a number.
- Write numbers as digits, rounded the way a person would say them ("about 4.3 million", not "4.28"
  or "four point three million"). The reply is shown on screen as well as spoken.
- Write units as words ("micrograms per cubic meter", "degrees Fahrenheit", "parts per million").
- Plain text only: no markdown, lists, symbols or URLs.

Question: {question}

Written answer:
{answer}"""


def spoken_reply(question: str, answer_text: str) -> str:
    """A short spoken version of answer_text. Falls back to its first sentences if Gemini fails."""
    try:
        response = get_gemini().models.generate_content(
            model=MODEL,
            contents=SPOKEN_PROMPT.format(max_words=MAX_SPOKEN_WORDS, question=question, answer=answer_text),
            config=types.GenerateContentConfig(
                temperature=0.3,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        text = (response.text or "").strip()
        if text:
            return text
    except Exception:  # Speech is a nicety on top of the answer; never fail the turn over it.
        pass
    return first_sentences(answer_text)


def first_sentences(text: str, limit: int = 2) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sentences[:limit])


def speech_url(text: str, voice: str) -> str:
    return "/voice/speak?" + urlencode({"text": text, "voice": voice})


def converse(audio: bytes, mime_type: str, voice: str, conversation_id: str | None) -> dict:
    """One spoken turn: what was heard, what to say back, and the full answer card when there is one."""
    card = with_source_links(ask_voice(audio, mime_type, voice, conversation_id))
    transcript = card.get("transcript", "")

    if card.get("status") == "answered":
        reply = spoken_reply(transcript, card["answer_text"])
        answer = card
    else:
        reply = card.get("clarification") or "Sorry, I couldn't answer that. Could you ask it another way?"
        answer = None

    return {
        "status": card.get("status"),
        "conversation_id": card["conversation_id"],
        "transcript": transcript,
        "reply": reply,
        "speech_url": speech_url(reply, voice),
        "answer": answer,
    }
