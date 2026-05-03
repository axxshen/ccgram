"""TTS subpackage — text-to-speech synthesis providers.

Public re-exports and shared text-preparation utility.
"""

from __future__ import annotations

import re
from typing import Iterable

from .base import SpeechSynthesizer, TtsAudio, TtsSynthesisError

_PAGINATION_RE = re.compile(r"\n\n\[\d+/\d+\]$")
_USER_PREFIX = "\U0001f464 "


def prepare_tts_text(parts: Iterable[str]) -> str:
    """Merge message parts into a clean, plain-text string for TTS."""
    # Lazy: avoids pulling in Telegram at import time
    from ccgram.entity_formatting import convert_to_entities

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


__all__ = [
    "SpeechSynthesizer",
    "TtsAudio",
    "TtsSynthesisError",
    "prepare_tts_text",
]
