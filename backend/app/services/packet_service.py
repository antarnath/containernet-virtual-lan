"""Packet service — M4 phase 04 (wire view per link).

The capture container for each link writes one NDJSON line per packet
to ``/var/lib/containernet/captures/<link_capture_name>.ndjson``.
This module:

  * classifies each packet's protocol (TCP/UDP/ICMP/ARP/HTTP/other)
  * tags each packet with the ``src_node_kind`` of the node that sent
    it (looked up by src_mac against a per-project MAC table built
    once at start time)
  * streams those events to the browser over Server-Sent Events

The classifier runs here (not in the capture shim) so the wire view
and the canvas dot animation agree on the same canonical protocol
label regardless of which container the packet came through.

Threading: the file tail runs in a background thread (one per SSE
client) so the event loop is never blocked. Cancellation is handled
by the consumer closing the generator.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.core.docker_client import get_docker_client

log = logging.getLogger(__name__)


# ─── protocol classifier ───────────────────────────────────────────────
# The shim already labels each packet with the L4 protocol name
# ("TCP", "UDP", "ICMP") and a separate L7 block for HTTP. We turn
# that into the small set the design system cares about.

PROTO_TCP = "tcp"
PROTO_UDP = "udp"
PROTO_ICMP = "icmp"
PROTO_ARP = "arp"
PROTO_HTTP = "http"
PROTO_OTHER = "other"

VALID_PROTOCOLS = {PROTO_TCP, PROTO_UDP, PROTO_ICMP, PROTO_ARP, PROTO_HTTP, PROTO_OTHER}


def classify_protocol(pkt: dict) -> str:
    """Return one of tcp / udp / icmp / arp / http / other.

    Inspects the shim's parsed packet:
      * pkt["l3"]["protocol_name"] in {"TCP","UDP","ICMP"}
      * pkt["l7"] is present and is_request / is_response for HTTP
      * pkt["l2"]["ethertype_name"] == "ARP" → arp
    """
    if not isinstance(pkt, dict):
        return PROTO_OTHER
    l2 = pkt.get("l2") or {}
    if l2.get("ethertype_name") == "ARP":
        return PROTO_ARP
    l3 = pkt.get("l3") or {}
    name = (l3.get("protocol_name") or "").upper()
    l4 = pkt.get("l4") or {}
    l7 = pkt.get("l7")
    if name == "TCP":
        if l7 and (l7.get("is_request") or l7.get("is_response")):
            return PROTO_HTTP
        return PROTO_TCP
    if name == "UDP":
        # Best-effort HTTP sniff for UDP-based protocols (rare on
        # the wire view but cheap to check).
        if l4.get("dst_port") in (80, 8080) or l4.get("src_port") in (80, 8080):
            return PROTO_HTTP
        return PROTO_UDP
    if name == "ICMP":
        return PROTO_ICMP
    return PROTO_OTHER


# ─── MAC table (per project, per process) ──────────────────────────────
# {project_id: {mac: node_kind}}
# Built once at start time from `docker inspect` of every node
# container. The veth at the host side carries the node's MAC —
# same MAC the bridge sees. Invalidated on stop.

_mac_tables: dict[str, dict[str, str]] = {}


def get_project_mac_table(project_id: str) -> dict[str, str]:
    """Return {mac: node_kind} for every node in the project.

    Lazily builds the table by inspecting each node container. Called
    by the packet streamer when a packet's src_mac is unknown.
    """
    table = _mac_tables.get(project_id)
    if table is not None:
        return table
    table = _build_mac_table(project_id)
    _mac_tables[project_id] = table
    return table


def _build_mac_table(project_id: str) -> dict[str, str]:
    """Build {mac: node_kind} by inspecting every node container.

    The MAC we want is the container's eth0 (or first interface)
    MAC — that's what the bridge sees as the source MAC of the
    frame the container emitted.
    """
    client = get_docker_client()
    out: dict[str, str] = {}
    try:
        containers = client.containers.list(
            all=True,
            filters={"label": f"containernet.project={project_id}"},
        )
    except Exception as exc:
        log.warning("[packet_service] list containers for MAC table failed: %s", exc)
        return out
    for c in containers:
        try:
            attrs = c.attrs
        except Exception:
            continue
        # The node kind is stored in the ``containernet.role`` label
        # (set by node_service.spawn_node when it spawns each kind).
        # Fall back to "" if absent.
        labels = attrs.get("Config", {}).get("Labels") or {}
        kind = labels.get("containernet.role", "")
        # Gather every MAC across every interface.
        net_settings = attrs.get("NetworkSettings", {}) or {}
        ifaces = net_settings.get("Interfaces") or {}
        for _name, info in ifaces.items():
            mac = (info or {}).get("MacAddress") or ""
            if mac:
                out[mac.lower()] = kind
        # Also include the per-interface MacAddress from the legacy
        # "Networks.<net>.MacAddress" (older Docker API shape).
        nets = net_settings.get("Networks") or {}
        for _name, info in nets.items():
            mac = (info or {}).get("MacAddress") or ""
            if mac:
                out[mac.lower()] = kind
    log.info(
        "[packet_service] built MAC table for project %s: %d entries",
        project_id[:8], len(out),
    )
    return out


def invalidate_project(project_id: str) -> None:
    """Drop the cached MAC table. Called by the lifecycle on stop."""
    _mac_tables.pop(project_id, None)


# ─── capture file path resolution ──────────────────────────────────────
# M4 phase 04 — the per-link NDJSON file is written by every node
# container that has an interface on the link (see
# node_service.spawn_node). The path is stable and derived from
# project id + link id; no need to look up a sidecar container.

_capture_path_cache: dict[str, str] = {}


def _link_capture_filename(project_id: str, link_id: str) -> str:
    """Stable per-link filename. Matches the convention used by
    node_service._link_capture_filename (and the node entrypoint's
    capture command)."""
    short_p = project_id.replace("-", "")[:8]
    short_l = link_id.replace("-", "")[:4]
    return f"{short_p}l{short_l}"


def resolve_capture_path(project_id: str, link_id: str) -> str | None:
    """Return the absolute NDJSON file path for a link's capture."""
    cached = _capture_path_cache.get(link_id)
    if cached and os.path.exists(cached):
        return cached

    path = (
        f"/var/lib/containernet/captures/"
        f"{_link_capture_filename(project_id, link_id)}.ndjson"
    )
    if os.path.exists(path):
        _capture_path_cache[link_id] = path
        return path
    return None


# ─── packet event shape ────────────────────────────────────────────────

@dataclass
class PacketEvent:
    """Wire-shape packet event sent to the browser."""
    id: int
    ts: str
    ts_ns: int
    link_id: str
    protocol: str  # tcp / udp / icmp / arp / http / other
    src_node_kind: str  # host / switch / router / server / attacker / ""
    src_mac: str
    dst_mac: str
    src_ip: str
    dst_ip: str
    src_port: int | None
    dst_port: int | None
    length: int
    summary: str
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "ts_ns": self.ts_ns,
            "link_id": self.link_id,
            "protocol": self.protocol,
            "src_node_kind": self.src_node_kind,
            "src_mac": self.src_mac,
            "dst_mac": self.dst_mac,
            "src_ip": self.src_ip,
            "dst_ip": self.dst_ip,
            "src_port": self.src_port,
            "dst_port": self.dst_port,
            "length": self.length,
            "summary": self.summary,
        }


# ─── stream (the SSE consumer side) ────────────────────────────────────

async def stream_packets_for_link(
    project_id: str,
    link_id: str,
) -> AsyncIterator[dict]:
    """Async-iterate PacketEvent dicts for a single link.

    Tails the link's NDJSON file: reads new lines as they appear
    (the capture shim flushes after every packet), parses each into
    a PacketEvent, augments with src_node_kind from the project's
    MAC table, and yields. When the consumer cancels (e.g. the
    browser closes the SSE), the file handle is closed cleanly.
    """
    path = resolve_capture_path(project_id, link_id)
    if not path:
        # File doesn't exist yet (capture container still spinning
        # up). Poll briefly so we don't error out before the first
        # packet arrives.
        for _ in range(20):
            await asyncio.sleep(0.5)
            path = resolve_capture_path(project_id, link_id)
            if path:
                break
    if not path:
        log.warning(
            "[packet_service] no capture file for link %s in project %s",
            link_id, project_id,
        )
        return

    # Build (or reuse) the MAC table for src_node_kind lookups.
    mac_table = get_project_mac_table(project_id)

    # The file tail runs in a thread (blocking I/O) so we don't
    # stall the asyncio loop. We poll every 100ms — fast enough
    # for "live" feel, slow enough to be cheap.
    last_pos = 0
    last_size = 0
    try:
        last_size = os.path.getsize(path)
        last_pos = last_size  # start at the end — only forward
    except OSError:
        last_pos = 0

    log.info(
        "[packet_service] tailing %s for link %s (start at %d bytes)",
        path, link_id, last_pos,
    )

    while True:
        try:
            cur_size = os.path.getsize(path)
        except OSError:
            await asyncio.sleep(0.2)
            continue
        if cur_size < last_pos:
            # File was truncated/rotated. Start over from 0.
            log.info(
                "[packet_service] capture file %s rotated; restarting from 0",
                path,
            )
            last_pos = 0
        if cur_size > last_pos:
            new_bytes = await asyncio.to_thread(
                _read_range, path, last_pos, cur_size
            )
            last_pos = cur_size
            for line in new_bytes.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ev = _to_event(raw, link_id, mac_table)
                if ev is not None:
                    yield ev.to_dict()
        else:
            await asyncio.sleep(0.1)


def _read_range(path: str, start: int, end: int) -> bytes:
    """Read bytes [start, end) from `path` (sync; runs in a thread)."""
    with open(path, "rb") as f:
        f.seek(start)
        return f.read(end - start)


def _to_event(raw: dict, link_id: str, mac_table: dict[str, str]) -> PacketEvent | None:
    """Turn a shim-emitted JSON object into a PacketEvent."""
    if not isinstance(raw, dict):
        return None
    l2 = raw.get("l2") or {}
    l3 = raw.get("l3") or {}
    l4 = raw.get("l4") or {}
    src_mac = (l2.get("src_mac") or "").lower()
    src_ip = l3.get("src_ip") or ""
    proto = classify_protocol(raw)
    src_kind = mac_table.get(src_mac, "")
    src_port = l4.get("src_port") if isinstance(l4, dict) else None
    dst_port = l4.get("dst_port") if isinstance(l4, dict) else None
    try:
        pkt_id = int(raw.get("id") or 0)
    except (TypeError, ValueError):
        pkt_id = 0
    return PacketEvent(
        id=pkt_id,
        ts=raw.get("ts") or "",
        ts_ns=int(raw.get("ts_ns") or 0),
        link_id=link_id,
        protocol=proto,
        src_node_kind=src_kind,
        src_mac=src_mac,
        dst_mac=(l2.get("dst_mac") or "").lower(),
        src_ip=src_ip,
        dst_ip=l3.get("dst_ip") or "",
        src_port=src_port,
        dst_port=dst_port,
        length=int(raw.get("len") or 0),
        summary=raw.get("summary") or "",
        raw=raw,
    )


# ─── recent-packets snapshot (for canvas dot animation) ───────────────
# A small ring buffer of the most recent N packets per link, keyed
# by (project_id, link_id). The canvas animation reads from this
# (no SSE needed for the dot — just a poll every 1s).

_recent_max = 32
_recent: dict[tuple[str, str], list[dict]] = {}


def remember_packet(project_id: str, ev: PacketEvent) -> None:
    """Add an event to the project's recent-packets ring buffer."""
    key = (project_id, ev.link_id)
    bucket = _recent.setdefault(key, [])
    bucket.append(ev.to_dict())
    if len(bucket) > _recent_max:
        bucket = bucket[-_recent_max:]
        _recent[key] = bucket


def get_recent_packets(project_id: str, link_id: str | None = None, limit: int = 20) -> list[dict]:
    """Return recent packets for one link (or all links in the project)."""
    out: list[dict] = []
    if link_id is not None:
        out = list(_recent.get((project_id, link_id), []))
    else:
        for v in _recent.values():
            out.extend(v)
    out.sort(key=lambda p: p.get("ts_ns") or 0)
    return out[-limit:]


def reset_recent(project_id: str) -> None:
    """Drop cached recent packets for a project (called on stop)."""
    keys = [k for k in _recent if k[0] == project_id]
    for k in keys:
        _recent.pop(k, None)


# ─── sync stream wrapper (the file tail) ──────────────────────────────
# The SSE endpoint needs a *sync* generator to feed StreamingResponse
# without making the asyncio loop block on the file poll. We adapt
# the async stream into a sync one by running a small thread loop.

def sync_iter_packets(
    project_id: str,
    link_id: str,
    stop_event: Any,
) -> Any:
    """Sync iterator over PacketEvent dicts for a single link.

    Used by FastAPI's StreamingResponse (which is sync). The
    iterator polls the NDJSON file on a short interval; it stops
    when ``stop_event.is_set()`` is True (e.g. the client
    disconnected). Cancellation is cooperative.
    """
    path = resolve_capture_path(project_id, link_id)
    if not path:
        # Capture hasn't started yet — wait up to 10s for the file
        # to appear before giving up.
        for _ in range(50):
            if stop_event.is_set():
                return
            time.sleep(0.2)
            path = resolve_capture_path(project_id, link_id)
            if path:
                break
    if not path:
        return

    mac_table = get_project_mac_table(project_id)

    last_pos = 0
    try:
        last_pos = os.path.getsize(path)
    except OSError:
        last_pos = 0

    while not stop_event.is_set():
        try:
            cur_size = os.path.getsize(path)
        except OSError:
            time.sleep(0.2)
            continue
        if cur_size < last_pos:
            last_pos = 0  # rotated
        if cur_size > last_pos:
            try:
                with open(path, "rb") as f:
                    f.seek(last_pos)
                    chunk = f.read(cur_size - last_pos)
            except OSError:
                time.sleep(0.2)
                continue
            last_pos = cur_size
            for line in chunk.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ev = _to_event(raw, link_id, mac_table)
                if ev is not None:
                    remember_packet(project_id, ev)
                    yield ev.to_dict()
        else:
            time.sleep(0.1)
