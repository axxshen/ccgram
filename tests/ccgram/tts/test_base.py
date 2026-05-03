import pytest
from ccgram.tts.base import TtsAudio, TtsSynthesisError, prepare_tts_text


def test_prepare_tts_strips_pagination():
    parts = ("Hello **world**\n\n[1/2]", "More _text_\n\n[2/2]")
    assert prepare_tts_text(parts) == "Hello world\nMore text"


def test_prepare_tts_strips_user_prefix():
    parts = ("\U0001f464 Hello there",)
    assert prepare_tts_text(parts) == "Hello there"


def test_prepare_tts_skips_empty_parts():
    parts = ("", "   ", "hello")
    assert prepare_tts_text(parts) == "hello"


def test_prepare_tts_returns_empty_for_all_blank():
    assert prepare_tts_text(("", "  ")) == ""


def test_tts_audio_frozen():
    audio = TtsAudio(data=b"abc")
    with pytest.raises(Exception):
        audio.data = b"xyz"  # type: ignore[misc]


def test_tts_audio_default_filename():
    audio = TtsAudio(data=b"abc")
    assert audio.filename == "reply.mp3"


def test_tts_synthesis_error_is_exception():
    err = TtsSynthesisError("boom")
    assert isinstance(err, Exception)
    assert str(err) == "boom"
