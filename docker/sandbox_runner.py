"""Minimal runner entrypoint baked into the analytical execution image."""

from __future__ import annotations

import contextlib
import base64
import io
import json
import sys
import traceback


class LimitedTextIO(io.StringIO):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit
        self.truncated = False

    def write(self, text: str) -> int:
        remaining = self.limit - self.tell()
        if remaining <= 0:
            self.truncated = True
            return len(text)
        if len(text) > remaining:
            super().write(text[:remaining])
            self.truncated = True
            return len(text)
        return super().write(text)


def main() -> int:
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--payload":
            request = json.loads(base64.b64decode(sys.argv[2]).decode("utf-8"))
        else:
            request = json.load(sys.stdin)
        code = request["code"]
        input_data = request.get("input_data") or {}
        stdout = LimitedTextIO(64 * 1024)
        stderr = LimitedTextIO(64 * 1024)

        def run_calculation():
            namespace = {"INPUT_DATA": input_data}
            # A function wrapper preserves the existing return-oriented tool
            # contract while keeping the request namespace minimal.
            function_code = "def __omniops_run():\n" + "\n".join("    " + line for line in code.splitlines())
            exec(compile(function_code, "<omniops-analytical-code>", "exec"), namespace)
            return namespace["__omniops_run"]()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                result = run_calculation()
                payload = {"success": True, "status": "success", "result": result, "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}
            except MemoryError:
                payload = {"success": False, "status": "resource_limit", "error_code": "SANDBOX_MEMORY_LIMIT", "error": "Analytical code exceeded the memory limit.", "stdout": stdout.getvalue(), "stderr": stderr.getvalue(), "resource_limit_hit": True}
            except BaseException as exc:
                payload = {"success": False, "status": "user_code_failure", "error_code": "SANDBOX_USER_CODE_ERROR", "error": str(exc), "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}
        if stdout.truncated or stderr.truncated:
            payload.update({"success": False, "status": "resource_limit", "error_code": "SANDBOX_OUTPUT_LIMIT", "error": "Sandbox output exceeded the configured limit.", "resource_limit_hit": True})
        encoded = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
        if len(encoded) > 256 * 1024:
            encoded = json.dumps({"success": False, "status": "resource_limit", "error_code": "SANDBOX_OUTPUT_LIMIT", "error": "Sandbox result exceeded the configured limit.", "resource_limit_hit": True, "stdout": stdout.getvalue()[:64 * 1024], "stderr": stderr.getvalue()[:64 * 1024]}, separators=(",", ":")).encode("utf-8")
        sys.stdout.buffer.write(encoded)
        sys.stdout.flush()
        return 0
    except BaseException as exc:
        json.dump({"success": False, "status": "infrastructure_failure", "error_code": "SANDBOX_INFRASTRUCTURE_ERROR", "error": str(exc)}, sys.stdout)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
