import pytest

from ccgram.config import config
from ccgram.tts import TtsAudio, prepare_tts_text, synthesize_speech


def test_prepare_tts_text_strips_markdown_and_pagination():
    parts = ("Hello **world**\n\n[1/2]", "More _text_\n\n[2/2]")
    assert prepare_tts_text(parts) == "Hello world\nMore text"


async def test_synthesize_speech_collects_audio(monkeypatch):
    class DummyCommunicate:
        def __init__(self, text, voice):
            self.text = text
            self.voice = voice

        async def stream(self):
            yield {"type": "audio", "data": b"hello"}
            yield {"type": "audio", "data": b"world"}

    monkeypatch.setattr("ccgram.tts.Communicate", DummyCommunicate)
    monkeypatch.setattr(config, "tts_voice", "en-US-TestVoice")
    result = await synthesize_speech("Hello world")
    assert result == TtsAudio(data=b"helloworld")


async def test_synthesize_speech_rejects_empty_text():
    with pytest.raises(ValueError):
        await synthesize_speech("   ")
