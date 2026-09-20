"""Tests for the narrow backend-to-runner contract and fail-closed modes."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.core import config
from app.sandbox_runner_server import ExecuteRequest, RunnerSettings, app as runner_app
from app.tools import python_sandbox


@pytest.mark.parametrize(
    "field,value",
    [
        ("image", "evil-image"),
        ("mounts", [{"source": "/", "target": "/host"}]),
        ("network_mode", "host"),
        ("privileged", True),
        ("env", {"GEMINI_API_KEY": "stolen"}),
        ("command", ["/bin/sh"]),
    ],
)
def test_runner_contract_forbids_docker_control_injection(field, value):
    payload = {"code": "return 1", field: value}
    with pytest.raises(ValidationError):
        ExecuteRequest.model_validate(payload)


def test_runner_requires_authentication_and_accepts_only_narrow_contract(monkeypatch):
    monkeypatch.setattr(RunnerSettings, "token", "boundary-test-token")
    monkeypatch.setattr(
        "app.sandbox_runner_server._execute",
        lambda request: {"success": True, "status": "success", "result": 1},
    )

    async def exercise():
        transport = httpx.ASGITransport(app=runner_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://runner") as client:
            unauthorized = await client.post("/v1/execute", json={"code": "return 1"})
            authorized = await client.post(
                "/v1/execute",
                json={"code": "return 1"},
                headers={"Authorization": "Bearer boundary-test-token"},
            )
        return unauthorized, authorized

    unauthorized, authorized = asyncio.run(exercise())
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["success"] is True


def test_backend_runner_payload_has_no_runtime_controls(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"execution_id": "e1", "status": "success", "success": True, "result": 1}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json, headers):
            captured.update({"url": url, "json": json, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr(config.settings, "SANDBOX_RUNNER_URL", "http://runner:9100")
    monkeypatch.setattr(config.settings, "SANDBOX_RUNNER_TOKEN", "token")
    monkeypatch.setattr(python_sandbox.httpx, "Client", FakeClient)
    result = python_sandbox.RemoteSandboxRunner.execute("return 1", {}, 3)

    assert result.success is True
    assert set(captured["json"]) == {"code", "input_data", "timeout_seconds"}
    assert all(field not in captured["json"] for field in {"image", "mounts", "network_mode", "privileged", "env"})


def test_remote_success_gets_deterministic_calculation_identity(monkeypatch):
    outputs = iter(
        [
            python_sandbox.SandboxResult(status="success", success=True, computed_output={"total": 3}),
            python_sandbox.SandboxResult(status="success", success=True, computed_output={"total": 3}),
        ]
    )
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(config.settings, "SANDBOX_EXECUTION_MODE", "remote")
    monkeypatch.setattr(
        python_sandbox.RemoteSandboxRunner,
        "execute",
        lambda *args, **kwargs: next(outputs),
    )

    first = python_sandbox.PythonSandboxRunner.execute(
        "return INPUT_DATA['a'] + INPUT_DATA['b']",
        {"a": 1, "b": 2},
    )
    second = python_sandbox.PythonSandboxRunner.execute(
        "return INPUT_DATA['a'] + INPUT_DATA['b']",
        {"b": 2, "a": 1},
    )

    assert first.reproducibility_hash is not None
    assert first.reproducibility_hash == second.reproducibility_hash


def test_production_mode_fails_closed_even_when_local_docker_exists(monkeypatch):
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(config.settings, "SANDBOX_EXECUTION_MODE", "remote")
    monkeypatch.setattr(config.settings, "SANDBOX_RUNNER_URL", None)
    monkeypatch.setattr(
        python_sandbox.ContainerSandboxRunner,
        "execute",
        lambda *args, **kwargs: pytest.fail("production must not use the local Docker launcher"),
    )

    result = python_sandbox.PythonSandboxRunner.execute("return 1")
    assert result.success is False
    assert result.error_code == "SANDBOX_UNAVAILABLE"


def test_direct_local_launcher_is_also_disabled_in_production(monkeypatch):
    """The trusted CLI helper must not be a production escape hatch."""
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(
        python_sandbox.shutil,
        "which",
        lambda name: pytest.fail("production must not inspect or invoke Docker"),
    )

    result = python_sandbox.ContainerSandboxRunner.execute("return 1", {}, 1)
    assert result.success is False
    assert result.error_code == "SANDBOX_UNAVAILABLE"
