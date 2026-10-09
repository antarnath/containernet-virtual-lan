"""Realtime broadcast — per-project WebSocket channels.

M4 phase 03 introduces the first WebSocket: ``/ws/projects/{id}``.
A single project can have many clients (the dashboard, the canvas
panel, a future logs view, …) and they all receive the same
stream of events for that project.

The broadcast interface is intentionally tiny:

    await broadcast_project_event(project_id, {...})

The caller doesn't need to know how many clients are connected
or where they're connected to — this module handles the
fan-out. The WebSocket endpoint (``api/realtime.py``) registers
its clients in the ``_clients`` dict on connect and removes them
on disconnect.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)

# {project_id: {client_id: WebSocket}}
_clients: dict[str, dict[str, WebSocket]] = {}
# {client_id: project_id} for fast cleanup on disconnect
_client_project: dict[str, str] = {}
# Monotonic counter so each client has a unique id even if they
# reconnect rapidly.
_next_client_id = 0
_client_id_lock = asyncio.Lock()

# M4 phase 07 — pub/sub for in-process subscribers (e.g. the SSE
# stream). {project_id: {subscriber_id: asyncio.Queue}}. The
# broadcast_project_event fan-out writes to every WS client AND
# every queue subscriber for that project.
_subscribers: dict[str, dict[str, asyncio.Queue]] = {}
_subscriber_id_lock = asyncio.Lock()
_next_subscriber_id = 0


async def register(project_id: str, ws: WebSocket) -> str:
    """Add a WebSocket to the project's fan-out list. Returns a
    client_id the caller should pass back to ``unregister``."""
    global _next_client_id
    async with _client_id_lock:
        _next_client_id += 1
        cid = f"c{_next_client_id}"
    _clients.setdefault(project_id, {})[cid] = ws
    _client_project[cid] = project_id
    return cid


def unregister(client_id: str) -> None:
    pid = _client_project.pop(client_id, None)
    if pid is None:
        return
    bucket = _clients.get(pid)
    if bucket is None:
        return
    bucket.pop(client_id, None)
    if not bucket:
        _clients.pop(pid, None)


async def subscribe(project_id: str, queue: asyncio.Queue) -> str:
    """Add a Queue subscriber for in-process fan-out (e.g. SSE).

    The queue is enqueued on every broadcast for that project.
    A full queue drops the oldest item to keep the broadcast
    non-blocking.
    """
    global _next_subscriber_id
    async with _subscriber_id_lock:
        _next_subscriber_id += 1
        sid = f"s{_next_subscriber_id}"
    _subscribers.setdefault(project_id, {})[sid] = queue
    return sid


def unsubscribe(project_id: str, subscriber_id: str) -> None:
    bucket = _subscribers.get(project_id)
    if not bucket:
        return
    bucket.pop(subscriber_id, None)
    if not bucket:
        _subscribers.pop(project_id, None)


async def broadcast_project_event(project_id: str, payload: dict[str, Any]) -> None:
    """Send ``payload`` to every connected client for this project.

    A client whose send raises (e.g. socket closed) is dropped
    silently. The send is best-effort — we never block on a
    slow / dead client. Also fans out to in-process subscribers
    (SSE stream, etc.).
    """
    bucket = _clients.get(project_id)
    if bucket:
        msg = json.dumps(payload)
        dead: list[str] = []
        for cid, ws in list(bucket.items()):
            try:
                await ws.send_text(msg)
            except Exception as exc:
                log.debug("[realtime] client %s send failed: %s", cid, exc)
                dead.append(cid)
        for cid in dead:
            unregister(cid)

    # In-process subscribers.
    subs = _subscribers.get(project_id)
    if subs:
        for sid, q in list(subs.items()):
            try:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(payload)
            except Exception as exc:
                log.debug("[realtime] subscriber %s enqueue failed: %s", sid, exc)


def connected_count(project_id: str) -> int:
    return len(_clients.get(project_id, {}))
