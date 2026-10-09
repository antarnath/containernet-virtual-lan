"""Unit test for the route resolver (M4 phase 05).

Run inside the backend container with::

    python tests/test_route_resolver.py

Builds a tiny in-memory topology (host - router - host) and
verifies that resolve_route returns the correct hop list for
same-subnet, cross-subnet, and unreachable destinations.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

sys.path.insert(0, "/app")

# We don't actually need the DB for this test — the resolver's
# _load_topology uses asyncpg, but we can short-circuit by
# monkey-patching _load_topology to return a pre-built Project-
# like object. The cleanest path is to set ``_load_topology`` on
# the module to a fake that returns a SimpleNamespace.

from types import SimpleNamespace
from app.services import route_resolver


def _iface(iface_id: str, node_id: str, name: str, ip: str, mask: str = "/24"):
    return SimpleNamespace(
        id=iface_id, node_id=node_id, name=name,
        ip_address=ip, subnet_mask=mask, mac_address=None,
    )


def _node(node_id: str, name: str, kind: str, ifaces: list):
    return SimpleNamespace(
        id=node_id, name=name, kind=kind, interfaces=ifaces,
        container_id=None, container_status="stopped",
        canvas_x=0.0, canvas_y=0.0, attack_mode=None,
        created_at=None, updated_at=None,
    )


def _link(link_id: str, iface_a_id: str, iface_b_id: str, subnet: str):
    return SimpleNamespace(
        id=link_id, iface_a_id=iface_a_id, iface_b_id=iface_b_id,
        subnet_cidr=subnet, docker_bridge_name=None, docker_network_id=None,
    )


def _build_topology():
    """Build a host - router - host topology with two subnets.

    Host-1 (10.0.0.2) --link1-- Router-1 (10.0.0.1 / 10.0.1.1) --link2-- Host-2 (10.0.1.2)
    """
    h1 = _node("h1", "Host-1", "host", [
        _iface("h1e0", "h1", "eth0", "10.0.0.2"),
    ])
    r1 = _node("r1", "Router-1", "router", [
        _iface("r1e0", "r1", "eth0", "10.0.0.1"),
        _iface("r1e1", "r1", "eth1", "10.0.1.1"),
    ])
    h2 = _node("h2", "Host-2", "host", [
        _iface("h2e0", "h2", "eth0", "10.0.1.2"),
    ])
    link1 = _link("l1", "h1e0", "r1e0", "10.0.0.0/24")
    link2 = _link("l2", "r1e1", "h2e0", "10.0.1.0/24")
    project = SimpleNamespace(
        id="test", name="test", nodes=[h1, r1, h2], links=[link1, link2],
        routes=[],
    )
    return project, h1, r1, h2, link1, link2


async def main() -> int:
    project, h1, r1, h2, link1, link2 = _build_topology()

    # Patch the resolver to use our in-memory topology.
    async def fake_load(session, project_id):
        return project
    route_resolver._load_topology = fake_load

    class _NoopRouterProxy:
        async def get_router_state(self, node_id, container_id):
            from app.services.router_proxy import RouterState
            return RouterState(routes=[], neigh=[], ifaces=[], fetched_at=0)
    import app.services.router_proxy as rp
    rp.get_router_state = _NoopRouterProxy().get_router_state

    # Stub the dynamic import: route_resolver imports router_proxy
    # inside resolve_route, so we also need to patch the module
    # attribute.
    import sys as _sys
    _sys.modules["app.services.router_proxy"] = rp

    passed = 0
    failed = 0

    def check(label: str, condition: bool, info: str = ""):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS  {label}")
        else:
            failed += 1
            print(f"  FAIL  {label}  {info}")

    # ─── Test 1: same-subnet route (Host-1 → Router-1 10.0.0.1) ──
    hops = await route_resolver.resolve_route(None, "test", "h1", "10.0.0.1")
    check("same-subnet: 2 hops", len(hops) == 2, f"got {len(hops)}")
    check(
        "same-subnet: last hop iface is h1 eth0",
        hops[-1].iface_name == "eth0" and hops[-1].iface_ip == "10.0.0.2",
        f"got {hops[-1].iface_name}/{hops[-1].iface_ip}",
    )
    check(
        "same-subnet: no link crossing for self dst",
        hops[-1].link_id == link1.id,  # dst is on the same subnet, but not the same iface
        f"got link_id={hops[-1].link_id}",
    )

    # ─── Test 2: cross-subnet route (Host-1 → Host-2 10.0.1.2) ────
    hops = await route_resolver.resolve_route(None, "test", "h1", "10.0.1.2")
    check("cross-subnet: 3 hops", len(hops) == 3, f"got {len(hops)}")
    check(
        "cross-subnet: ends at Router-1 eth1",
        hops[-1].node_id == "r1" and hops[-1].iface_name == "eth1",
        f"got {hops[-1].node_id}/{hops[-1].iface_name}",
    )
    check(
        "cross-subnet: middle hop is Router-1 eth0 (default gw)",
        hops[1].node_id == "r1" and hops[1].iface_name == "eth0",
        f"got {hops[1].node_id}/{hops[1].iface_name}",
    )

    # ─── Test 3: unreachable destination ─────────────────────────
    try:
        await route_resolver.resolve_route(None, "test", "h1", "8.8.8.8")
        check("unreachable: raises RouteError", False, "no exception")
    except route_resolver.RouteError as exc:
        check("unreachable: raises RouteError", True, str(exc))

    # ─── Test 4: invalid IP ───────────────────────────────────────
    try:
        await route_resolver.resolve_route(None, "test", "h1", "not.an.ip")
        check("invalid IP: raises RouteError", False, "no exception")
    except route_resolver.RouteError as exc:
        check("invalid IP: raises RouteError", True, str(exc))

    # ─── Test 5: source node not in project ───────────────────────
    try:
        await route_resolver.resolve_route(None, "test", "nope", "10.0.0.1")
        check("unknown src: raises RouteError", False, "no exception")
    except route_resolver.RouteError as exc:
        check("unknown src: raises RouteError", True, str(exc))

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
