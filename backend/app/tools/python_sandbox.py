"""OS-isolated analytical Python execution.

AST validation is defense-in-depth. The security boundary is a dedicated
Docker execution image (or an internal sandbox-runner service), which receives
only a JSON request over stdin and runs with no network, no host mounts, no
inherited secrets, and bounded resources. Production fails closed when the
runner is unavailable; it never falls back to host Python execution.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, Optional, Set

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings


SAFE_MODULES: Set[str] = {
    "math", "statistics", "datetime", "decimal", "json",
    "pandas", "numpy", "re", "time",
}

FORBIDDEN_ATTRIBUTES: Set[str] = {
    "__class__", "__bases__", "__subclasses__", "__globals__",
    "__code__", "__closure__", "__dict__", "__module__", "__builtins__",
    "__import__", "__reduce__", "__reduce_ex__", "__mro__", "__init_subclass__",
    "__prepare__", "__spec__", "__loader__", "__file__", "__cached__",
    "__init__", "__new__", "__getattribute__",
    "f_locals", "f_globals", "f_builtins", "f_code", "gi_frame", "cr_frame",
    "read_csv", "read_parquet", "read_excel", "read_pickle", "read_sql",
    "read_table", "read_json", "read_html", "read_feather", "read_hdf",
    "read_stata", "read_sas", "read_spss", "read_clipboard", "read_xml",
    "to_pickle", "to_csv", "to_excel", "to_sql", "to_parquet", "to_feather", "to_hdf",
    "to_json", "to_html", "to_stata", "to_clipboard", "to_xml",
    "eval", "query", "load", "save", "savez", "savez_compressed", "fromfile",
    "tofile", "memmap", "genfromtxt", "loadtxt", "fromregex", "fromstring",
}

FORBIDDEN_CALLS: Set[str] = {
    "eval", "exec", "compile", "open", "__import__", "globals", "locals",
    "getattr", "setattr", "delattr", "hasattr", "breakpoint", "input",
    "exit", "quit", "help",
}


class SandboxResult(BaseModel):
    execution_id: str = ""
    status: str = "failed"
    success: bool = False
    computed_output: Any = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    exit_code: Optional[int] = None
    timed_out: bool = False
    resource_limit_hit: bool = False
    artifacts: list[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    reproducibility_hash: Optional[str] = None


class ASTSecurityVisitor(ast.NodeVisitor):
    """Reject known unsafe constructs before code reaches the container."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root_mod = alias.name.split(".")[0]
            if root_mod not in SAFE_MODULES:
                self.errors.append(f"Import of unauthorized module '{alias.name}' is prohibited.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            root_mod = node.module.split(".")[0]
            if root_mod not in SAFE_MODULES:
                self.errors.append(f"Import from unauthorized module '{node.module}' is prohibited.")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in FORBIDDEN_ATTRIBUTES:
            self.errors.append(f"Access to introspection attribute '{node.attr}' is prohibited.")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_CALLS and isinstance(node.ctx, ast.Load):
            self.errors.append(f"Reference to restricted function '{node.id}' is prohibited.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            self.errors.append(f"Call to prohibited function '{node.func.id}()' is blocked.")
        elif isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRIBUTES:
            self.errors.append(f"Call to prohibited method '{node.func.attr}()' is blocked.")
        self.generic_visit(node)


def validate_python_code(code: str) -> None:
    """Parse and validate source. This is not the OS security boundary."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"Syntax error in Python script: {exc}") from exc
    visitor = ASTSecurityVisitor()
    visitor.visit(tree)
    if visitor.errors:
        raise ValueError(f"Security validation failed: {'; '.join(visitor.errors)}")


def _runner_request(code: str, input_data: Optional[Dict[str, Any]]) -> bytes:
    return json.dumps({"code": code, "input_data": input_data or {}}, separators=(",", ":"), default=str).encode("utf-8")


def _bounded_reader(stream, limit: int, output: bytearray, overflow: threading.Event) -> None:
    """Read a child stream without allowing unbounded parent memory growth."""
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            if len(output) + len(chunk) > limit:
                output.extend(chunk[: max(0, limit - len(output))])
                overflow.set()
                return
            output.extend(chunk)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _terminate_container(proc: subprocess.Popen, name: str) -> None:
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=2)
    except Exception:
        pass
    docker = shutil.which("docker")
    if docker:
        try:
            subprocess.run([docker, "rm", "-f", name], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=False)
        except Exception:
            pass


class ContainerSandboxRunner:
    """Run the dedicated image with a fail-closed Docker policy."""

    @classmethod
    def execute(cls, code: str, input_data: Optional[Dict[str, Any]], timeout_seconds: int) -> SandboxResult:
        execution_id = uuid.uuid4().hex
        start = time.monotonic()
        # This launcher is intentionally limited to local development/test.
        # Keep the guard at the launcher boundary as well as in the facade so
        # a direct import/call cannot reintroduce Docker Engine access from a
        # production API process.
        if (settings.ENVIRONMENT or "").lower() not in {"development", "test"}:
            return SandboxResult(
                execution_id=execution_id,
                status="infrastructure_failure",
                error_code="SANDBOX_UNAVAILABLE",
                error_message="Local Docker sandbox execution is disabled outside development/test; configure the remote runner.",
            )
        docker = shutil.which("docker")
        if not docker:
            return SandboxResult(execution_id=execution_id, error_code="SANDBOX_UNAVAILABLE", error_message="Docker is unavailable; analytical code execution failed closed.")

        name = f"omniops-sandbox-{execution_id[:20]}"
        command = [
            docker, "run", "--rm", "-i", "--init", "--name", name,
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt", "no-new-privileges:true",
            "--pids-limit", str(max(1, settings.SANDBOX_MAX_PIDS)),
            "--memory", f"{max(64, settings.SANDBOX_MAX_MEMORY_MB)}m",
            "--memory-swap", f"{max(64, settings.SANDBOX_MAX_MEMORY_MB)}m",
            "--cpus", str(max(0.1, settings.SANDBOX_CPU_LIMIT)), "--user", "65532:65532",
            "--workdir", "/sandbox",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--env", "PATH=/usr/local/bin:/usr/bin:/bin",
            "--env", "PYTHONUNBUFFERED=1",
            "--env", f"SANDBOX_MEMORY_LIMIT_MB={max(64, settings.SANDBOX_MAX_MEMORY_MB)}",
            settings.SANDBOX_IMAGE,
        ]
        proc: Optional[subprocess.Popen] = None
        stdout = bytearray()
        stderr = bytearray()
        overflow = threading.Event()
        try:
            # Only Docker CLI metadata is inherited by this trusted launcher;
            # the execution container itself receives the explicit env above.
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={"PATH": os.environ.get("PATH", ""), "PYTHONUNBUFFERED": "1"})
            assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
            proc.stdin.write(_runner_request(code, input_data))
            proc.stdin.close()
            out_thread = threading.Thread(target=_bounded_reader, args=(proc.stdout, settings.SANDBOX_MAX_OUTPUT_BYTES, stdout, overflow), daemon=True)
            err_thread = threading.Thread(target=_bounded_reader, args=(proc.stderr, settings.SANDBOX_MAX_STDERR_BYTES, stderr, overflow), daemon=True)
            out_thread.start(); err_thread.start()
            try:
                proc.wait(timeout=max(1, timeout_seconds))
            except subprocess.TimeoutExpired:
                _terminate_container(proc, name)
                out_thread.join(timeout=2); err_thread.join(timeout=2)
                return SandboxResult(execution_id=execution_id, status="timeout", success=False, timed_out=True, duration_ms=int((time.monotonic() - start) * 1000), error_code="SANDBOX_TIMEOUT", error_message=f"Execution timed out after {timeout_seconds} seconds.", stdout=stdout.decode("utf-8", "replace"), stderr=stderr.decode("utf-8", "replace"))
            out_thread.join(timeout=2); err_thread.join(timeout=2)
            duration_ms = int((time.monotonic() - start) * 1000)
            if overflow.is_set():
                _terminate_container(proc, name)
                return SandboxResult(execution_id=execution_id, status="resource_limit", success=False, resource_limit_hit=True, duration_ms=duration_ms, error_code="SANDBOX_OUTPUT_LIMIT", error_message="Sandbox output exceeded the configured limit.", stdout=stdout.decode("utf-8", "replace"), stderr=stderr.decode("utf-8", "replace"), exit_code=proc.returncode)
            raw = stdout.decode("utf-8", "replace").strip()
            if not raw:
                return SandboxResult(execution_id=execution_id, status="infrastructure_failure", success=False, duration_ms=duration_ms, exit_code=proc.returncode, error_code="SANDBOX_INFRASTRUCTURE_ERROR", error_message=stderr.decode("utf-8", "replace").strip() or "Sandbox produced no result.", stderr=stderr.decode("utf-8", "replace"))
            try:
                payload = json.loads(raw.splitlines()[-1])
            except json.JSONDecodeError:
                return SandboxResult(execution_id=execution_id, status="infrastructure_failure", success=False, duration_ms=duration_ms, exit_code=proc.returncode, error_code="SANDBOX_INFRASTRUCTURE_ERROR", error_message="Sandbox returned malformed output.", stdout=raw, stderr=stderr.decode("utf-8", "replace"))
            result_value = payload.get("result")
            user_stdout = str(payload.get("stdout") or "")[: settings.SANDBOX_MAX_STDOUT_BYTES]
            user_stderr = str(payload.get("stderr") or "")[: settings.SANDBOX_MAX_STDERR_BYTES]
            if payload.get("success"):
                repro_hash = hashlib.sha256(json.dumps({"code": code.strip(), "input": input_data, "output": result_value}, sort_keys=True, default=str).encode("utf-8")).hexdigest()
                return SandboxResult(execution_id=execution_id, status="success", success=True, computed_output=result_value, stdout=user_stdout, stderr=user_stderr, duration_ms=duration_ms, exit_code=proc.returncode, reproducibility_hash=repro_hash)
            return SandboxResult(execution_id=execution_id, status=payload.get("status", "user_code_failure"), success=False, stdout=user_stdout, stderr=user_stderr, duration_ms=duration_ms, exit_code=proc.returncode, error_code=payload.get("error_code", "SANDBOX_USER_CODE_ERROR"), error_message=payload.get("error") or "User code failed.", resource_limit_hit=bool(payload.get("resource_limit_hit")))
        except (OSError, subprocess.SubprocessError) as exc:
            if proc is not None:
                _terminate_container(proc, name)
            return SandboxResult(execution_id=execution_id, status="infrastructure_failure", success=False, duration_ms=int((time.monotonic() - start) * 1000), error_code="SANDBOX_INFRASTRUCTURE_ERROR", error_message=str(exc))
        finally:
            if proc is not None and proc.poll() is None:
                _terminate_container(proc, name)


class RemoteSandboxRunner:
    """Client for a dedicated internal sandbox-runner service."""

    @classmethod
    def execute(cls, code: str, input_data: Optional[Dict[str, Any]], timeout_seconds: int) -> SandboxResult:
        execution_id = uuid.uuid4().hex
        if not settings.SANDBOX_RUNNER_URL:
            return SandboxResult(execution_id=execution_id, error_code="SANDBOX_UNAVAILABLE", error_message="Sandbox runner URL is not configured; execution failed closed.")
        headers = {"Authorization": f"Bearer {settings.SANDBOX_RUNNER_TOKEN}"} if settings.SANDBOX_RUNNER_TOKEN else {}
        try:
            with httpx.Client(timeout=timeout_seconds + 2, trust_env=False) as client:
                response = client.post(settings.SANDBOX_RUNNER_URL.rstrip("/") + "/v1/execute", json={"code": code, "input_data": input_data or {}, "timeout_seconds": timeout_seconds}, headers=headers)
            response.raise_for_status()
            payload = response.json()
            # The runner protocol names the user result `result`; normalize it
            # to the public SandboxResult contract without exposing Docker data.
            if "computed_output" not in payload and "result" in payload:
                payload["computed_output"] = payload["result"]
            return SandboxResult.model_validate(payload)
        except Exception as exc:
            return SandboxResult(execution_id=execution_id, status="infrastructure_failure", error_code="SANDBOX_INFRASTRUCTURE_ERROR", error_message=f"Sandbox runner unavailable: {exc}")


class PythonSandboxRunner:
    """Compatibility facade; never executes untrusted code on the host."""

    @classmethod
    def execute(cls, code: str, input_data: Optional[Dict[str, Any]] = None, timeout_seconds: int = settings.SANDBOX_TIMEOUT_SECONDS) -> SandboxResult:
        start = time.monotonic()
        try:
            if len(code.encode("utf-8")) > settings.SANDBOX_MAX_OUTPUT_BYTES:
                raise ValueError("Sandbox code exceeds the configured input limit.")
            validate_python_code(code)
        except ValueError as exc:
            return SandboxResult(status="policy_rejected", duration_ms=int((time.monotonic() - start) * 1000), error_code="SANDBOX_POLICY_REJECTED", error_message=str(exc))
        mode = (settings.SANDBOX_EXECUTION_MODE or "").lower()
        environment = (settings.ENVIRONMENT or "").lower()
        if mode == "remote":
            # Production never falls back to the local Docker launcher when
            # the isolated service is absent.
            result = RemoteSandboxRunner.execute(code, input_data, timeout_seconds)
        elif mode in {"container", "local_docker"} and environment in {"development", "test"}:
            result = ContainerSandboxRunner.execute(code, input_data, timeout_seconds)
        else:
            result = SandboxResult(
                status="infrastructure_failure",
                error_code="SANDBOX_UNAVAILABLE",
                error_message="No permitted sandbox execution mode is configured; execution failed closed.",
            )
        if not result.duration_ms:
            result.duration_ms = int((time.monotonic() - start) * 1000)
        return result
