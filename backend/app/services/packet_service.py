"""Packet service — read packet events from a project's capture container.

The capture container runs `tcpdump | capture_shim.py > $CAPTURE_FILE`.
This service reads that NDJSON file via `docker exec cat` and returns events.

Two consumers:
  * REST replay (`get_packets`)  — returns events with id > since.
  * SSE stream (`iter_packets`)  — long-poll loop that yields new events
                                   as they appear in the file.

The capture container runs in the host network namespace but writes its
NDJSON output to a path bind-mounted from the host, so `docker exec cat`
still works to read it. We keep the cursor (last-seen id) on the
consumer side so two callers don't fight each other.
"""

from __future__ import annotations

import json
import time
from typing import Iterator

import docker
from docker.errors import APIError, NotFound

from app.core.docker_client import get_docker_client
from app.services import container_service


# Path inside the capture container where the shim writes NDJSON.
# Configurable via the CAPTURE_FILE env var on the capture container
# (default: /tmp/capture.ndjson, set to /var/lib/containernet/...
# when host-bind-mounted for persistence).
CAPTURE_FILE = "/tmp/capture.ndjson"


def get_capture_container_id(project_id: str) -> str | None:
    """Return the capture container's ID for a project, or None."""
    info = container_service.get_project_capture_container(project_id)
    if info is None:
        return None
    return info["id"]


def _exec_read_ndjson(container_id: str, since_bytes: int = 0) -> str:
    """Read the NDJSON output file from the capture container.

    We don't use `tail -c +N` because that requires the file to exist
    and the container to have busybox coreutils-tail. We just `cat`
    the file and slice in Python.

    The capture container sets $CAPTURE_FILE to point at its
    host-bind-mounted NDJSON output path; we honour that env var so we
    read from the same location the shim writes to.
    """
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
    except NotFound:
        raise FileNotFoundError("capture container not found")
    if container.status != "running":
        raise RuntimeError(f"capture container not running ({container.status})")
    # Honour $CAPTURE_FILE if the container was started with one;
    # otherwise fall back to the in-container default.
    env = container.attrs.get("Config", {}).get("Env", []) or []
    capture_path = CAPTURE_FILE
    for entry in env:
        if entry.startswith("CAPTURE_FILE="):
            capture_path = entry.split("=", 1)[1]
            break
    exec_result = container.exec_run(
        ["cat", capture_path],
        stdout=True,
        stderr=True,
        stream=False,
    )
    if exec_result.exit_code != 0:
        stderr = exec_result.output.decode("utf-8", errors="replace")
        # Missing file is normal before the first packet arrives.
        if "No such file" in stderr or "not found" in stderr.lower():
            return ""
        raise RuntimeError(f"capture exec failed: {stderr}")
    return exec_result.output.decode("utf-8", errors="replace")


def get_packets(project_id: str, since: int = 0, limit: int = 1000) -> list[dict]:
    """Return PacketEvents from the project's capture with id > since."""
    container_id = get_capture_container_id(project_id)
    if container_id is None:
        raise LookupError("no capture container for this project")
    raw = _exec_read_ndjson(container_id)
    if not raw:
        return []
    out: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("id", 0) > since:
            out.append(event)
    # The file is append-only and IDs are monotonic, so it's already
    # roughly time-ordered, but we sort defensively.
    out.sort(key=lambda e: e.get("id", 0))
    if limit and len(out) > limit:
        out = out[:limit]
    return out


def iter_packets(
    project_id: str,
    since: int = 0,
    poll_interval_s: float = 0.1,
    heartbeat_s: float = 15.0,
) -> Iterator[tuple[str, dict | None]]:
    """Yield ("event", event) tuples from the project's capture container.

    Polls every ``poll_interval_s`` seconds. If no new packets arrive
    within ``heartbeat_s`` seconds, yields a ``(":hb", None)`` tuple so
    SSE consumers can keep their connection alive.

    Yields ``("reset", None)`` if the capture container disappears.
    """
    cursor = since
    last_data = time.monotonic()
    while True:
        try:
            events = get_packets(project_id, since=cursor, limit=50)
        except (LookupError, FileNotFoundError, RuntimeError):
            yield ("reset", None)
            return
        except Exception:
            yield ("reset", None)
            return
        if events:
            for e in events:
                cursor = max(cursor, e.get("id", cursor))
                yield ("event", e)
            last_data = time.monotonic()
        else:
            now = time.monotonic()
            if now - last_data >= heartbeat_s:
                yield (":hb", None)
                last_data = now
        time.sleep(poll_interval_s)
