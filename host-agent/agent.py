"""Host Agent main entrypoint.

Runs the following subsystems concurrently:
  1. metrics_exporter    — aiohttp server on :9100 (/healthz, /metrics)
  2. message_service     — aiohttp server on :8080 (/send, /receive)
  3. health_monitor      — background loop POSTing heartbeats to backend
  4. attack_control      — only when AGENT_ROLE=attacker (M4 phase 06).
                           aiohttp server on :9092 exposing /state,
                           /attack, /attack/stop.

All servers share the same asyncio event loop. SIGTERM triggers
graceful shutdown.
"""

import asyncio
import logging
import signal

import attack_control
import attack_engine
import health_monitor
import message_service
import metrics_exporter
from config import config

# M4 phase 06 — without a handler, the engine's `log.info` calls
# go nowhere (Python's lastResort is WARNING+). Configure the root
# logger to print everything to stdout so `docker logs` shows the
# attack state.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)


async def main() -> None:
    role = config.AGENT_ROLE or "host"
    print(
        f"=== Host Agent starting for {config.HOST_NAME} ({config.HOST_IP}) "
        f"role={role} ==="
    )

    servers = [
        metrics_exporter.run_server(),
        message_service.run_server(),
        health_monitor.run_heartbeat_loop(),
    ]

    # M4 phase 06 — attackers also run the attack control server.
    # The engine is created here so its lifetime is tied to the agent;
    # the control server reads it via app["engine"].
    if role == "attacker":
        engine = attack_engine.AttackEngine()
        servers.append(
            attack_control.run_server(engine)
        )
        # Auto-start the attack if ATTACK_MODE was set at spawn time
        # (the backend's kind_env() copies the user's chosen mode
        # into the env). target_ip is left None — the engine runs in
        # the no-target modes (unknown_host) just fine, and the user
        # can hit /attack from the panel to set the target for the
        # other modes.
        if config.ATTACK_MODE:
            try:
                engine.start(config.ATTACK_MODE, target_ip="127.0.0.1")
            except Exception as exc:
                print(f"[{config.HOST_NAME}] auto-start failed: {exc}")

    await asyncio.gather(*servers)


def shutdown_handler(*_):
    print(f"[{config.HOST_NAME}] received shutdown signal")
    raise SystemExit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown_handler)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print(f"[{config.HOST_NAME}] agent stopped")