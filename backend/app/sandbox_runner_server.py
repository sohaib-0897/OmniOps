"""Dedicated internal sandbox runner.

This service is separate from the web/backend container. Only this service is
allowed to talk to the Docker Engine, and it accepts a constrained structured
request rather than arbitrary Docker arguments. Production should deploy it
on an isolated/rootless runner host where possible.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
import uuid
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=256 * 1024)
    input_data: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=5, ge=1, le=60)


class RunnerSettings:
    image = os.getenv("SANDBOX_IMAGE", "omniops-python-sandbox:2026.09.05")
    token = os.getenv("SANDBOX_RUNNER_TOKEN", "")
    memory_mb = int(os.getenv("SANDBOX_MAX_MEMORY_MB", "256"))
    pids = int(os.getenv("SANDBOX_MAX_PIDS", "32"))
    cpu_limit = max(0.1, float(os.getenv("SANDBOX_CPU_LIMIT", "1.0")))


app = FastAPI(title="OmniOps Sandbox Runner", docs_url=None, redoc_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _authorize(authorization: Optional[str]) -> None:
    if not RunnerSettings.token or authorization != f"Bearer {RunnerSettings.token}":
        raise HTTPException(status_code=401, detail="Sandbox runner authorization failed.")


def _execute(request: ExecuteRequest) -> dict[str, Any]:
    execution_id = uuid.uuid4().hex
    payload = base64.b64encode(request.model_dump_json().encode("utf-8")).decode("ascii")
    container_id: Optional[str] = None
    started = time.monotonic()
    transport = httpx.HTTPTransport(uds="/var/run/docker.sock")
    try:
        with httpx.Client(transport=transport, base_url="http://docker", timeout=request.timeout_seconds + 5, trust_env=False) as client:
            create = client.post("/v1.41/containers/create", params={"name": f"omniops-sandbox-{execution_id[:20]}"}, json={
                "Image": RunnerSettings.image,
                # The image entrypoint is the trusted runner; only its payload
                # argument is supplied by this API.
                "Cmd": ["--payload", payload],
                "Env": ["PATH=/usr/local/bin:/usr/bin:/bin", "PYTHONUNBUFFERED=1", f"SANDBOX_MEMORY_LIMIT_MB={RunnerSettings.memory_mb}"],
                "User": "65532:65532",
                "WorkingDir": "/sandbox",
                "Tty": True,
                "HostConfig": {
                    "NetworkMode": "none", "ReadonlyRootfs": True,
                    "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
                    "PidsLimit": RunnerSettings.pids, "Memory": RunnerSettings.memory_mb * 1024 * 1024,
                    "MemorySwap": RunnerSettings.memory_mb * 1024 * 1024,
                    "NanoCpus": int(RunnerSettings.cpu_limit * 1_000_000_000), "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
                    "AutoRemove": False,
                },
            })
            create.raise_for_status()
            container_id = create.json()["Id"]
            start_response = client.post(f"/v1.41/containers/{container_id}/start")
            start_response.raise_for_status()
            try:
                wait_response = client.post(f"/v1.41/containers/{container_id}/wait", params={"condition": "not-running"}, timeout=request.timeout_seconds + 2)
                wait_response.raise_for_status()
                result = wait_response.json()
            except httpx.TimeoutException:
                try:
                    client.post(f"/v1.41/containers/{container_id}/kill")
                except Exception:
                    pass
                return {"execution_id": execution_id, "status": "timeout", "success": False, "timed_out": True, "resource_limit_hit": True, "error_code": "SANDBOX_TIMEOUT", "error_message": f"Execution timed out after {request.timeout_seconds} seconds.", "duration_ms": int((time.monotonic() - started) * 1000)}
            logs = client.get(f"/v1.41/containers/{container_id}/logs", params={"stdout": 1, "stderr": 1, "tail": 200}).content
            exit_code = result.get("StatusCode") if isinstance(result, dict) else None
        # The image emits one bounded JSON response. Do not return arbitrary
        # Docker metadata or environment details to the backend.
        import json
        try:
            output = json.loads(logs.decode("utf-8", "replace").splitlines()[-1])
        except Exception:
            output = {"success": False, "status": "infrastructure_failure", "error_code": "SANDBOX_INFRASTRUCTURE_ERROR", "error": "Sandbox returned malformed output."}
        output.update({"execution_id": execution_id, "exit_code": exit_code, "duration_ms": int((time.monotonic() - started) * 1000)})
        if "error" in output and "error_message" not in output:
            output["error_message"] = output["error"]
        return output
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"execution_id": execution_id, "status": "infrastructure_failure", "success": False, "error_code": "SANDBOX_UNAVAILABLE", "error_message": "Sandbox image is unavailable."}
        return {"execution_id": execution_id, "status": "infrastructure_failure", "success": False, "error_code": "SANDBOX_INFRASTRUCTURE_ERROR", "error_message": "Sandbox runner rejected the execution request."}
    except Exception:
        return {"execution_id": execution_id, "status": "infrastructure_failure", "success": False, "error_code": "SANDBOX_INFRASTRUCTURE_ERROR", "error_message": "Sandbox runner could not start an isolated execution."}
    finally:
        if container_id:
            try:
                with httpx.Client(transport=transport, base_url="http://docker", timeout=3, trust_env=False) as client:
                    client.delete(f"/v1.41/containers/{container_id}", params={"force": "true"})
            except Exception:
                pass
        transport.close()


@app.post("/v1/execute")
async def execute(request: ExecuteRequest, authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _authorize(authorization)
    return await asyncio.to_thread(_execute, request)
