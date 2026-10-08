"""WebSocket endpoint for per-project realtime events.

M4 phase 03. The first channel is ``/ws/projects/{id}`` — it
streams anomaly events from the detector to the canvas / panel /
logs view clients. The connection is server-push only; the
client never sends anything (we ignore incoming frames so an
unintended send doesn't crash the handler).

Connection lifecycle:

  client                                server
  ────────                              ─────
  ws connect /ws/projects/{id}    ──▶   accept
                                       register client
                                       (loop: receive + ignore)
  on anomaly event:                     fan-out send_text
  ◀── {type: "anomaly", ...}    ───     unregister on close
  ws close                       ──▶   unregister
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services import realtime

log = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/projects/{project_id}")
async def ws_project(websocket: WebSocket, project_id: str) -> None:
    await websocket.accept()
    cid = await realtime.register(project_id, websocket)
    log.info("[ws] project=%s client=%s connected", project_id, cid)
    try:
        # We don't expect any inbound messages; the loop's only
        # job is to keep the connection open and notice when the
        # client disconnects.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.debug("[ws] project=%s client=%s error: %s", project_id, cid, exc)
    finally:
        realtime.unregister(cid)
        log.info("[ws] project=%s client=%s disconnected", project_id, cid)
