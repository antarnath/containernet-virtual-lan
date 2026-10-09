"""Inter-router static route installer.

When a topology has more than one router, each router only installs
the directly-attached ``/29`` (or whatever mask) subnets at boot —
the kernel does that automatically when each interface comes up.
The router does NOT automatically learn about subnets on the other
side of a peer router's wires.

For a user-drawn topology like::

    Host-1 ---+              +--- Host-4
              |              |
    Host-2 ---+-- Router-1 --+-- Router-2 ---+--- Host-5
              |    |        |   |           |
    Host-3 ---+    |        |   +--- Host-6 ---+
                   |        |
                   +-- uplink+
                        10.99.0.0/29
                        R1=10.99.0.1, R2=10.99.0.2

…Router-1 needs:

    192.168.20.0/24 via 10.99.0.2

…and Router-2 needs the symmetric route. We install these via the
router agent's ``POST /routes`` endpoint (which calls ``ip route
replace`` inside the container). The agent's ``replace`` makes the
operation idempotent — calling this on every project start is fine.

This runs after all containers are up (in ``project_lifecycle.start_project``)
so the agent URLs are guaranteed resolvable. Failures are logged
and counted but never abort the start; the project still comes up
in the ``running`` state with whatever routes managed to install.
The user can see missing routes on the Router panel and install
them manually via the existing ``POST /routes`` UI.

Why we don't pass ``dev=``:
  The *project model*'s interface name (whatever the user typed:
  ``eth3`` / ``Gi0/0/0`` / etc.) is just a label — the actual
  *kernel* interface name depends on attach order, so it would
  not generally match. The kernel can auto-pick the right outgoing
  interface when ``via=`` is a directly-attached next-hop, so we
  only send ``dst`` and ``via`` and let the kernel figure it out.
  The agent's ``POST /routes`` accepts this (it now only requires
  either ``via`` or ``dev``, not both).

Scope notes (v1):
  • Only inter-router wires trigger this. A router↔switch↔host
    chain is L2 only; no IP routes needed.
  • For a chain R1—R2—R3, R1 learns about R2's down-LANs but NOT
    about R3's down-LANs (those are 2 hops away). v2 would do a
    proper SPF walk; for the dual-router demo this is sufficient.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

from app.models import NodeKind, Project, ProjectLink, ProjectNode
from app.services import router_proxy

log = logging.getLogger(__name__)


@dataclass
class InstallResult:
    """Outcome of installing routes for a single project."""
    installed: int = 0
    skipped: int = 0  # pairs where one side had no IP / no container
    failed: int = 0
    errors: list[str] = field(default_factory=list)


# ─── public API ────────────────────────────────────────────────────────

async def install_inter_router_routes(project: Project) -> InstallResult:
    """Walk the project's links and install static routes for every
    router-to-router pair.

    Safe to call multiple times — the agent uses ``ip route replace``
    so re-installing the same route is a no-op. Caller decides when
    (typically: right after ``start_project`` spawns all nodes).
    """
    result = InstallResult()
    routers = [n for n in project.nodes if _kind(n) == NodeKind.ROUTER]
    if len(routers) < 2:
        # Nothing to do for single-router topologies. Don't bother
        # logging — this is the common case.
        return result

    # Build iface-id → (node, iface) so each link endpoint resolves
    # in O(1) instead of O(N²).
    iface_index: dict[str, tuple[ProjectNode, object]] = {}
    for n in project.nodes:
        for i in n.interfaces:
            iface_index[i.id] = (n, i)

    # For every link whose BOTH endpoints are on routers, install
    # the routes.
    for link in project.links:
        a = iface_index.get(link.iface_a_id)
        b = iface_index.get(link.iface_b_id)
        if a is None or b is None:
            continue
        node_a, iface_a = a
        node_b, iface_b = b
        if _kind(node_a) != NodeKind.ROUTER or _kind(node_b) != NodeKind.ROUTER:
            continue
        # Install: every LAN on node_a (except this uplink) onto node_b,
        # and vice versa. The two ``_install_peer_lans`` calls are
        # symmetric — each passes BOTH the target's and the peer's
        # uplink iface (for the via-IP and the dev-name, respectively).
        uplink_subnet = link.subnet_cidr
        # node_b is the target, node_a is the peer.
        await _install_peer_lans(
            target_node=node_b,
            target_uplink_iface=iface_b,
            peer_uplink_iface=iface_a,
            uplink_link_id=link.id,
            peer_node=node_a,
            all_links=project.links,
            skip_subnet=uplink_subnet,
            result=result,
        )
        # node_a is the target, node_b is the peer.
        await _install_peer_lans(
            target_node=node_a,
            target_uplink_iface=iface_a,
            peer_uplink_iface=iface_b,
            uplink_link_id=link.id,
            peer_node=node_b,
            all_links=project.links,
            skip_subnet=uplink_subnet,
            result=result,
        )

    if result.installed or result.failed or result.skipped:
        log.info(
            "[route_installer] project=%s installed=%d skipped=%d failed=%d",
            project.id, result.installed, result.skipped, result.failed,
        )
    else:
        log.debug(
            "[route_installer] project=%s no inter-router routes to install",
            project.id,
        )
    return result


# ─── helpers ───────────────────────────────────────────────────────────

def _kind(node: ProjectNode) -> NodeKind:
    """Coerce ``node.kind`` (which may be a string or enum) to NodeKind."""
    if isinstance(node.kind, NodeKind):
        return node.kind
    return NodeKind(node.kind)


def _peer_lans(
    peer: ProjectNode,
    *,
    all_links: list[ProjectLink],
    skip_subnet: str | None,
    skip_link_id: str | None,
) -> Iterable[str]:
    """Yield the ``subnet_cidr`` for every LAN link on ``peer`` that
    is NOT the inter-router uplink we're installing from.

    We iterate ``all_links`` (the project's pre-loaded link list) and
    filter to those where AT LEAST ONE endpoint iface belongs to
    ``peer`` — that's the definition of a "link on peer". (The other
    endpoint is a host / switch, which is the LAN it owns.) We avoid
    the M2M ``peer.links`` relationship, which would trigger a
    lazy-load the async session can't service.
    """
    peer_iface_ids = {i.id for i in peer.interfaces}
    for link in all_links:
        if link.id == skip_link_id:
            continue
        # Exactly one end is on the peer (the other is the host/switch).
        a_on_peer = link.iface_a_id in peer_iface_ids
        b_on_peer = link.iface_b_id in peer_iface_ids
        if not (a_on_peer ^ b_on_peer):
            # Either neither side is on peer (some unrelated link)
            # or both are (which would mean it's the uplink or some
            # other router-to-something thing — we don't want).
            continue
        if not link.subnet_cidr:
            continue
        if link.subnet_cidr == skip_subnet:
            continue
        yield link.subnet_cidr


async def _install_peer_lans(
    *,
    target_node: ProjectNode,
    target_uplink_iface,
    peer_uplink_iface,
    uplink_link_id: str,
    peer_node: ProjectNode,
    all_links: list[ProjectLink],
    skip_subnet: str | None,
    result: InstallResult,
) -> None:
    """Install every LAN subnet on ``peer_node`` (except the uplink)
    on ``target_node``.

    ``target_uplink_iface`` is the interface on ``target_node`` that
    faces ``peer_node`` — kept for clarity / future use; we don't
    pass its name to the kernel because that name (from the project
    model) doesn't always match the kernel's actual ``ethN`` name.

    ``peer_uplink_iface`` is the iface on ``peer_node`` that faces
    ``target_node`` — its IP is the ``via`` next-hop. The kernel
    auto-picks the outgoing interface from a directly-attached
    next-hop, so this is all we need to send.

    ``all_links`` is the project's pre-loaded link list — we pass it
    in so we don't trigger lazy-loads on the M2M ``node.links`` (which
    can't be served in an async session context).
    """
    if not target_node.container_id:
        result.skipped += 1
        result.errors.append(
            f"{target_node.name!r} has no container; skipping routes"
        )
        return
    if not peer_uplink_iface.ip_address:
        # No IP on the peer's uplink side — we don't have a next-hop.
        result.skipped += 1
        return
    via_ip = peer_uplink_iface.ip_address
    # Note: we deliberately do NOT pass `dev=` here. The router agent
    # builds ``ip route replace <dst> via <via>``; the kernel then
    # picks the right outgoing interface automatically (since via is
    # a directly-attached next-hop). This is robust against the gap
    # between the *project model*'s interface name (whatever the
    # user typed: ``eth3`` / ``Gi0/0/0`` / etc.) and the *kernel*'s
    # interface name (``eth1`` / ``eth2`` / …) which depends on
    # attach order and would otherwise require a lookup.

    for subnet in _peer_lans(
        peer_node,
        all_links=all_links,
        skip_subnet=skip_subnet,
        skip_link_id=uplink_link_id,
    ):
        install = await router_proxy.set_route(
            target_node.container_id,
            dst=subnet,
            via=via_ip,
            dev=None,
        )
        if install.ok:
            result.installed += 1
            log.info(
                "[route_installer] %s: route %s via %s OK",
                target_node.name, subnet, via_ip,
            )
        else:
            result.failed += 1
            msg = (
                f"{target_node.name}: route {subnet} via {via_ip} "
                f"failed: {install.error}"
            )
            result.errors.append(msg)
            log.warning("[route_installer] %s", msg)
