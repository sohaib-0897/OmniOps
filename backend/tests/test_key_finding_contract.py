"""Regression tests for the canonical executive key-finding contract.

The live Ollama E2E produced ``{"title": ..., "statement": ...}`` because
``SynthesisReport.key_findings`` was an unconstrained ``List[Dict[str, Any]]``.
The frontend renders ``detail``, so every key finding displayed an empty body.
These tests pin the contract at the schema level, where the provider is bound.
"""
import json

import pytest
from pydantic import ValidationError

from app.llm.base import KeyFinding, SynthesisReport
from app.llm.ollama_provider import OllamaProvider

from test_ollama_provider import FakeClient, chat_response


EVIDENCE_ID = "6dba7862-2181-45e3-ad0f-ec1716888c1d"


def _synthesis_payload(key_findings):
    return json.dumps({
        "executive_summary": "The source reports 42 units.",
        "key_findings": key_findings,
        "claims": [{
            "claim_id": "CLM-001",
            "statement": "The source reports 42 units.",
            "epistemic_type": "fact",
            "confidence_score": 0.9,
            "citations": [EVIDENCE_ID],
            "calculation_ids": [],
            "supporting_claims": [],
        }],
        "inferences": [],
        "recommendations": [],
        "missing_data_warnings": [],
        "contradictions": [],
    })


def test_provider_schema_constrains_key_finding_field_names():
    """The JSON schema handed to a structured provider must require `detail`."""
    schema = SynthesisReport.model_json_schema()["$defs"]["KeyFinding"]

    assert set(schema["properties"]) == {"title", "detail", "claim_id"}
    assert sorted(schema["required"]) == ["detail", "title"]
    assert "statement" not in schema["properties"]


def test_key_finding_requires_a_body():
    with pytest.raises(ValidationError):
        KeyFinding.model_validate({"title": "Headline only"})


def test_key_finding_normalizes_legacy_statement_body():
    """An unconstrained provider answering `statement` still yields `detail`."""
    finding = KeyFinding.model_validate({"title": "North Hub", "statement": "1,250 orders"})

    assert finding.detail == "1,250 orders"
    assert finding.model_dump() == {"title": "North Hub", "detail": "1,250 orders", "claim_id": None}


@pytest.mark.asyncio
async def test_ollama_synthesis_emits_canonical_key_findings(monkeypatch):
    """Reproduces the live E2E defect: `statement` must not reach the report."""
    client = FakeClient(posts=[chat_response(_synthesis_payload(
        [{"title": "Measured result", "statement": "42 units", "claim_id": "CLM-001"}],
    ))])
    monkeypatch.setattr("app.llm.ollama_provider.httpx.AsyncClient", lambda **_kwargs: client)

    report = await OllamaProvider("http://ollama:11434", "qwen3:4b").verify_and_synthesize(
        "Summarize.", [], [{"id": EVIDENCE_ID, "exact_quote": "42 units"}], [],
    )

    assert report.key_findings[0].detail == "42 units"
    assert report.key_findings[0].model_dump()["detail"] == "42 units"
    # The request itself carried the canonical schema, so a compliant provider
    # is constrained to `detail` rather than relying on this normalization.
    finding_schema = client.payloads[0]["format"]["$defs"]["KeyFinding"]
    assert "detail" in finding_schema["required"]


@pytest.mark.asyncio
async def test_ollama_synthesis_rejects_body_less_key_findings(monkeypatch):
    client = FakeClient(posts=[chat_response(_synthesis_payload([{"title": "Headline only"}]))])
    monkeypatch.setattr("app.llm.ollama_provider.httpx.AsyncClient", lambda **_kwargs: client)

    with pytest.raises(Exception) as excinfo:
        await OllamaProvider("http://ollama:11434", "qwen3:4b").verify_and_synthesize(
            "Summarize.", [], [{"id": EVIDENCE_ID, "exact_quote": "42 units"}], [],
        )

    assert getattr(excinfo.value, "code", None) == "PROVIDER_RESPONSE_INVALID"
