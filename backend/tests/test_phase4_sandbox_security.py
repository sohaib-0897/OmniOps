"""Adversarial tests for the real Docker sandbox boundary."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.tools.python_sandbox import ContainerSandboxRunner, PythonSandboxRunner


def _raw(code: str, timeout: int = 10):
    # Call the container boundary directly for bypass tests. Production calls
    # go through PythonSandboxRunner, which adds AST defense-in-depth first.
    return ContainerSandboxRunner.execute(code, {}, timeout)


def test_sandbox_safe_calculation_uses_container():
    result = PythonSandboxRunner.execute("return 6 * 7")
    assert result.success is True
    assert result.computed_output == 42
    assert result.status == "success"
    assert result.exit_code == 0


def test_container_does_not_receive_application_secrets():
    result = _raw("import os\nreturn {k: v for k, v in os.environ.items() if k in {'GEMINI_API_KEY','OPENAI_API_KEY','DATABASE_URL','SECRET_KEY'}}")
    assert result.success is True
    assert result.computed_output == {}


def test_container_cannot_read_application_or_host_paths():
    result = _raw("import os\nreturn {p: os.path.exists(p) for p in ['/app/.env','/workspace/.env','/host/.env']}")
    assert result.success is True
    assert result.computed_output == {"/app/.env": False, "/workspace/.env": False, "/host/.env": False}


def test_container_root_is_read_only_but_tmpfs_is_disposable():
    result = _raw("import os\ntry:\n    open('/outside-marker', 'w').write('x')\n    outside = True\nexcept Exception:\n    outside = False\nopen('/tmp/inside-marker', 'w').write('x')\nreturn {'outside': outside, 'inside': os.path.exists('/tmp/inside-marker')}")
    assert result.success is True
    assert result.computed_output == {"outside": False, "inside": True}


def test_container_network_is_disabled_even_if_static_policy_is_bypassed():
    result = _raw("import socket\ntry:\n    socket.create_connection(('1.1.1.1', 80), timeout=1)\n    connected = True\nexcept Exception:\n    connected = False\nreturn connected", timeout=10)
    assert result.success is True
    assert result.computed_output is False


def test_container_cannot_reach_localhost_or_backend_network():
    result = _raw("import socket\nchecks = []\nfor target in [('127.0.0.1', 8000), ('127.0.0.1', 5432)]:\n    try:\n        socket.create_connection(target, timeout=1)\n        checks.append(True)\n    except Exception:\n        checks.append(False)\nreturn checks", timeout=10)
    assert result.success is True
    assert result.computed_output == [False, False]


def test_infinite_loop_is_terminated_by_wall_clock_limit():
    result = _raw("while True:\n    pass", timeout=1)
    assert result.success is False
    assert result.timed_out is True
    assert result.error_code == "SANDBOX_TIMEOUT"


def test_stdout_is_bounded():
    result = _raw("print('x' * 400000)\nreturn 1")
    assert result.success is False
    assert result.error_code == "SANDBOX_OUTPUT_LIMIT"
    assert result.resource_limit_hit is True
    assert len(result.stdout) <= 65536


def test_memory_limit_contains_large_allocation():
    result = _raw("x = bytearray(512 * 1024 * 1024)\nfor i in range(0, len(x), 4096):\n    x[i] = 1\nreturn x[0]", timeout=5)
    assert result.success is False
    assert result.resource_limit_hit or result.error_code in {"SANDBOX_MEMORY_LIMIT", "SANDBOX_INFRASTRUCTURE_ERROR"}


def test_process_creation_is_contained_by_pid_limit():
    result = _raw("import subprocess\nprocs = []\nfor _ in range(100):\n    procs.append(subprocess.Popen(['python', '-c', 'import time; time.sleep(5)']))\nreturn len(procs)", timeout=2)
    assert result.success is False
    assert result.timed_out or result.resource_limit_hit or result.error_code in {"SANDBOX_USER_CODE_ERROR", "SANDBOX_MEMORY_LIMIT"}


def test_concurrent_sandboxes_have_distinct_execution_ids():
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda value: _raw(f"return {value}"), [1, 2]))
    assert all(result.success for result in results)
    assert len({result.execution_id for result in results}) == 2
    assert {result.computed_output for result in results} == {1, 2}


def test_unavailable_production_runner_fails_closed(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(config.settings, "SANDBOX_RUNNER_URL", None)
    result = PythonSandboxRunner.execute("return 1")
    assert result.success is False
    assert result.error_code == "SANDBOX_UNAVAILABLE"
