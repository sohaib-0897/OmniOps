"""Deterministic contract tests for the current Gemini multimodal APIs.

Live provider calls are intentionally kept out of the ordinary backend suite;
the closure script invokes those separately so a transient external provider
outage cannot turn a deterministic regression into a false failure.
"""

from __future__ import annotations

import base64

import pytest

from app.core import config
from app.ingestion.capabilities import CapabilityStatus, GEMINI_MODEL_CAPABILITIES, capability_matrix
from app.llm.base import ProviderError, ProviderState
from app.llm.multimodal import GeminiMultimodalProvider


def test_current_gemini_models_have_explicit_modality_capabilities():
    assert GEMINI_MODEL_CAPABILITIES["gemini-3.8-flash"] == {
        "text": True,
        "image": True,
        "audio_understanding": True,
        "structured_output": True,
    }
    assert GEMINI_MODEL_CAPABILITIES["gemini-3.5-transcribe"] == {
        "audio_transcription": True,
        "word_timestamps": True,
        "speaker_diarization": True,
    }


def test_capability_matrix_uses_dedicated_models(monkeypatch):
    monkeypatch.setattr(config.settings, "GEMINI_API_KEY", "configured-but-not-called")
    monkeypatch.setattr(config.settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(config.settings, "GEMINI_VISION_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(config.settings, "GEMINI_TRANSCRIPTION_MODEL", "gemini-3.5-transcribe")
    matrix = capability_matrix()
    assert matrix["image_semantic_vision"].status == CapabilityStatus.AVAILABLE
    assert matrix["image_semantic_vision"].model == "gemini-3.8-flash"
    assert matrix["audio_transcription"].status == CapabilityStatus.AVAILABLE
    assert matrix["audio_transcription"].model == "gemini-3.5-transcribe"
    assert matrix["audio_timestamps"].status == CapabilityStatus.AVAILABLE
    assert matrix["audio_diarization"].status == CapabilityStatus.AVAILABLE


@pytest.mark.asyncio
async def test_vision_interaction_uses_image_and_structured_response(tmp_path, monkeypatch):
    image = tmp_path / "chart.png"
    image.write_bytes(b"png-fixture")
    provider = GeminiMultimodalProvider("secret-not-printed", "gemini-3.8-flash", "gemini-3.5-transcribe")
    captured = {}

    async def fake_post(payload):
        captured.update(payload)
        return {"output_text": '{"summary":"A bar chart","visual_entities":["bar chart"]}'}

    monkeypatch.setattr(provider, "_post_interaction", fake_post)
    result = await provider.analyze_image(str(image), "image/png")
    assert result.summary == "A bar chart"
    assert captured["model"] == "gemini-3.8-flash"
    assert captured["input"][1]["type"] == "image"
    assert base64.b64decode(captured["input"][1]["data"]) == b"png-fixture"
    assert captured["response_format"]["mime_type"] == "application/json"


@pytest.mark.asyncio
async def test_transcription_request_uses_verbatim_word_timestamps_and_diarization(tmp_path, monkeypatch):
    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"wav-fixture")
    provider = GeminiMultimodalProvider("secret-not-printed", "gemini-3.8-flash", "gemini-3.5-transcribe")
    captured = {}

    async def fake_upload(_path, _mime):
        return "https://generativelanguage.googleapis.com/v1beta/files/audio-fixture"

    async def fake_post(payload):
        captured.update(payload)
        return {
            "id": "interaction-fixture",
            "output_text": "Revenue increased",
            "steps": [{"content": [{"annotations": [
                {"type": "word_info", "text": "Revenue", "start_offset": "0.100s", "end_offset": "0.450s", "speaker": "spk_1"},
                {"type": "word_info", "text": "increased", "start_offset": "0.500s", "end_offset": "0.850s", "speaker": "spk_2"},
            ]}]}],
        }

    monkeypatch.setattr(provider, "_upload_file", fake_upload)
    monkeypatch.setattr(provider, "_post_interaction", fake_post)
    result = await provider.transcribe_audio(str(audio), "audio/wav")
    config_payload = captured["generation_config"]["transcription_config"]["mode"]
    assert captured["model"] == "gemini-3.5-transcribe"
    assert config_payload["type"] == "verbatim"
    assert config_payload["timestamp_granularities"] == ["word"]
    assert config_payload["diarization_mode"] == "speaker"
    assert [(item.start_ms, item.end_ms) for item in result.segments] == [(100, 450), (500, 850)]
    assert [item.speaker for item in result.segments] == ["spk_1", "spk_2"]


def test_transcription_parser_does_not_invent_timestamps_or_speakers():
    result = GeminiMultimodalProvider.parse_transcription_response({
        "output_text": "A sentence without timing annotations",
        "steps": [{"content": [{"annotations": [{"type": "citation", "text": "ignored"}]}]}],
    })
    assert result.transcript == "A sentence without timing annotations"
    assert result.segments == []


def test_gemini_is_preferred_over_openai_for_audio_when_both_are_configured(monkeypatch):
    monkeypatch.setattr(config.settings, "GEMINI_API_KEY", "gemini-configured")
    monkeypatch.setattr(config.settings, "OPENAI_API_KEY", "openai-configured")
    from app.llm.multimodal import configured_gemini_multimodal

    provider = configured_gemini_multimodal()
    assert provider is not None
    assert provider.model == config.settings.GEMINI_VISION_MODEL
    assert provider.transcription_model == config.settings.GEMINI_TRANSCRIPTION_MODEL


@pytest.mark.asyncio
async def test_provider_http_failure_is_typed_and_fail_closed(monkeypatch):
    provider = GeminiMultimodalProvider("secret-not-printed", "gemini-3.8-flash")

    class FakeResponse:
        status_code = 403

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.llm.multimodal.httpx.AsyncClient", lambda **_kwargs: FakeClient())
    with pytest.raises(ProviderError) as raised:
        await provider._post_interaction({"model": "gemini-3.8-flash"})
    assert raised.value.state == ProviderState.AUTHENTICATION_FAILED
    assert raised.value.code == "PROVIDER_AUTH_FAILED"
