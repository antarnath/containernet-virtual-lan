"""Periodic heartbeat — tells the backend 'I'm alive'.

Phase 03: the payload now carries ``project_id`` if set, so the backend can
route this heartbeat into the right ``project_hosts`` row instead of the
legacy global ``hosts`` table.
"""

import asyncio
from datetime import datetime, timezone

import aiohttp

from config import config


async def send_heartbeat(session: aiohttp.ClientSession) -> None:
    payload = {
        "host_id": config.HOST_ID,
        "host_name": config.HOST_NAME,
        "host_ip": config.HOST_IP,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if config.PROJECT_ID:
        payload["project_id"] = config.PROJECT_ID

    try:
        async with session.post(
            f"{config.BACKEND_URL}/api/health",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=3),
        ) as resp:
            if resp.status == 200:
                print(f"[{config.HOST_NAME}] heartbeat OK")
            else:
                print(f"[{config.HOST_NAME}] heartbeat {resp.status}")
    except Exception as exc:
        # Backend not ready yet — log locally so we know the loop runs
        print(f"[{config.HOST_NAME}] heartbeat failed: {exc}")


async def run_heartbeat_loop() -> None:
    async with aiohttp.ClientSession() as session:
        while True:
            await send_heartbeat(session)
            await asyncio.sleep(config.HEARTBEAT_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(run_heartbeat_loop())