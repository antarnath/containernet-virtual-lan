"""WebSocket connection manager + global event publisher.

Broadcasting a JSON event to every connected browser is just one call:
    from app.ws import publish
    publish("communication_complete", {"id": "...", "status": "delivered"})

Each event is wrapped in a standard envelope before being sent:
    {"type": "<event_type>", "data": <payload>, "ts": "<iso8601>"}
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Tracks active WebSocket clients and broadcasts events to them."""

    def __init__(self) -> None:
        self._clients: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.append(ws)
        print(f"[ws] client connected — total {len(self._clients)}")

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)
        print(f"[ws] client disconnected — total {len(self._clients)}")

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send the event to every connected client. Drops dead ones silently."""
        payload = json.dumps(event, default=str)
        dead: list[WebSocket] = []
        # Snapshot the list under the lock to avoid mutation during iteration.
        async with self._lock:
            snapshot = list(self._clients)
        for client in snapshot:
            try:
                await client.send_text(payload)
            except Exception:
                dead.append(client)
        if dead:
            async with self._lock:
                for d in dead:
                    if d in self._clients:
                        self._clients.remove(d)


# Singleton — every module imports this same instance.
manager = ConnectionManager()


def publish(event_type: str, data: Any) -> None:
    """Fire-and-forget event publish. Safe to call from sync code.

    Schedules the broadcast on the running event loop. If there is no loop
    running (e.g. at app startup), the call is logged once and dropped.
    """
    envelope = {
        "type": event_type,
        "data": data,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        print(f"[ws] publish() called with no running loop — event '{event_type}' dropped")
        return
    loop.create_task(manager.broadcast(envelope))