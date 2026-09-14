"""WebSocket event bus for the backend.

Other modules call `publish(event_type, data)` (broadcast-to-all) or
`publish_to_project(project_id, event_type, data)` (scoped broadcast) to
push events to connected browsers instantly. The WebSocket route in
api/websocket.py uses `manager.connect / disconnect / subscribe` to
register clients and per-project subscriptions.
"""

from app.ws.events import manager, publish, publish_to_project

__all__ = ["manager", "publish", "publish_to_project"]