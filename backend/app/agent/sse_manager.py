import asyncio
import json
import uuid
from typing import Dict, Any, AsyncGenerator, Set
from pydantic import BaseModel

class SSEBroadcaster:
    """Manages active Server-Sent Event subscriber queues and session cancellation tokens."""

    def __init__(self):
        # Maps session_id (str) -> Set[asyncio.Queue]
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        # Maps session_id (str) -> asyncio.Event (cancellation token)
        self._cancellation_events: Dict[str, asyncio.Event] = {}
        # Maps session_id (str) -> List[str] (buffered event payloads for replay)
        self._history: Dict[str, list] = {}

    def get_cancellation_event(self, session_id: str) -> asyncio.Event:
        if session_id not in self._cancellation_events:
            self._cancellation_events[session_id] = asyncio.Event()
        return self._cancellation_events[session_id]

    def request_cancellation(self, session_id: str) -> bool:
        """Signal ongoing investigation state machine to stop."""
        event = self.get_cancellation_event(session_id)
        event.set()
        return True

    def is_cancelled(self, session_id: str) -> bool:
        if session_id in self._cancellation_events:
            return self._cancellation_events[session_id].is_set()
        return False

    def subscribe(self, session_id: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        if session_id not in self._subscribers:
            self._subscribers[session_id] = set()
        self._subscribers[session_id].add(queue)

        # Replay past buffered events so late-connecting or reconnected subscribers never miss events
        if session_id in self._history:
            for event_payload in self._history[session_id]:
                queue.put_nowait(event_payload)

        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue):
        if session_id in self._subscribers:
            self._subscribers[session_id].discard(queue)
            if not self._subscribers[session_id]:
                del self._subscribers[session_id]

    async def emit(self, session_id: str, event_type: str, data: Dict[str, Any]):
        """Emit sanitized SSE event to all connected listeners and store in history."""
        payload = f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"

        if session_id not in self._history:
            self._history[session_id] = []
        self._history[session_id].append(payload)

        if session_id in self._subscribers:
            dead_queues = set()
            for q in self._subscribers[session_id]:
                try:
                    q.put_nowait(payload)
                except Exception:
                    dead_queues.add(q)
                    
            for dq in dead_queues:
                self._subscribers[session_id].discard(dq)

    def clear_history(self, session_id: str):
        self._history.pop(session_id, None)

sse_manager = SSEBroadcaster()
