import asyncio
import json
from typing import Dict, Any, Set

class SSEBroadcaster:
    """Manages active Server-Sent Event subscriber queues and session cancellation tokens."""

    def __init__(self):
        # Maps session_id (str) -> Set[asyncio.Queue]
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        # Maps session_id (str) -> asyncio.Event (cancellation token)
        self._cancellation_events: Dict[str, asyncio.Event] = {}
        # Durable replay is served from runtime_events in PostgreSQL. This local
        # broadcaster deliberately retains no history across emissions.
        self._queue_size = 100

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
        queue = asyncio.Queue(maxsize=self._queue_size)
        if session_id not in self._subscribers:
            self._subscribers[session_id] = set()
        self._subscribers[session_id].add(queue)

        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue):
        if session_id in self._subscribers:
            self._subscribers[session_id].discard(queue)
            if not self._subscribers[session_id]:
                del self._subscribers[session_id]

    async def emit(self, session_id: str, event_type: str, data: Dict[str, Any]):
        """Emit to local listeners without allowing slow clients to grow RAM."""
        payload = f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"

        if session_id in self._subscribers:
            dead_queues = set()
            for q in self._subscribers[session_id]:
                try:
                    q.put_nowait(payload)
                except (asyncio.QueueFull, RuntimeError):
                    dead_queues.add(q)
                    
            for dq in dead_queues:
                self._subscribers[session_id].discard(dq)

    def clear_history(self, session_id: str):
        # Compatibility shim: persisted runtime events are the replay store.
        return None

sse_manager = SSEBroadcaster()
