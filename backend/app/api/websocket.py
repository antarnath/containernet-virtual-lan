"""WebSocket route at /ws.

Browsers connect once on app startup and stay connected. The server pushes
events to them via the global ConnectionManager.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ws import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        # Keep the connection open. We don't currently expect client -> server
        # messages, but we still need to read so we can detect disconnects.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)