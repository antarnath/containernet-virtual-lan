"""Host Agent message service (Phase 05).

Real HTTP endpoints on :8080:
  POST /send     - The backend calls this to ask us to deliver a message.
                   We then POST to the destination's /receive endpoint.
  POST /receive  - Called by another host agent. We log and ack.
  GET  /messages - Returns the last 50 messages we sent/received (debug).
"""

import asyncio
import json
from collections import deque
from datetime import datetime, timezone

import aiohttp
from aiohttp import web

from config import config

# Local ring buffer of messages seen by this host (max 50).
_message_log: deque = deque(maxlen=50)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record(direction: str, **fields) -> dict:
    """Append a record to the log and return it."""
    entry = {"direction": direction, "ts": _now_iso(), **fields}
    _message_log.append(entry)
    print(f"[{config.HOST_NAME}] {direction}: {json.dumps(fields)}")
    return entry


async def handle_send(request: web.Request) -> web.Response:
    """Called by the backend. We open a NEW connection to the destination
    and POST the payload to its /receive endpoint."""
    body = await request.json()
    target_ip = body.get("target_ip")
    target_host_id = body.get("target_host_id")
    comm_id = body.get("comm_id", "")
    project_id = body.get("project_id", "")
    payload = body.get("payload", "")
    protocol = body.get("protocol", "HTTP")

    if not target_ip or not target_host_id:
        return web.json_response(
            {"status": "failed", "error": "missing target_ip or target_host_id"},
            status=400,
        )

    _record(
        "outgoing",
        comm_id=comm_id,
        project_id=project_id,
        target=target_host_id,
        target_ip=target_ip,
        payload=payload,
        protocol=protocol,
    )

    # Open a NEW HTTP client and POST to the destination's /receive endpoint.
    url = f"http://{target_ip}:8080/receive"
    out_body = {
        "comm_id": comm_id,
        "project_id": project_id,
        "from_host_id": config.HOST_ID,
        "from_ip": config.HOST_IP,
        "payload": payload,
        "protocol": protocol,
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.post(url, json=out_body) as resp:
                text = await resp.text()
                return web.json_response(
                    {
                        "status": "sent" if 200 <= resp.status < 300 else "failed",
                        "target": target_host_id,
                        "code": resp.status,
                        "ack": text[:200],
                    }
                )
    except Exception as exc:
        return web.json_response(
            {"status": "failed", "target": target_host_id, "error": f"{type(exc).__name__}: {exc}"},
            status=502,
        )


async def handle_receive(request: web.Request) -> web.Response:
    """Called by another host agent. We log and ack."""
    body = await request.json()
    _record(
        "incoming",
        comm_id=body.get("comm_id", ""),
        project_id=body.get("project_id", ""),
        from_host_id=body.get("from_host_id", ""),
        from_ip=body.get("from_ip", ""),
        payload=body.get("payload", ""),
        protocol=body.get("protocol", "HTTP"),
    )
    return web.json_response({"status": "received", "host": config.HOST_NAME})


async def handle_messages(_request: web.Request) -> web.Response:
    """Debug endpoint — return the last 50 messages."""
    return web.json_response({"host": config.HOST_NAME, "messages": list(_message_log)})


async def run_server() -> None:
    app = web.Application()
    app.router.add_post("/send", handle_send)
    app.router.add_post("/receive", handle_receive)
    app.router.add_get("/messages", handle_messages)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.MESSAGE_PORT)
    await site.start()
    print(f"[{config.HOST_NAME}] message server listening on :{config.MESSAGE_PORT} (real)")


if __name__ == "__main__":
    asyncio.run(run_server())