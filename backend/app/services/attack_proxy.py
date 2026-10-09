"""attack_proxy — forwards start/stop/state to an attacker's :9092.

M4 phase 06. The backend is the only thing that can mutate the
attacker's state (the user hits POST /api/.../attacks/<id>/start).
The proxy wraps each call in a short-timeout aiohttp POST and
returns a small result dict the API layer can serialize.

The IP we hit is the attacker's IP on the **backend** network
(``containernet_containernet_lan``) — same trick as
``communication_service._backend_lan_ip``. Falling back to the
first topology IP works for tests that don't have docker access.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProjectNode

log = logging.getLogger(__name__)

CONTROL_PORT = 9092
# The start call kicks off a scapy ARP loop which takes a few
# hundred ms to import scapy + bind the raw socket on first run.
# Give it room.
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=10)


# ── result shapes ────────────────────────────────────────────


class ProxyError(Exception):
    """Raised when the proxy can't reach the attacker's :9092."""


# ── public API ───────────────────────────────────────────────


async def attacker_state(
    node: ProjectNode, session: AsyncSession
) -> dict[str, Any]:
    """Return the attacker's /state dict. On any error, return
    ``{"error": "<reason>"}`` so the caller can surface it to the UI
    without 500ing the request."""
    ip = _backend_lan_ip(node)
    if not ip:
        return {"error": "no_backend_lan_ip", "running": False}
    url = f"http://{ip}:{CONTROL_PORT}/state"
    try:
        async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as http:
            async with http.get(url) as resp:
                if 200 <= resp.status < 300:
                    return await resp.json()
                return {"error": f"http_{resp.status}", "running": False}
    except Exception as exc:
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "running": False,
        }


async def start_attack(
    node: ProjectNode, mode: str, target_ip: str
) -> dict[str, Any]:
    """POST /attack with {mode, target_ip}. Returns the new state
    on success, or {"error": "..."} on failure."""
    ip = _backend_lan_ip(node)
    if not ip:
        return {"ok": False, "error": "no_backend_lan_ip"}
    url = f"http://{ip}:{CONTROL_PORT}/attack"
    try:
        async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as http:
            async with http.post(url, json={
                "mode": mode, "target_ip": target_ip
            }) as resp:
                body = await resp.json()
                if 200 <= resp.status < 300:
                    return body
                return {
                    "ok": False,
                    "error": body.get("error", f"http_{resp.status}"),
                }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


async def stop_attack(node: ProjectNode) -> dict[str, Any]:
    ip = _backend_lan_ip(node)
    if not ip:
        return {"ok": False, "error": "no_backend_lan_ip"}
    url = f"http://{ip}:{CONTROL_PORT}/attack/stop"
    try:
        async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as http:
            async with http.post(url) as resp:
                body = await resp.json()
                if 200 <= resp.status < 300:
                    return body
                return {
                    "ok": False,
                    "error": body.get("error", f"http_{resp.status}"),
                }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ── helpers ──────────────────────────────────────────────────


def _backend_lan_ip(node: ProjectNode) -> str | None:
    """Return the attacker's IP on the BACKEND network.

    Mirrors communication_service._backend_lan_ip; duplicated here to
    avoid an import cycle (communication_service imports this file's
    neighbours for routing).
    """
    container_id = getattr(node, "container_id", None)
    if not container_id:
        return None
    try:
        from app.core.config import settings
        from app.core.docker_client import get_docker_client

        client = get_docker_client()
        c = client.containers.get(container_id)
        nets = c.attrs.get("NetworkSettings", {}).get("Networks", {}) or {}
        pref = nets.get(settings.BACKEND_NETWORK) or {}
        if pref.get("IPAddress"):
            return pref["IPAddress"]
        for _name, info in nets.items():
            if info.get("IPAddress"):
                return info["IPAddress"]
    except Exception:
        return None
    return None
