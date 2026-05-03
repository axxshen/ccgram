"""TTS subpackage — text-to-speech synthesis providers.

Public re-exports, shared text-preparation utility, and provider factory.
"""

from __future__ import annotations

import re
from typing import Iterable

from .base import SpeechSynthesizer, TtsAudio, TtsSynthesisError

_PAGINATION_RE = re.compile(r"\n\n\[\d+/\d+\]$")
_USER_PREFIX = "\U0001f464 "

_PROVIDERS = {"edge": "EdgeTtsSynthesizer"}


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


def get_synthesizer() -> SpeechSynthesizer | None:
    """Return a SpeechSynthesizer based on config, or None if TTS is disabled.

    Returns None if tts_provider is not configured (empty string).
    """
    # Lazy: config singleton resolved by factory call
    from ccgram.config import config

    provider = config.tts_provider
    if not provider:
        return None

    if provider not in _PROVIDERS:
        msg = f"Unknown TTS provider: {provider!r}. Supported: {list(_PROVIDERS)}"
        raise ValueError(msg)

    # Lazy: optional dep, only when provider=edge
    from .edge import EdgeTtsSynthesizer

    return EdgeTtsSynthesizer(voice=config.tts_voice)


__all__ = [
    "SpeechSynthesizer",
    "TtsAudio",
    "TtsSynthesisError",
    "get_synthesizer",
    "prepare_tts_text",
]
