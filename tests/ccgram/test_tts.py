import pytest

from ccgram.config import config
from ccgram.tts import TtsAudio, prepare_tts_text, synthesize_speech


def test_prepare_tts_text_strips_markdown_and_pagination():
    parts = ("Hello **world**\n\n[1/2]", "More _text_\n\n[2/2]")
    assert prepare_tts_text(parts) == "Hello world\nMore text"


@pytest.mark.asyncio
async def test_synthesize_speech_collects_audio(monkeypatch):
    class DummyCommunicate:
        def __init__(self, text, voice):
            self.text = text
            self.voice = voice

        async def stream(self):
            yield {"type": "audio", "data": b"hello"}
            yield {"type": "audio", "data": b"world"}

    monkeypatch.setattr("ccgram.tts.Communicate", DummyCommunicate)
    original_voice = config.tts_voice
    config.tts_voice = "en-US-TestVoice"
    try:
        result = await synthesize_speech("Hello world")
    finally:
        config.tts_voice = original_voice
    assert result == TtsAudio(data=b"helloworld")


@pytest.mark.asyncio
async def test_synthesize_speech_rejects_empty_text():
    with pytest.raises(ValueError):
        await synthesize_speech("   ")
