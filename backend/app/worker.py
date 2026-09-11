"""Durable investigation worker entry point for production deployments."""
import asyncio, os, socket, uuid
from app.agent.service import InvestigationRuntime
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine

async def run() -> None:
    settings.validate_production_configuration()
    worker_id = f"worker:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    try:
        while True:
            async with AsyncSessionLocal() as db:
                result = await InvestigationRuntime(db).run_worker_once(worker_id)
            await asyncio.sleep(0.25 if result else 1.0)
    finally:
        await engine.dispose()

if __name__ == "__main__": asyncio.run(run())
