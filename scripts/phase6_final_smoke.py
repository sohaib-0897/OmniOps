"""Final running-image identity and authenticated external sandbox smoke."""
import json
import httpx
from phase6_topology import docker


def main():
    report = {}
    report["containers"] = []
    for name in ("a", "b", "worker", "front", "runner"):
        item = json.loads(docker("inspect", "omniops-phase6-" + name))[0]
        report["containers"].append({"name": item["Name"], "id": item["Id"][:12], "image_id": item["Image"], "user": item["Config"]["User"], "read_only": item["HostConfig"]["ReadonlyRootfs"], "health": item["State"].get("Health", {}).get("Status"), "mount_destinations": [m["Destination"] for m in item["Mounts"]]})
    with httpx.Client(timeout=10) as client:
        report["frontend"] = client.get("http://127.0.0.1:13000").status_code
        report["readiness"] = [client.get(f"http://127.0.0.1:{port}/api/v1/readiness").status_code for port in (18001, 18002)]
    code = "from app.tools.python_sandbox import PythonSandboxRunner; import json; r=PythonSandboxRunner.execute('print(1 + 1)'); print(json.dumps({'success':r.success,'stdout':r.stdout,'error_code':r.error_code})); assert r.success and r.stdout.strip()=='2'"
    report["external_sandbox"] = json.loads(docker("exec", "omniops-phase6-a", "python", "-c", code))
    with open("phase6-final-smoke.json", "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
