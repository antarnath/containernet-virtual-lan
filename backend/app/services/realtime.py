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


async def broadcast_project_event(project_id: str, payload: dict[str, Any]) -> None:
    """Send ``payload`` to every connected client for this project.

    A client whose send raises (e.g. socket closed) is dropped
    silently. The send is best-effort — we never block on a
    slow / dead client.
    """
    bucket = _clients.get(project_id)
    if not bucket:
        return
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


def connected_count(project_id: str) -> int:
    return len(_clients.get(project_id, {}))
