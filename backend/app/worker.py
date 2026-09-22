"""Durable investigation worker entry point for production deployments."""
import asyncio, logging, os, socket, uuid
from app.agent.service import InvestigationRuntime
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine

logger = logging.getLogger(__name__)

# A single investigation must never terminate the durable worker. Failures are
# already persisted with a normalized failure code by the runtime itself; this
# bound only covers an unexpected error escaping one poll iteration so the
# worker keeps claiming subsequent work.
ITERATION_ERROR_BACKOFF_SECONDS = 2.0


async def run() -> None:
    settings.validate_production_configuration()
    worker_id = f"worker:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    try:
        while True:
            try:
                async with AsyncSessionLocal() as db:
                    result = await InvestigationRuntime(db).run_worker_once(worker_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Worker iteration failed; the worker remains available for new work.")
                await asyncio.sleep(ITERATION_ERROR_BACKOFF_SECONDS)
                continue
            await asyncio.sleep(0.25 if result else 1.0)
    finally:
        await engine.dispose()

if __name__ == "__main__": asyncio.run(run())
