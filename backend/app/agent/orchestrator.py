"""Deprecated compatibility wrapper for the durable investigation runtime."""
from __future__ import annotations

import uuid
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession


class AgentOrchestrator:
    """Compatibility symbol; all execution is delegated to the durable runtime."""

    def __init__(self, session_id: uuid.UUID, workspace_id: uuid.UUID, db: AsyncSession):
        self.session_id = session_id
        self.workspace_id = workspace_id
        self.db = db

    async def run(self, objective: str, max_steps: int = 12) -> Dict[str, Any]:
        from app.agent.service import run_investigation
        return await run_investigation(self.session_id, self.db, worker_id=f"compat:{self.session_id}")
