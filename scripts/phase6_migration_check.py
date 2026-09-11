"""Run the migration cycle on a newly named, isolated PostgreSQL database."""
import json
import os
import uuid
from phase6_topology import docker


def main():
    config = json.loads(docker("inspect", "omniops-phase6-a"))[0]
    env = {**os.environ, **dict(v.split("=", 1) for v in config["Config"]["Env"] if "=" in v)}
    database = "omniops_phase6_migration_test_" + uuid.uuid4().hex[:8]
    docker("exec", "omniops-postgres", "createdb", "-U", "omniops", database)
    env["DATABASE_URL"] = env["DATABASE_URL"].rsplit("/", 1)[0] + "/" + database
    flags = [item for value in config["Config"]["Env"] for item in ("-e", value.split("=", 1)[0])]
    records = []
    for args in (("upgrade", "head"), ("current",), ("downgrade", "-1"), ("upgrade", "head"), ("current",)):
        output = docker("run", "--rm", "--network", "omniops_default", *flags, "omniops-backend:phase6", "alembic", "-c", "alembic.ini", *args, env=env)
        records.append({"command": "alembic " + " ".join(args), "exit": 0, "stdout": output})
    code = "import asyncio; from app.api.v1.health import readiness_check; from app.core.database import AsyncSessionLocal; from fastapi import Response; exec('async def check():\\n async with AsyncSessionLocal() as db:\\n  r=Response(); result=await readiness_check(r, db); assert r.status_code==200; print(result.model_dump_json())\\nasyncio.run(check())')"
    smoke = docker("run", "--rm", "--network", "omniops_default", *flags, "omniops-backend:phase6", "python", "-c", code, env=env)
    report = {"database": database, "commands": records, "schema_readiness": json.loads(smoke)}
    with open("phase6-migration-evidence.json", "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
