import asyncio

import httpx
import pytest

from app.llm.base import ProviderError, ProviderState
from app.llm.gemini_provider import GeminiProvider


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, *_args, **_kwargs):
        self.calls += 1
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response


def test_gemini_retry_budget_stays_inside_worker_lease():
    assert GeminiProvider.RETRY_BUDGET_SECONDS + GeminiProvider.REQUEST_TIMEOUT_SECONDS < 120
    assert GeminiProvider._retry_delay(FakeResponse(429, headers={"retry-after": "900"}), 0) == 30.0


@pytest.mark.asyncio
async def test_gemini_retries_transient_503_then_returns_structured_output(monkeypatch):
    client = FakeClient([
        FakeResponse(503),
        FakeResponse(503),
        FakeResponse(200, {"output_text": '{"tasks": []}'}),
    ])
    monkeypatch.setattr("app.llm.gemini_provider.httpx.AsyncClient", lambda **_kwargs: client)

    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("app.llm.gemini_provider.asyncio.sleep", fake_sleep)
    provider = GeminiProvider("configured-test-key", "gemini-3.8-flash")

    assert await provider._call_gemini("system", "prompt") == '{"tasks": []}'
    assert client.calls == 3
    assert sleeps == [1, 2]


@pytest.mark.asyncio
async def test_gemini_exhausted_rate_limit_remains_explicit(monkeypatch):
    client = FakeClient([FakeResponse(429) for _ in range(5)])
    monkeypatch.setattr("app.llm.gemini_provider.httpx.AsyncClient", lambda **_kwargs: client)

    async def fake_sleep(_delay):
        return None

    monkeypatch.setattr("app.llm.gemini_provider.asyncio.sleep", fake_sleep)
    provider = GeminiProvider("configured-test-key", "gemini-3.8-flash")

    with pytest.raises(ProviderError) as raised:
        await provider._call_gemini("system", "prompt")
    assert raised.value.state == ProviderState.RATE_LIMITED
    assert raised.value.code == "PROVIDER_RATE_LIMITED"
    assert client.calls == 5


@pytest.mark.asyncio
async def test_gemini_honors_retry_after_and_does_not_retry_daily_quota(monkeypatch):
    client = FakeClient([
        FakeResponse(429, {"error": {"code": "too_many_requests"}}, {"retry-after": "7"}),
        FakeResponse(200, {"output_text": "ok"}),
    ])
    monkeypatch.setattr("app.llm.gemini_provider.httpx.AsyncClient", lambda **_kwargs: client)
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("app.llm.gemini_provider.asyncio.sleep", fake_sleep)
    provider = GeminiProvider("configured-test-key", "gemini-3.8-flash")
    assert await provider._call_gemini("system", "prompt") == "ok"
    assert sleeps == [7.0]

    quota_client = FakeClient([
        FakeResponse(429, {"error": {"code": "quota_exceeded"}}),
    ])
    monkeypatch.setattr("app.llm.gemini_provider.httpx.AsyncClient", lambda **_kwargs: quota_client)
    with pytest.raises(ProviderError) as raised:
        await provider._call_gemini("system", "prompt")
    assert raised.value.code == "PROVIDER_QUOTA_EXCEEDED"
    assert quota_client.calls == 1


@pytest.mark.asyncio
async def test_gemini_authentication_failure_is_not_retried(monkeypatch):
    client = FakeClient([FakeResponse(403)])
    monkeypatch.setattr("app.llm.gemini_provider.httpx.AsyncClient", lambda **_kwargs: client)
    provider = GeminiProvider("configured-test-key", "gemini-3.8-flash")

    with pytest.raises(ProviderError) as raised:
        await provider._call_gemini("system", "prompt")
    assert raised.value.state == ProviderState.AUTHENTICATION_FAILED
    assert raised.value.code == "PROVIDER_AUTH_FAILED"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_gemini_timeout_is_retried_then_remains_explicit(monkeypatch):
    client = FakeClient([httpx.ReadTimeout("timed out") for _ in range(5)])
    monkeypatch.setattr("app.llm.gemini_provider.httpx.AsyncClient", lambda **_kwargs: client)

    async def fake_sleep(_delay):
        return None

    monkeypatch.setattr("app.llm.gemini_provider.asyncio.sleep", fake_sleep)
    provider = GeminiProvider("configured-test-key", "gemini-3.8-flash")

    with pytest.raises(ProviderError) as raised:
        await provider._call_gemini("system", "prompt")
    assert raised.value.state == ProviderState.TIMEOUT
    assert raised.value.code == "PROVIDER_TIMEOUT"
    assert client.calls == 5


@pytest.mark.asyncio
async def test_gemini_malformed_response_is_explicit_and_not_retried(monkeypatch):
    client = FakeClient([FakeResponse(200, [])])
    monkeypatch.setattr("app.llm.gemini_provider.httpx.AsyncClient", lambda **_kwargs: client)
    provider = GeminiProvider("configured-test-key", "gemini-3.8-flash")

    with pytest.raises(ProviderError) as raised:
        await provider._call_gemini("system", "prompt")
    assert raised.value.state == ProviderState.MALFORMED_RESPONSE
    assert raised.value.code == "PROVIDER_RESPONSE_INVALID"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_gemini_retry_wait_is_cancellable(monkeypatch):
    client = FakeClient([FakeResponse(429)])
    monkeypatch.setattr("app.llm.gemini_provider.httpx.AsyncClient", lambda **_kwargs: client)

    async def cancel_sleep(_delay):
        raise asyncio.CancelledError

    monkeypatch.setattr("app.llm.gemini_provider.asyncio.sleep", cancel_sleep)
    provider = GeminiProvider("configured-test-key", "gemini-3.8-flash")

    with pytest.raises(asyncio.CancelledError):
        await provider._call_gemini("system", "prompt")
    assert client.calls == 1
