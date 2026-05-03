"""Base types for TTS synthesis providers.

Defines the Protocol, result types, and shared text-preparation utilities
that all SpeechSynthesizer implementations must follow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Protocol


class TtsSynthesisError(Exception):
    """Raised by any SpeechSynthesizer when synthesis fails in a known way."""


@dataclass(frozen=True, slots=True)
class TtsAudio:
    """Synthesized TTS audio payload."""

    data: bytes
    filename: str = "reply.mp3"


class SpeechSynthesizer(Protocol):
    """Protocol for TTS synthesis backends."""

    async def synthesize(self, text: str) -> TtsAudio:
        """Synthesize speech from plain text, returning audio bytes.

        Raises TtsSynthesisError on known backend failures.
        """
        ...


_PAGINATION_RE = re.compile(r"\n\n\[\d+/\d+\]$")
_USER_PREFIX = "\U0001f464 "


def prepare_tts_text(parts: Iterable[str]) -> str:
    """Merge message parts into a clean, plain-text string for TTS."""
    # Lazy: avoid importing telegram at module load time in a foundational module
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
