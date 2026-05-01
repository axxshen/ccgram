"""Edge TTS helpers for voice replies.

Converts assistant text into synthesized audio bytes using edge-tts.
Provides utility helpers for cleaning message parts before synthesis.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from edge_tts import Communicate
from edge_tts.exceptions import (
    NoAudioReceived,
    UnexpectedResponse,
    UnknownResponse,
    WebSocketError,
)
import structlog

from .config import config
from .entity_formatting import convert_to_entities

logger = structlog.get_logger()

_PAGINATION_RE = re.compile(r"\n\n\[\d+/\d+\]$")
_USER_PREFIX = "\U0001f464 "
_DEFAULT_TTS_FILENAME = "reply.mp3"

TTS_ERRORS = (
    NoAudioReceived,
    UnexpectedResponse,
    UnknownResponse,
    WebSocketError,
    RuntimeError,
    ValueError,
    OSError,
)


@dataclass(frozen=True, slots=True)
class TtsAudio:
    """Synthesized TTS audio payload."""

    data: bytes
    filename: str = _DEFAULT_TTS_FILENAME


def prepare_tts_text(parts: Iterable[str]) -> str:
    """Merge message parts into a clean, plain-text string for TTS."""
    cleaned_parts: list[str] = []
    for part in parts:
        cleaned = _PAGINATION_RE.sub("", part).strip()
        if cleaned:
            cleaned_parts.append(cleaned)
    combined = "\n".join(cleaned_parts)
    if combined.startswith(_USER_PREFIX):
        combined = combined[len(_USER_PREFIX) :]
    plain_text, _entities = convert_to_entities(combined)
    return plain_text.strip()


async def synthesize_speech(text: str) -> TtsAudio:
    """Synthesize speech from plain text using Edge TTS."""
    if not text.strip():
        msg = "Cannot synthesize empty text"
        raise ValueError(msg)
    voice = config.tts_voice or "en-US-EmmaMultilingualNeural"
    communicate = Communicate(text, voice=voice)
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            data = chunk.get("data")
            if isinstance(data, (bytes, bytearray)):
                audio.extend(data)
            else:
                logger.warning("Unexpected audio chunk payload type: %s", type(data))
    if not audio:
        msg = "No audio bytes received from Edge TTS"
        raise RuntimeError(msg)
    return TtsAudio(data=bytes(audio))
