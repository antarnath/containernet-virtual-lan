"""Router proxy — fetches live state from a router container's :9090 agent.

M4 phase 03. The router agent (router-agent/agent.py, running inside
each router container) exposes its routing table, ARP table, and
interface state over a tiny HTTP API. The backend's
``router_proxy`` module:

  1. Discovers the router container's IP on the backend network by
     reading the container's ``NetworkSettings.Networks`` (so the
     panel can call ``http://<ip>:9090/state/routes`` etc.).
  2. Caches responses in-process for 1.5s (the panel polls every 2s;
     the cache prevents a thundering herd if many panels mount).
  3. On the first poll, takes a snapshot of the ARP table. On every
     subsequent poll, diffs against the snapshot. Any change is
     recorded as an AnomalyEvent row and broadcast over the project's
     WebSocket.

This module is the read-side companion to ``node_service.spawn_node``
which set up the agent. The write-side (configuring routes from
the panel) will land in a later phase — phase 03 is read-only.

Threading: this module uses ``asyncio`` exclusively. The HTTP
client is ``urllib.request`` (stdlib) so we don't pull in
``httpx`` / ``aiohttp`` just for this.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from app.core.docker_client import get_docker_client

log = logging.getLogger(__name__)

# How long to cache a router-state response before re-fetching. The
# panel polls every 2s; 1.5s means a second panel mounting on the
# same router within 2s gets the same data without hitting the agent.
CACHE_TTL_SEC = 1.5

# How long the urllib request to the agent is allowed to take.
# 2s is plenty for a `ip route` dump; anything longer and the
# router is probably wedged.
HTTP_TIMEOUT_SEC = 2.0


# ─── data shapes ───────────────────────────────────────────────────────

@dataclass
class RouteEntry:
    destination: str
    gateway: str
    iface: str
    protocol: str
    scope: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {
            "destination": self.destination,
            "gateway": self.gateway,
            "iface": self.iface,
            "protocol": self.protocol,
            "scope": self.scope,
            "source": self.source,
        }


@dataclass
class NeighEntry:
    ip: str
    iface: str
    mac: str
    state: str
    age: str

    def to_dict(self) -> dict[str, str]:
        return {
            "ip": self.ip,
            "iface": self.iface,
            "mac": self.mac,
            "state": self.state,
            "age": self.age,
        }


@dataclass
class IfaceEntry:
    name: str
    state: str
    ip_mask: str
    mac: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "state": self.state,
            "ip_mask": self.ip_mask,
            "mac": self.mac,
        }


@dataclass
class RouterState:
    routes: list[RouteEntry] = field(default_factory=list)
    neigh: list[NeighEntry] = field(default_factory=list)
    ifaces: list[IfaceEntry] = field(default_factory=list)
    fetched_at: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "routes": [r.to_dict() for r in self.routes],
            "neigh": [n.to_dict() for n in self.neigh],
            "ifaces": [i.to_dict() for i in self.ifaces],
            "fetched_at": self.fetched_at,
            "error": self.error,
        }


# ─── in-process cache ─────────────────────────────────────────────────

# Keyed by node_id (the ProjectNode row's UUID). The cache holds
# (state, expiry_monotonic). Reads check expiry and re-fetch on miss.
_cache: dict[str, tuple[RouterState, float]] = {}


def _cache_get(node_id: str) -> RouterState | None:
    entry = _cache.get(node_id)
    if entry is None:
        return None
    state, expiry = entry
    if time.monotonic() > expiry:
        return None
    return state


def _cache_put(node_id: str, state: RouterState) -> None:
    _cache[node_id] = (state, time.monotonic() + CACHE_TTL_SEC)


def _cache_invalidate(node_id: str) -> None:
    _cache.pop(node_id, None)


# ─── public API ───────────────────────────────────────────────────────

async def get_router_state(node_id: str, container_id: str | None) -> RouterState:
    """Return the cached or freshly-fetched RouterState for a node.

    If the container isn't running (container_id is None or the
    HTTP call fails), returns a RouterState with ``error`` set and
    empty lists. The panel handles the error case gracefully.
    """
    cached = _cache_get(node_id)
    if cached is not None:
        return cached

    if not container_id:
        return RouterState(error="container not running", fetched_at=time.time())

    # Run the blocking HTTP fetch in a thread so we don't stall
    # the event loop (urllib is sync).
    try:
        state = await asyncio.to_thread(_fetch_all, container_id)
    except Exception as exc:
        log.warning("[router_proxy] fetch failed for %s: %s", node_id, exc)
        state = RouterState(error=str(exc), fetched_at=time.time())

    _cache_put(node_id, state)
    return state


def invalidate(node_id: str) -> None:
    """Drop the cached state for a node. Called when the container
    is restarted (the new container has a different IP / state)."""
    _cache_invalidate(node_id)


# ─── write-side (route installation) ───────────────────────────────────
# Used by route_installer.py to push static routes into a router
# container's kernel via the agent's ``POST /routes`` endpoint.
# The agent runs ``ip route replace …`` server-side, so a success
# means the route is in the kernel immediately and survives until
# the container is stopped.

@dataclass
class RouteInstallResult:
    ok: bool
    error: str | None = None
    route: str | None = None  # The route string the agent installed


async def set_route(
    container_id: str | None,
    *,
    dst: str,
    via: str | None = None,
    dev: str | None = None,
) -> RouteInstallResult:
    """Install (or replace) a static route in a router's kernel.

    Wraps the agent's ``POST /routes`` handler. ``via`` may be
    omitted for directly-attached subnets (rare — most routes
    installed by the system will have a via). The agent's
    ``ip route replace`` makes the call idempotent: re-installing
    the same route is a no-op.

    Retries briefly on connection-refused: right after
    ``containers.run`` the agent's HTTP server may not be bound
    yet. The retries cover the typical agent-startup race without
    blocking the start path for more than a couple of seconds.

    Returns a ``RouteInstallResult`` with ``ok=True`` on a 2xx
    response from the agent. Network/timeout errors return
    ``ok=False`` with the exception message; the caller decides
    whether to retry or log-and-continue.
    """
    if not container_id:
        return RouteInstallResult(ok=False, error="no container_id")
    url = agent_url(container_id, "/routes")
    if not url:
        # Container may not be attached to a routable network yet
        # (the attach call finished but the veth hasn't come up).
        # Wait briefly and try again — we want to install routes
        # before the project returns to the user.
        for _ in range(5):
            await asyncio.sleep(0.3)
            url = agent_url(container_id, "/routes")
            if url:
                break
    if not url:
        return RouteInstallResult(ok=False, error="agent unreachable")
    body = json.dumps({"dst": dst, "via": via, "dev": dev}).encode("utf-8")
    # Retry the POST itself briefly to ride out the agent-startup
    # race. ``ip route replace`` is idempotent so retrying on a
    # transient refusal is safe.
    last: RouteInstallResult | None = None
    for attempt in range(5):
        result = await asyncio.to_thread(_post_json, url, body)
        if result.ok:
            return result
        last = result
        # Only retry on connection-level errors, not on the agent
        # explicitly returning ok=False (those won't fix themselves).
        err = (result.error or "").lower()
        if "refused" not in err and "timeout" not in err and "reset" not in err:
            return result
        await asyncio.sleep(0.3)
    return last or RouteInstallResult(ok=False, error="unknown")


def _post_json(url: str, body: bytes) -> RouteInstallResult:
    """Blocking POST. Runs inside ``asyncio.to_thread``."""
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            payload = resp.read().decode("utf-8", errors="replace") or "{}"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return RouteInstallResult(ok=False, error=str(exc))
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        parsed = {}
    if parsed.get("ok"):
        return RouteInstallResult(ok=True, route=parsed.get("route"))
    return RouteInstallResult(ok=False, error=parsed.get("error", "unknown error"))


# ─── HTTP fetch + parse ───────────────────────────────────────────────

def agent_url(container_id: str, path: str = "") -> str | None:
    """Compute the router agent's URL for a container.

    Public helper so other services (e.g. ``route_installer``) can
    reach the same :9090 endpoint the panel uses. Returns ``None``
    if the container isn't reachable from the backend (e.g. missing
    or not attached to any routable network).

    We use the container's IP on the BACKEND_NETWORK so we can reach
    :9090 from the backend container. The default `bridge` (docker0)
    is reachable too but its IP isn't stable across reattaches, so
    we prefer the explicit backend network. Per-link bridge IPs would
    also work, but the backend isn't attached to those.

    The preferred network name is read from settings.BACKEND_NETWORK
    (e.g. ``containernet_containernet_lan``). If the container
    isn't attached to that network, we fall back to the first
    attached network with an IP.
    """
    from app.core.config import settings
    client = get_docker_client()
    try:
        c = client.containers.get(container_id)
    except Exception:
        return None
    nets = c.attrs.get("NetworkSettings", {}).get("Networks", {}) or {}
    preferred = settings.BACKEND_NETWORK
    # First try the preferred network.
    pref = nets.get(preferred) or {}
    if pref.get("IPAddress"):
        return f"http://{pref['IPAddress']}:9090{path}"
    # Fall back: any attached network with an IP.
    for net_name, net_info in nets.items():
        if net_name == preferred:
            continue
        ip = net_info.get("IPAddress")
        if ip:
            return f"http://{ip}:9090{path}"
    return None


def _agent_url(container_id: str, path: str) -> str | None:
    """Backwards-compatible alias for the public ``agent_url``."""
    return agent_url(container_id, path)


def _fetch_all(container_id: str) -> RouterState:
    """Blocking — fetch routes / neigh / ifaces from the agent.

    Tries ``/state/all`` first (one round-trip, JSON response) and
    falls back to the three separate ``/state/*`` endpoints if the
    combined one isn't available. The fallback also handles the
    plain-text vs JSON choice per-endpoint.
    """
    state = RouterState(fetched_at=time.time())

    # Combined endpoint — preferred.
    all_text = _http_get_text(_agent_url(container_id, "/state/all"))
    if all_text is not None:
        try:
            payload = json.loads(all_text)
            state.routes = _parse_routes(payload.get("routes") or "")
            state.neigh = _parse_neigh(payload.get("neigh") or "")
            state.ifaces = _parse_ifaces(payload.get("ifaces") or "")
            return state
        except (json.JSONDecodeError, TypeError):
            # Fall through to per-endpoint fetches.
            pass

    # Per-endpoint fallback.
    routes_text = _http_get_text(_agent_url(container_id, "/state/routes"))
    if routes_text is not None:
        state.routes = _parse_routes(routes_text)

    neigh_text = _http_get_text(_agent_url(container_id, "/state/neigh"))
    if neigh_text is not None:
        state.neigh = _parse_neigh(neigh_text)

    ifaces_text = _http_get_text(_agent_url(container_id, "/state/ifaces"))
    if ifaces_text is not None:
        state.ifaces = _parse_ifaces(ifaces_text)

    return state


def _http_get_text(url: str | None) -> str | None:
    """GET a URL and return the response body, or None on error."""
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_SEC) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        log.debug("[router_proxy] HTTP %s failed: %s", url, exc)
        return None


# ─── parsers ──────────────────────────────────────────────────────────

def _parse_routes(text: str) -> list[RouteEntry]:
    """Parse `ip -j route` JSON output into RouteEntry list.

    The agent uses ``ip -j route`` which returns a JSON array.
    We gracefully fall back to ``ip route`` plain text if the
    JSON output is empty (e.g. inside a minimal Alpine image
    where ``ip -j`` isn't available).
    """
    text = text.strip()
    if not text:
        return []
    # Try JSON first.
    if text.startswith("["):
        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            items = []
        out: list[RouteEntry] = []
        for it in items:
            out.append(RouteEntry(
                destination=it.get("dst", "default") or "default",
                gateway=it.get("gateway", "") or "",
                iface=it.get("dev", "") or "",
                protocol=it.get("protocol", "") or "",
                scope=it.get("scope", "") or "",
                source=it.get("prefsrc", "") or "",
            ))
        return out
    # Plain text fallback.
    return _parse_routes_text(text)


def _parse_routes_text(text: str) -> list[RouteEntry]:
    out: list[RouteEntry] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Example lines:
        #   default via 10.0.0.1 dev eth0
        #   10.0.0.0/24 dev eth1 proto kernel scope link src 10.0.0.2
        parts = line.split()
        try:
            entry = RouteEntry(
                destination=parts[0] if parts else "",
                gateway=_kw(parts, "via"),
                iface=_kw(parts, "dev"),
                protocol=_kw(parts, "proto"),
                scope=_kw(parts, "scope"),
                source=_kw(parts, "src"),
            )
        except Exception:
            continue
        out.append(entry)
    return out


def _kw(parts: list[str], key: str) -> str:
    """Look up ``key <value>`` in a list of words; return '' if missing."""
    for i, w in enumerate(parts):
        if w == key and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def _parse_neigh(text: str) -> list[NeighEntry]:
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            items = []
        out: list[NeighEntry] = []
        for it in items:
            lladdr = (it.get("lladdr") or "").lower()
            out.append(NeighEntry(
                ip=it.get("dst", "") or "",
                iface=it.get("dev", "") or "",
                mac=lladdr,
                state=it.get("state", "") or "",
                age=str(it.get("age", "") or ""),
            ))
        return out
    return _parse_neigh_text(text)


def _parse_neigh_text(text: str) -> list[NeighEntry]:
    """Parse `ip neigh` plain text. The lines look like:
        10.0.0.1 dev eth1 lladdr 02:42:0a:00:00:01 REACHABLE
        10.0.0.3 dev eth1 INCOMPLETE
    """
    out: list[NeighEntry] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        ip = parts[0]
        try:
            dev_i = parts.index("dev")
            iface = parts[dev_i + 1] if dev_i + 1 < len(parts) else ""
        except ValueError:
            iface = ""
        try:
            ll_i = parts.index("lladdr")
            mac = parts[ll_i + 1].lower() if ll_i + 1 < len(parts) else ""
        except ValueError:
            mac = ""
        # State is the last token (REACHABLE, STALE, DELAY, etc.)
        # or "INCOMPLETE" when no lladdr.
        state = parts[-1] if parts[-1] not in (ip, iface) else ""
        out.append(NeighEntry(
            ip=ip, iface=iface, mac=mac, state=state, age="",
        ))
    return out


def _parse_ifaces(text: str) -> list[IfaceEntry]:
    text = text.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            items = []
        out: list[IfaceEntry] = []
        for it in items:
            addrs = it.get("addr_info") or []
            ip_mask = ""
            for a in addrs:
                if a.get("family") == "inet":
                    ip = a.get("local", "")
                    plen = a.get("prefixlen", "")
                    if ip:
                        ip_mask = f"{ip}/{plen}" if plen else ip
                        break
            out.append(IfaceEntry(
                name=it.get("ifname", "") or "",
                state=it.get("operstate", "") or it.get("state", "") or "",
                ip_mask=ip_mask,
                mac=(it.get("address") or "").lower(),
            ))
        return out
    return _parse_ifaces_text(text)


def _parse_ifaces_text(text: str) -> list[IfaceEntry]:
    """Parse `ip -br addr` output. Lines look like:
        eth0   UP    10.0.0.1/24 02:42:0a:00:00:01
        lo     UNKNOWN 127.0.0.1/8 ::
    """
    out: list[IfaceEntry] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        out.append(IfaceEntry(
            name=parts[0],
            state=parts[1] if len(parts) > 1 else "",
            ip_mask=parts[2] if len(parts) > 2 else "",
            mac=(parts[3] if len(parts) > 3 else "").lower(),
        ))
    return out
