"""Host Agent main entrypoint.

Runs three subsystems concurrently:
  1. metrics_exporter  — aiohttp server on :9100 (/healthz, /metrics)
  2. message_service   — aiohttp server on :8080 (stub in Phase 02, real in Phase 05)
  3. health_monitor    — background loop POSTing heartbeats to backend

All three share the same asyncio event loop. SIGTERM triggers graceful shutdown.
"""

import asyncio
import signal

import health_monitor
import message_service
import metrics_exporter
from config import config


async def main() -> None:
    print(f"=== Host Agent starting for {config.HOST_NAME} ({config.HOST_IP}) ===")

    await asyncio.gather(
        metrics_exporter.run_server(),
        message_service.run_server(),
        health_monitor.run_heartbeat_loop(),
    )


def shutdown_handler(*_):
    print(f"[{config.HOST_NAME}] received shutdown signal")
    raise SystemExit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown_handler)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print(f"[{config.HOST_NAME}] agent stopped")