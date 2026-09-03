"""WebSocket event bus for the backend.

Other modules call `publish(event_type, data)` to broadcast to every connected
browser instantly. The WebSocket route in api/websocket.py uses
`manager.connect/disconnect` to register/deregister clients.
"""

from app.ws.events import manager, publish

__all__ = ["manager", "publish"]