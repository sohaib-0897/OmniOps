"""Reproducible local production-mode closure topology; secrets never printed."""
import json
import os
import secrets
import subprocess
import sys


def docker(*args, env=None):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if result.returncode:
        # Docker startup diagnostics contain no supplied environment values.
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


def main():
    if "--replace-front" in sys.argv:
        old = json.loads(docker("inspect", "omniops-phase6-front"))[0]
        assert old["Name"] == "/omniops-phase6-front"
        docker("rm", "-f", "omniops-phase6-front")
        print(docker("run", "-d", "--name", "omniops-phase6-front", "--network", "omniops_default", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m", "-p", "127.0.0.1:13000:3000", "omniops-frontend:phase6"))
        return
    if "--replace-runner" in sys.argv:
        old = json.loads(docker("inspect", "omniops-phase6-runner"))[0]
        env = {**os.environ, **dict(v.split("=", 1) for v in old["Config"]["Env"] if "=" in v)}
        assert old["Name"] == "/omniops-phase6-runner"
        docker("rm", "-f", "omniops-phase6-runner")
        print(docker("run", "-d", "--name", "omniops-phase6-runner", "--network", "omniops_default", "-e", "SANDBOX_RUNNER_TOKEN", "-e", "SANDBOX_IMAGE", "-v", "/var/run/docker.sock:/var/run/docker.sock", "omniops-sandbox-runner:phase6", env=env))
        return
    if "--replace-web" in sys.argv:
        for name in ("a", "b", "worker"):
            container = f"omniops-phase6-{name}"
            old = json.loads(docker("inspect", container))[0]
            env = {**os.environ, **dict(v.split("=", 1) for v in old["Config"]["Env"] if "=" in v)}
            flags = [item for value in old["Config"]["Env"] for item in ("-e", value.split("=", 1)[0])]
            assert old["Name"] == "/" + container
            docker("rm", "-f", container)
            ports = ["-p", f"127.0.0.1:{18001 if name == 'a' else 18002}:8000"] if name != "worker" else []
            command = [] if name != "worker" else ["python", "-m", "app.worker"]
            health = [] if name != "worker" else ["--health-cmd", "python -c \"from pathlib import Path; assert b'app.worker' in Path('/proc/1/cmdline').read_bytes()\""]
            print(name, docker("run", "-d", "--name", container, "--network", "omniops_default", *flags,
                              "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m", "--memory", "2g", "--cpus", "2",
                              "-v", "omniops_phase6_closure_storage:/app/storage", *ports, *health, "omniops-backend:phase6", *command, env=env))
        return
    pg = json.loads(docker("inspect", "omniops-postgres"))[0]
    pg_env = dict(v.split("=", 1) for v in pg["Config"]["Env"] if "=" in v)
    database = "omniops_phase6_closure_test"
    existing = docker("exec", "omniops-postgres", "psql", "-U", "omniops", "-d", "postgres", "-Atc", f"SELECT 1 FROM pg_database WHERE datname='{database}'")
    if not existing:
        docker("exec", "omniops-postgres", "createdb", "-U", "omniops", database)
    docker("volume", "create", "omniops_phase6_closure_storage")
    env = dict(os.environ)
    env.update(DATABASE_URL=f"postgresql+asyncpg://omniops:{pg_env['POSTGRES_PASSWORD']}@omniops-postgres:5432/{database}",
               SECRET_KEY=secrets.token_urlsafe(48), ENVIRONMENT="production", COOKIE_SECURE="true",
               CORS_ORIGINS='["https://localhost:13000"]', SANDBOX_EXECUTION_MODE="remote",
               SANDBOX_RUNNER_URL="http://omniops-phase6-runner:9100", SANDBOX_RUNNER_TOKEN=secrets.token_urlsafe(48),
               SANDBOX_IMAGE="omniops-python-sandbox:phase6", LLM_PROVIDER="analytical",
               OPENAI_API_KEY="", GEMINI_API_KEY="", ANTHROPIC_API_KEY="")
    names = ["DATABASE_URL", "SECRET_KEY", "ENVIRONMENT", "COOKIE_SECURE", "CORS_ORIGINS", "SANDBOX_EXECUTION_MODE", "SANDBOX_RUNNER_URL", "SANDBOX_RUNNER_TOKEN", "SANDBOX_IMAGE", "LLM_PROVIDER", "OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"]
    flags = [item for name in names for item in ("-e", name)]
    base = ["--network", "omniops_default"]
    print(docker("run", "-d", "--name", "omniops-phase6-runner", *base, "-e", "SANDBOX_RUNNER_TOKEN", "-e", "SANDBOX_IMAGE", "-v", "/var/run/docker.sock:/var/run/docker.sock", "omniops-sandbox-runner:phase6", env=env))
    print(docker("run", "--name", "omniops-phase6-migrate", *base, *flags, "omniops-backend:phase6", "alembic", "-c", "alembic.ini", "upgrade", "head", env=env))
    for name, port in [("a", "18001"), ("b", "18002"), ("worker", None)]:
        ports = ["-p", f"127.0.0.1:{port}:8000"] if port else []
        command = [] if port else ["python", "-m", "app.worker"]
        print(name, docker("run", "-d", "--name", f"omniops-phase6-{name}", *base, *flags,
                          "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m", "--memory", "2g", "--cpus", "2",
                          "-v", "omniops_phase6_closure_storage:/app/storage", *ports, "omniops-backend:phase6", *command, env=env))


if __name__ == "__main__":
    main()
