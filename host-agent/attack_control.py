"""Attack control HTTP server — :9092 endpoints the backend calls.

M4 phase 06. Three endpoints, all tiny:

  GET  /state           — current attack status (engine.snapshot())
  POST /attack          — start an attack: body {"mode", "target_ip"}
  POST /attack/stop     — stop any running attack

The server only starts when ``AGENT_ROLE=attacker`` is set (gated by
agent.py). The engine instance is created in agent.py and passed in.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import web

from attack_engine import AttackEngine

log = logging.getLogger(__name__)

# Port the backend hits. The backend's attack_proxy reaches this port
# over the shared backend bridge (10.10.0.0/24), so the bind on
# 0.0.0.0:9092 is correct.
CONTROL_PORT = 9092

# The 5 attack modes the engine understands. Kept here so the HTTP
# layer can validate the incoming body before forwarding.
ATTACK_MODES = {
    "unknown_host", "duplicate_ip", "arp_spoof", "tcp_flood",
    "http_flood",
}


async def run_server(engine: AttackEngine) -> None:
    """Start the control server. Runs forever (until cancelled)."""
    app = web.Application()
    app["engine"] = engine
    app.router.add_get("/state", _handle_get_state)
    app.router.add_post("/attack", _handle_post_attack)
    app.router.add_post("/attack/stop", _handle_post_attack_stop)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", CONTROL_PORT)
    await site.start()
    log.info("[attack_control] listening on :%d", CONTROL_PORT)
    # Sleep forever; the agent's main loop will cancel us.
    import asyncio
    while True:
        await asyncio.sleep(3600)


async def _handle_get_state(request: web.Request) -> web.Response:
    engine: AttackEngine = request.app["engine"]
    return web.json_response(engine.snapshot())


async def _handle_post_attack(request: web.Request) -> web.Response:
    engine: AttackEngine = request.app["engine"]
    try:
        body: dict[str, Any] = await request.json()
    except (json.JSONDecodeError, Exception):
        return web.json_response(
            {"ok": False, "error": "invalid JSON body"}, status=400
        )
    mode = body.get("mode")
    target_ip = body.get("target_ip")
    if not mode or mode not in ATTACK_MODES:
        return web.json_response(
            {"ok": False, "error": f"mode must be one of {sorted(ATTACK_MODES)}"},
            status=400,
        )
    if not target_ip or not isinstance(target_ip, str):
        return web.json_response(
            {"ok": False, "error": "target_ip required"}, status=400
        )
    try:
        engine.start(mode, target_ip)
    except Exception as exc:
        log.exception("[attack_control] start failed: %s", exc)
        return web.json_response(
            {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )
    return web.json_response({"ok": True, "state": engine.snapshot()})


async def _handle_post_attack_stop(request: web.Request) -> web.Response:
    engine: AttackEngine = request.app["engine"]
    try:
        engine.stop()
    except Exception as exc:
        log.exception("[attack_control] stop failed: %s", exc)
        return web.json_response(
            {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )
    return web.json_response({"ok": True, "state": engine.snapshot()})
