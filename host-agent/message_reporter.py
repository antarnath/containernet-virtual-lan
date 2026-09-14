"""Host agent → backend message reporter — Phase 08.

After every send (``handle_send``) and receive (``handle_receive``), the
agent POSTs a copy of the event to the backend so it can be:

  1. persisted in the ``messages`` table for history reloads, and
  2. fanned out to subscribed browsers via the ``message`` WebSocket event.

The reporter is fire-and-forget — failures are logged but never raise,
so a flaky backend never breaks the actual host-to-host delivery.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import aiohttp

from config import config


_REPORT_TIMEOUT = 3.0  # seconds


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def report(direction: str, **fields) -> None:
    """POST one message event to the backend. Returns nothing.

    Args:
        direction: ``"in"`` for a receive, ``"out"`` for a send.
        **fields: arbitrary kwargs — at least ``comm_id``, ``peer_host_id``,
            ``payload``, ``protocol``. Missing fields default to empty.

    Never raises; logs and swallows all failures.
    """
    if not config.PROJECT_ID or not config.HOST_ID:
        # Legacy static hosts (pc1/pc2/pc3) don't have a project scope,
        # so there's nowhere on the backend to file the report. Skip.
        return

    payload = {
        "direction": direction,
        "comm_id": fields.get("comm_id", "") or "",
        "peer_host_id": fields.get("peer_host_id", "") or "",
        "payload": fields.get("payload", "") or "",
        "protocol": fields.get("protocol", "HTTP") or "HTTP",
        "timestamp": fields.get("timestamp") or _now_iso(),
    }
    url = (
        f"{config.BACKEND_URL}/api/projects/{config.PROJECT_ID}"
        f"/hosts/{config.HOST_ID}/messages"
    )
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=_REPORT_TIMEOUT)
        ) as session:
            async with session.post(url, json=payload):
                # Discard the response body — we only care it didn't error.
                pass
    except Exception as exc:
        # Reporting must NEVER affect the local send/receive.
        print(f"[{config.HOST_NAME}] message report failed: {exc}")


def fire_and_forget(direction: str, **fields) -> None:
    """Schedule ``report(...)`` as an asyncio task. Non-blocking.

    Use this from sync request handlers — ``report`` is async, so we
    dispatch it on the running loop without awaiting.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop (shouldn't happen inside an aiohttp handler, but be safe).
        return
    loop.create_task(report(direction, **fields))