"""HTTP server exposing host health and Prometheus-format metrics.

Routes:
  GET /healthz  -> JSON identity
  GET /metrics  -> Prometheus text format (CPU, RAM, network, uptime)

Listens on 0.0.0.0:METRICS_PORT so it's reachable from inside the LAN.
"""

import asyncio
import time

from aiohttp import web
from prometheus_client import (
    CollectorRegistry,
    Gauge,
    generate_latest,
)
import psutil

from config import config


REGISTRY = CollectorRegistry()

CPU_USAGE = Gauge("host_cpu_usage_percent", "CPU usage %", registry=REGISTRY)
MEM_USAGE = Gauge("host_memory_usage_percent", "Memory usage %", registry=REGISTRY)
NET_RX = Gauge("host_network_rx_bytes_total", "Bytes received", registry=REGISTRY)
NET_TX = Gauge("host_network_tx_bytes_total", "Bytes sent", registry=REGISTRY)
UPTIME = Gauge("host_uptime_seconds", "Seconds since boot", registry=REGISTRY)
HOST_BOOT_TIME = psutil.boot_time()


async def healthz(_request: web.Request) -> web.Response:
    """Liveness check — returns 200 with host identity if the agent is alive."""
    return web.json_response({
        "status": "ok",
        "host_id": config.HOST_ID,
        "host_name": config.HOST_NAME,
        "host_ip": config.HOST_IP,
        "ts": time.time(),
    })


async def metrics(_request: web.Request) -> web.Response:
    """Return Prometheus-format metrics for this host."""
    CPU_USAGE.set(psutil.cpu_percent(interval=0.1))
    MEM_USAGE.set(psutil.virtual_memory().percent)
    net = psutil.net_io_counters()
    NET_RX.set(net.bytes_recv)
    NET_TX.set(net.bytes_sent)
    UPTIME.set(time.time() - HOST_BOOT_TIME)

    body = generate_latest(REGISTRY)
    # newer prometheus_client embeds charset in CONTENT_TYPE_LATEST;
    # aiohttp 3.x rejects passing a content_type that includes a charset,
    # so we set the Content-Type header directly instead.
    return web.Response(
        body=body,
        headers={"Content-Type": "text/plain; version=0.0.4; charset=utf-8"},
    )


async def run_server() -> None:
    app = web.Application()
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/metrics", metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.METRICS_PORT)
    await site.start()
    print(f"[{config.HOST_NAME}] metrics server listening on :{config.METRICS_PORT}")


if __name__ == "__main__":
    asyncio.run(run_server())