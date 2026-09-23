import json
from types import SimpleNamespace

import httpx
import pytest

from app.agent.service import InvestigationRuntime
from app.core.config import settings
from app.llm.base import PlanOutput, PlannedTask, ProviderError, ProviderState, ToolDecision
from app.llm.client import OmniOpsLLMClient
from app.llm.gemini_provider import GeminiProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.openai_provider import OpenAIProvider


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, *, posts=None, get=None):
        self.posts = iter(posts or [])
        self.get_response = get
        self.payloads = []
        self.post_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, _url, json):
        self.post_calls += 1
        self.payloads.append(json)
        response = next(self.posts)
        if isinstance(response, BaseException):
            raise response
        return response

    async def get(self, _url):
        if isinstance(self.get_response, BaseException):
            raise self.get_response
        return self.get_response


def chat_response(content):
    return FakeResponse(payload={"message": {"role": "assistant", "content": content}, "done": True})


@pytest.mark.asyncio
async def test_ollama_structured_planning_uses_schema_and_validates(monkeypatch):
    client = FakeClient(posts=[chat_response(json.dumps({
        "reasoning_summary": "Retrieve the uploaded source.",
        "tasks": [{
            "id": "TASK-1",
            "title": "Retrieve facts",
            "description": "Find the key facts in the source.",
            "target_modality": "document",
            "expected_output": "Cited source facts",
        }],
    }))])
    monkeypatch.setattr("app.llm.ollama_provider.httpx.AsyncClient", lambda **_kwargs: client)

    output = await OllamaProvider("http://ollama:11434", "qwen3:4b").generate_investigation_plan(
        "Summarize the source.", {"documents": [{"name": "facts.txt"}]},
    )

    assert output.tasks[0].id == "TASK-1"
    assert client.payloads[0]["model"] == "qwen3:4b"
    assert client.payloads[0]["stream"] is False
    assert client.payloads[0]["format"]["title"] == "PlanOutput"


@pytest.mark.asyncio
async def test_ollama_structured_synthesis_validates_contract(monkeypatch):
    evidence_id = "6dba7862-2181-45e3-ad0f-ec1716888c1d"
    client = FakeClient(posts=[chat_response(json.dumps({
        "executive_summary": "The source reports 42 units.",
        "key_findings": [{"title": "Measured result", "detail": "42 units", "claim_id": "CLM-001"}],
        "claims": [{
            "claim_id": "CLM-001",
            "statement": "The source reports 42 units.",
            "epistemic_type": "fact",
            "confidence_score": 0.9,
            "citations": [evidence_id],
            "calculation_ids": [],
            "supporting_claims": [],
        }],
        "inferences": [],
        "recommendations": [],
        "missing_data_warnings": [],
        "contradictions": [],
    }))])
    monkeypatch.setattr("app.llm.ollama_provider.httpx.AsyncClient", lambda **_kwargs: client)

    output = await OllamaProvider("http://ollama:11434", "qwen3:4b").verify_and_synthesize(
        "Summarize.", [], [{"id": evidence_id, "exact_quote": "42 units"}], [],
    )

    assert output.claims[0].citations == [evidence_id]
    assert client.payloads[0]["format"]["title"] == "SynthesisReport"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (httpx.ConnectError("offline"), "PROVIDER_UNAVAILABLE"),
        (httpx.ReadTimeout("slow"), "PROVIDER_TIMEOUT"),
        (FakeResponse(404), "PROVIDER_MODEL_UNAVAILABLE"),
        (chat_response("not json"), "PROVIDER_RESPONSE_INVALID"),
        (chat_response('{"reasoning_summary":"missing tasks"}'), "PROVIDER_RESPONSE_INVALID"),
        (chat_response('{"reasoning_summary":"empty plan","tasks":[]}'), "PROVIDER_RESPONSE_INVALID"),
    ],
)
async def test_ollama_failures_are_explicit(monkeypatch, response, expected_code):
    responses = [response, response] if isinstance(response, httpx.ConnectError) else [response]
    client = FakeClient(posts=responses)
    monkeypatch.setattr("app.llm.ollama_provider.httpx.AsyncClient", lambda **_kwargs: client)

    async def no_wait(_delay):
        return None

    monkeypatch.setattr("app.llm.ollama_provider.asyncio.sleep", no_wait)
    with pytest.raises(ProviderError) as raised:
        await OllamaProvider("http://ollama:11434", "qwen3:4b").generate_investigation_plan("objective", {})
    assert raised.value.code == expected_code


@pytest.mark.asyncio
async def test_ollama_readiness_requires_configured_model(monkeypatch):
    missing = FakeClient(get=FakeResponse(payload={"models": [{"name": "gemma3:1b"}]}))
    monkeypatch.setattr("app.llm.ollama_provider.httpx.AsyncClient", lambda **_kwargs: missing)
    provider = OllamaProvider("http://ollama:11434", "qwen3:4b")
    assert (await provider.readiness())["code"] == "PROVIDER_MODEL_UNAVAILABLE"

    ready = FakeClient(get=FakeResponse(payload={"models": [{"name": "qwen3:4b"}]}))
    monkeypatch.setattr("app.llm.ollama_provider.httpx.AsyncClient", lambda **_kwargs: ready)
    assert (await provider.readiness())["status"] == "ready"


def test_provider_selection_is_explicit_and_has_no_fallback(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "qwen3:4b")
    assert isinstance(OmniOpsLLMClient()._provider, OllamaProvider)

    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "configured-test-key")
    assert isinstance(OmniOpsLLMClient()._provider, GeminiProvider)

    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "configured-test-key")
    assert isinstance(OmniOpsLLMClient()._provider, OpenAIProvider)

    monkeypatch.setattr(settings, "LLM_PROVIDER", "")
    with pytest.raises(ProviderError) as raised:
        OmniOpsLLMClient()
    assert raised.value.code == "LLM_PROVIDER_REQUIRED"

    monkeypatch.setattr(settings, "LLM_PROVIDER", "auto")
    with pytest.raises(ProviderError) as raised:
        OmniOpsLLMClient()
    assert raised.value.code == "LLM_PROVIDER_REQUIRED"


@pytest.mark.asyncio
async def test_ollama_failure_does_not_fall_back_to_gemini(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "qwen3:4b")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "configured-but-must-not-be-used")
    client = FakeClient(posts=[httpx.ConnectError("offline"), httpx.ConnectError("offline")])
    monkeypatch.setattr("app.llm.ollama_provider.httpx.AsyncClient", lambda **_kwargs: client)

    async def no_wait(_delay):
        return None

    monkeypatch.setattr("app.llm.ollama_provider.asyncio.sleep", no_wait)
    llm = OmniOpsLLMClient()
    with pytest.raises(ProviderError) as raised:
        await llm.generate_investigation_plan("objective", {})
    assert raised.value.code == "PROVIDER_UNAVAILABLE"
    assert isinstance(llm._provider, OllamaProvider)


@pytest.mark.asyncio
async def test_gemini_failure_does_not_fall_back_to_ollama(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "configured-test-key")
    llm = OmniOpsLLMClient()

    async def unavailable(*_args, **_kwargs):
        raise ProviderError(ProviderState.RATE_LIMITED, "PROVIDER_RATE_LIMITED", "quota unavailable")

    monkeypatch.setattr(llm._provider, "generate_investigation_plan", unavailable)
    with pytest.raises(ProviderError) as raised:
        await llm.generate_investigation_plan("objective", {})
    assert raised.value.code == "PROVIDER_RATE_LIMITED"
    assert isinstance(llm._provider, GeminiProvider)


@pytest.mark.asyncio
async def test_readiness_endpoint_reports_provider_failure(client, monkeypatch):
    # ``settings`` is instantiated during test collection, so patch the
    # existing singleton rather than mutating an environment variable that the
    # application will not re-read. The endpoint must reach readiness on an
    # explicitly configured provider, not the no-provider failure path.
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "missing-model")

    async def unavailable(_self):
        return {
            "status": "unavailable",
            "provider": "ollama",
            "model": "missing-model",
            "code": "PROVIDER_MODEL_UNAVAILABLE",
        }

    monkeypatch.setattr("app.llm.client.OmniOpsLLMClient.readiness", unavailable)
    response = await client.get("/api/v1/readiness")
    assert response.status_code == 503
    provider = response.json()["data"]["checks"]["llm_provider"]
    assert provider["provider"] == "ollama"
    assert provider["code"] == "PROVIDER_MODEL_UNAVAILABLE"


@pytest.mark.asyncio
async def test_provider_calls_renew_worker_lease(monkeypatch):
    calls = []

    async def fake_renew(_db, investigation, worker_id):
        calls.append((investigation.id, worker_id))
        return True

    monkeypatch.setattr("app.agent.service.renew_lease", fake_renew)
    db = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
    runtime = InvestigationRuntime(db)
    investigation = SimpleNamespace(id="investigation-id")

    await runtime._renew_provider_lease(investigation, "worker-1")
    assert calls == [("investigation-id", "worker-1")]
    assert OllamaProvider("http://ollama:11434", "qwen3:4b").timeout_seconds < OllamaProvider.WORKER_LEASE_SECONDS


@pytest.mark.asyncio
async def test_provider_plan_persists_modality_not_unbounded_output_description(monkeypatch):
    class ContractProvider:
        async def generate_investigation_plan(self, _objective, _catalog):
            return PlanOutput(
                reasoning_summary="Retrieve the source.",
                tasks=[PlannedTask(
                    id="task-1",
                    title="Retrieve",
                    description="Retrieve the source facts.",
                    target_modality="document",
                    expected_output="A deliberately verbose description of the expected evidence that exceeds the database type limit.",
                )],
            )

        async def decide_next_action(self, *_args):
            return ToolDecision(
                tool_name="hybrid_document_search",
                arguments={"query": "source facts", "top_k": 5},
                user_activity_summary="Searching the source.",
            )

    db = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))
    runtime = InvestigationRuntime(db, llm_client=ContractProvider())

    async def catalog(_investigation):
        return {"documents": [], "tables": []}

    monkeypatch.setattr(runtime, "_catalog_summary", catalog)
    investigation = SimpleNamespace(id="investigation-id", objective="Summarize.", max_steps=4)

    plan = await runtime._provider_plan(investigation)

    assert plan.steps[0].expected_evidence_type == "document"
    assert len(plan.steps[0].expected_evidence_type) <= 50
