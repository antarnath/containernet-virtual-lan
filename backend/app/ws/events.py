"""WebSocket connection manager + global event publisher.

Per-project subscription model (Phase 07)
----------------------------------------
Each browser tab opens a single WebSocket. After ``onopen`` the client sends
``{type: "subscribe", project_id: "<uuid>"}``; the manager records
``(project_id, websocket)`` in ``_subscriptions``. Events published via
``publish_to_project(project_id, event_type, data)`` are routed only to
sockets subscribed to that project.

Project-less events (legacy global hosts without ``project_id``) still call
``publish(event_type, data)`` and broadcast to every connected client.

Each event is wrapped in a standard envelope before being sent:

    { "type": "<event_type>",
      "project_id": "<uuid>",      # top level when published via
                                    # publish_to_project; absent otherwise
      "data": <payload>,           # payload data (may also carry
                                    # project_id for backwards compat with
                                    # the existing frontend handler)
      "ts": "<iso8601>" }
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Tracks active WebSocket clients and per-project subscriptions."""

    def __init__(self) -> None:
        # All live sockets — used for project-less broadcasts + sweep-on-error.
        self._clients: set[WebSocket] = set()
        # Per-project fan-out: project_id -> sockets subscribed to it.
        self._subscriptions: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        print(f"[ws] client connected — total {len(self._clients)}")

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
            # Drain from every subscription bucket so the dead socket never
            # resurfaces as a stale target.
            for subs in self._subscriptions.values():
                subs.discard(ws)
            # Compact: drop any project buckets that became empty.
            empty = [pid for pid, subs in self._subscriptions.items() if not subs]
            for pid in empty:
                self._subscriptions.pop(pid, None)
        print(f"[ws] client disconnected — total {len(self._clients)}")

    async def subscribe(self, ws: WebSocket, project_id: str) -> None:
        """Add ``ws`` to the subscriber set for ``project_id``."""
        async with self._lock:
            self._subscriptions.setdefault(project_id, set()).add(ws)

    async def unsubscribe_from_all(self, ws: WebSocket) -> None:
        """Drop ``ws`` from every subscription bucket (e.g. on project switch)."""
        async with self._lock:
            for subs in self._subscriptions.values():
                subs.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send the event to every connected client (project-less events).

        Drops dead sockets silently.
        """
        payload = json.dumps(event, default=str)
        dead: list[WebSocket] = []
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
                    self._clients.discard(d)
                    for subs in self._subscriptions.values():
                        subs.discard(d)

    async def broadcast_to_project(
        self, project_id: str, event: dict[str, Any]
    ) -> None:
        """Send the event only to sockets subscribed to ``project_id``.

        Drops dead subscribers silently and cleans up their subscription
        rows so the manager stays consistent.
        """
        payload = json.dumps(event, default=str)
        async with self._lock:
            targets = list(self._subscriptions.get(project_id, set()))
        dead: list[WebSocket] = []
        for client in targets:
            try:
                await client.send_text(payload)
            except Exception:
                dead.append(client)
        if dead:
            async with self._lock:
                for d in dead:
                    self._clients.discard(d)
                    for subs in self._subscriptions.values():
                        subs.discard(d)


# Singleton — every module imports this same instance.
manager = ConnectionManager()


def publish(event_type: str, data: Any) -> None:
    """Fire-and-forget broadcast to every connected client.

    Used for project-less events (legacy global hosts). New project-scoped
    events should use :func:`publish_to_project` instead.

    Safe to call from sync code: schedules the broadcast on the running
    event loop. If there is no loop running (e.g. at app startup), the
    call is logged once and dropped.
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


def publish_to_project(project_id: str, event_type: str, data: Any) -> None:
    """Fire-and-forget broadcast to every socket subscribed to ``project_id``.

    The envelope carries ``project_id`` at the top level so consumers can
    route on the envelope without parsing ``data``. ``data`` is also stamped
    with ``project_id`` for backwards compatibility with the existing
    frontend handler that reads ``env.data.project_id``.
    """
    if isinstance(data, dict):
        # Ensure the data payload carries project_id too. Don't overwrite
        # if the caller already set it explicitly.
        data = {**data, "project_id": data.get("project_id") or project_id}
    envelope = {
        "type": event_type,
        "project_id": project_id,
        "data": data,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        print(
            f"[ws] publish_to_project() with no running loop — "
            f"event '{event_type}' for project '{project_id}' dropped"
        )
        return
    loop.create_task(manager.broadcast_to_project(project_id, envelope))
