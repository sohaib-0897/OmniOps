"""Collect final image scan attempts, safe audit-log checks and Compose validation."""
import json
import os
import re
import subprocess
import sys
from phase6_topology import docker


def main():
    report = {"scans": []}
    if "--frontend" in sys.argv:
        with open("phase6-container-evidence.json", encoding="utf-8") as file:
            report = json.load(file)
    for image in ("omniops-backend:phase6", "omniops-frontend:phase6", "omniops-python-sandbox:phase6", "omniops-sandbox-runner:phase6"):
        if "--frontend" in sys.argv and image != "omniops-frontend:phase6":
            continue
        info = json.loads(docker("image", "inspect", image))[0]
        result = subprocess.run(["docker", "scout", "cves", image, "--format", "sarif"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
        output = result.stdout + result.stderr
        entry = {"image": image, "image_id": info["Id"], "exit": result.returncode}
        if "Log in with your Docker ID" in output:
            entry.update(status="BLOCKED_DOCKER_LOGIN_REQUIRED", critical=None, high=None, medium=None, low=None)
        elif result.returncode == 0:
            # Preserve the actual scanner output for analysis; never invent counts.
            filename = "phase6-" + image.split(":")[0] + "-scout.sarif"
            with open(filename, "w", encoding="utf-8") as file:
                file.write(result.stdout)
            entry.update(status="SCAN_COMPLETED_REVIEW_REQUIRED", artifact=filename)
        else:
            entry.update(status="SCAN_FAILED", diagnostic=output[:2000])
        report["scans"] = [old for old in report["scans"] if old["image"] != image] + [entry]
        with open("phase6-container-evidence.json", "w", encoding="utf-8") as file:
            json.dump(report, file, indent=2)
        print(json.dumps(entry), flush=True)
    logs = ""
    for name in ("a", "b"):
        result = subprocess.run(["docker", "logs", "omniops-phase6-" + name], capture_output=True, text=True, encoding="utf-8", errors="replace")
        logs += result.stdout + result.stderr
    report["audit_logs"] = {"structured_request_events": '"event_type": "request.completed"' in logs,
                            "refresh_replay_events": '"event_type": "auth.refresh_replay"' in logs,
                            "credential_patterns_found": bool(re.search(r'Bearer\s|omniops_refresh=|eyJ[A-Za-z0-9_-]{20,}\.', logs))}
    assert report["audit_logs"]["structured_request_events"] and report["audit_logs"]["refresh_replay_events"]
    assert not report["audit_logs"]["credential_patterns_found"]
    config = json.loads(docker("inspect", "omniops-phase6-a"))[0]
    env = {**os.environ, **dict(v.split("=", 1) for v in config["Config"]["Env"] if "=" in v)}
    env.update(OMNIOPS_BACKEND_IMAGE="omniops-backend:phase6", OMNIOPS_FRONTEND_IMAGE="omniops-frontend:phase6")
    docker("compose", "-f", "docker-compose.prod.yml", "config", "--quiet", env=env)
    report["production_compose_config"] = "PASS"
    worker = json.loads(docker("inspect", "omniops-phase6-worker"))[0]
    report["worker_healthcheck"] = worker["Config"]["Healthcheck"]
    report["worker_health"] = worker["State"].get("Health", {}).get("Status")
    with open("phase6-container-evidence.json", "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
