"""WebSocket route at /ws.

Browsers connect once on app startup and stay connected. Per Phase 07
they send ``{type: "subscribe", project_id: "<uuid>"}`` right after
``onopen``; the server records the subscription and only routes
project-scoped events to that socket. ``{type: "ping"}`` keeps the
connection alive and lets the client detect zombie sockets.

Project-less events (legacy global hosts without a ``project_id``) still
reach every connected socket because they are published via the global
``publish(...)`` helper.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ws import manager

router = APIRouter()
log = logging.getLogger(__name__)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        # The server only listens for control envelopes (subscribe / ping);
        # domain events are server -> client only.
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except (TypeError, ValueError):
                # Malformed frame — ignore but don't close the socket.
                log.debug("[ws] ignoring non-JSON frame from client")
                continue

            kind = msg.get("type") if isinstance(msg, dict) else None

            if kind == "subscribe":
                project_id = msg.get("project_id")
                if isinstance(project_id, str) and project_id:
                    await manager.subscribe(websocket, project_id)
                    try:
                        await websocket.send_text(
                            json.dumps(
                                {"type": "subscribed", "project_id": project_id}
                            )
                        )
                    except Exception:
                        # Socket died mid-handshake — let disconnect handle it.
                        pass
                # No project_id -> silently ignore; the client will resend.
                continue

            if kind == "ping":
                try:
                    await websocket.send_text(json.dumps({"type": "pong"}))
                except Exception:
                    pass
                continue

            # Unknown envelope — ignore. We don't close the socket; some
            # future feature may add new control types without a server bump.
            log.debug("[ws] unknown control envelope: %r", kind)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
