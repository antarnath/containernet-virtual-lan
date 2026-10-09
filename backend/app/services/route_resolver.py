"""Route resolution — M4 phase 05.

Given a project topology + a (source_node, destination_ip) pair,
walk the topology and return the list of hops the packet would
take. The result is the route preview shown in the Trigger
modal before the user clicks Send, and the canonical hop list
the frontend highlights in the wire view after the message is
sent.

Algorithm
---------
A real router resolves a route from its own routing table. In
M4 every router has a static-routes list (added by the user via
the router panel) and the kernel table (``ip route``) is what
the agent exposes. We don't introspect the kernel table from
here — that's expensive and racy. Instead we **simulate** the
forwarding decision using the topology:

  1. Source node's interface that matches ``dst_ip`` via
     longest-prefix match against the link's subnet_cidr.
  2. Walk to the neighbor on that link. If the neighbor is a
     switch, walk through to the next node.
  3. If the neighbor is a router, look at the router's static
     routes for a match on ``dst_ip``. The first matching route
     tells us which interface to egress on; recurse.
  4. Stop when the destination IP is on a directly-attached
     subnet of the current node (the next hop IS the dest).
  5. Cap at 16 hops; raise ``RouteLoop`` if exceeded (caller
     renders this as a "Routing loop detected" warning).

The function is a pure function of the project topology; no
side effects, no Docker calls. That makes it cheap enough to
run on every keystroke in the Trigger modal.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Project,
    ProjectInterface,
    ProjectLink,
    ProjectNode,
)

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


# ─── data shapes ──────────────────────────────────────────────────────

@dataclass
class Hop:
    """One step in the resolved route.

    * ``node_id`` — the node we're at after this hop
    * ``node_name`` — human-readable name
    * ``node_kind`` — host / switch / router / server / attacker
    * ``iface_name`` — which interface of ``node_id`` we egress on
    * ``iface_ip`` — the IP bound to that interface (may be None
      for switches)
    * ``link_id`` — the link we just crossed (None for the
      starting position)
    * ``link_subnet`` — the subnet of that link (for the UI)
    """
    node_id: str
    node_name: str
    node_kind: str
    iface_name: str | None
    iface_ip: str | None
    link_id: str | None
    link_subnet: str | None

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "node_kind": self.node_kind,
            "iface_name": self.iface_name,
            "iface_ip": self.iface_ip,
            "link_id": self.link_id,
            "link_subnet": self.link_subnet,
        }


class RouteError(Exception):
    """Unresolvable route (no matching subnet, dst unreachable)."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class RouteLoop(Exception):
    """More than MAX_HOPS steps — looks like a routing loop."""
    def __init__(self, visited: list[str]):
        super().__init__(f"routing loop after {len(visited)} hops: {' -> '.join(visited)}")
        self.visited = visited


MAX_HOPS = 16


# ─── main entry point ─────────────────────────────────────────────────

async def resolve_route(
    session: AsyncSession,
    project_id: str,
    src_node_id: str,
    dst_ip: str,
) -> list[Hop]:
    """Return the hop list for ``src_node_id`` → ``dst_ip``.

    Raises ``RouteError`` if the destination is unreachable.
    Raises ``RouteLoop`` if the walk exceeds ``MAX_HOPS`` (the
    topology has a routing loop).
    """
    project = await _load_topology(session, project_id)
    if project is None:
        raise RouteError(f"project {project_id!r} not found")

    # Index the topology for fast lookup.
    nodes_by_id: dict[str, ProjectNode] = {n.id: n for n in project.nodes}
    if src_node_id not in nodes_by_id:
        raise RouteError(f"source node {src_node_id!r} not in project")

    # Adjacency: node_id -> list of (neighbor_node_id, link, my_iface, peer_iface)
    adjacency: dict[str, list[tuple[ProjectNode, ProjectLink, ProjectInterface, ProjectInterface]]] = {}
    for link in project.links:
        iface_a = _iface_by_id(project, link.iface_a_id)
        iface_b = _iface_by_id(project, link.iface_b_id)
        if iface_a is None or iface_b is None:
            continue
        node_a = nodes_by_id.get(iface_a.node_id)
        node_b = nodes_by_id.get(iface_b.node_id)
        if node_a is None or node_b is None:
            continue
        adjacency.setdefault(node_a.id, []).append((node_b, link, iface_a, iface_b))
        adjacency.setdefault(node_b.id, []).append((node_a, link, iface_b, iface_a))

    # Build iface + link metadata for "is dst on a directly-attached subnet?" tests.
    node_subnets: dict[str, list[tuple[ProjectInterface, ProjectLink]]] = {}
    for link in project.links:
        for iface_id in (link.iface_a_id, link.iface_b_id):
            iface = _iface_by_id(project, iface_id)
            if iface is None:
                continue
            if iface.ip_address and link.subnet_cidr:
                try:
                    net = ipaddress.ip_network(link.subnet_cidr, strict=False)
                    node_subnets.setdefault(iface.node_id, []).append((iface, link))
                except ValueError:
                    continue

    # Routes per router: list of (dst_cidr, gateway, kernel_iface).
    # We pull the routing table from the live router agent via
    # ``router_proxy`` (cached for 2s). If a router's agent
    # is unreachable, we fall back to "no routes" — the walk
    # will then succeed for directly-attached subnets only.
    #
    # M4-09 fix: we now keep the ``gateway`` (via-IP) alongside the
    # kernel-resolved iface. The route_resolver can't match
    # ``my_iface.name == best.iface`` because the kernel name
    # (``eth3``) is assigned by Docker on attach order and almost
    # never matches the project-model name the user typed
    # (``eth2``). Instead we find the egress link by matching the
    # route's gateway IP against the peer's iface IP on each
    # adjacent link — that gives us the correct link regardless
    # of kernel vs project naming.
    routes_by_node: dict[str, list[tuple[ipaddress.IPv4Network, str, str]]] = {}
    try:
        from app.services import router_proxy
        for n in project.nodes:
            if _kind_str(n.kind) != "router":
                continue
            container_id = getattr(n, "container_id", None)
            try:
                state = await router_proxy.get_router_state(n.id, container_id)
            except Exception:
                continue
            for entry in state.routes:
                try:
                    net = ipaddress.ip_network(entry.destination, strict=False)
                except ValueError:
                    continue
                if not entry.iface:
                    continue
                routes_by_node.setdefault(n.id, []).append(
                    (net, entry.gateway, entry.iface)
                )
    except Exception as exc:
        log.debug("[route_resolver] could not enrich router routes: %s", exc)

    # ─── walk ──────────────────────────────────────────────────────
    try:
        dst = ipaddress.ip_address(dst_ip)
    except ValueError as exc:
        raise RouteError(f"invalid destination IP {dst_ip!r}: {exc}")

    hops: list[Hop] = []
    current_node = nodes_by_id[src_node_id]
    visited: list[str] = [current_node.id]
    egress_iface: ProjectInterface | None = None
    prev_link: ProjectLink | None = None

    # Push the source node as the first hop (no link yet).
    hops.append(Hop(
        node_id=current_node.id,
        node_name=current_node.name,
        node_kind=_kind_str(current_node.kind),
        iface_name=None,
        iface_ip=None,
        link_id=None,
        link_subnet=None,
    ))

    while True:
        if len(hops) > MAX_HOPS:
            raise RouteLoop(visited)

        # 1) Is the destination on a directly-attached subnet of
        #    the current node? (Either our own IP matches, or the
        #    dst is in one of the link subnets we're attached to.)
        for iface, link in node_subnets.get(current_node.id, []):
            if iface.ip_address and link.subnet_cidr:
                try:
                    net = ipaddress.ip_network(link.subnet_cidr, strict=False)
                except ValueError:
                    continue
                if dst in net:
                    # Found: dst is on this subnet. The "hop" is
                    # the iface on the current node, and the link
                    # that carries it. If the dst IP is exactly
                    # the iface IP, the message is local (no
                    # link crossing).
                    hops.append(Hop(
                        node_id=current_node.id,
                        node_name=current_node.name,
                        node_kind=_kind_str(current_node.kind),
                        iface_name=iface.name,
                        iface_ip=iface.ip_address,
                        link_id=link.id if str(dst) != iface.ip_address else None,
                        link_subnet=link.subnet_cidr,
                    ))
                    return hops

        # 2) Decide the egress link. For non-routers, the egress
        #    is the link whose subnet contains the dst. For
        #    routers, look at the static-routes table. As a
        #    fallback for non-routers, if the dst is NOT on any
        #    directly-attached subnet, we assume the host has a
        #    default route to a router on one of its attached
        #    links (the standard "default gateway" behaviour).
        next_link: ProjectLink | None = None
        next_neighbor: ProjectNode | None = None
        next_egress_iface: ProjectInterface | None = None
        next_peer_iface: ProjectInterface | None = None

        if current_node.kind == "router":
            # Longest-prefix match in the static-routes table.
            best: tuple[ipaddress.IPv4Network, str, str] | None = None
            for entry in routes_by_node.get(current_node.id, []):
                net, gw, dev = entry
                if dst in net:
                    if best is None or net.prefixlen > best[0].prefixlen:
                        best = entry
            if best is None:
                raise RouteError(
                    f"router {current_node.name!r} has no route to {dst_ip}"
                )
            # M4-09 fix: the route's gateway IP (``via``) is the
            # peer router's iface IP on the egress link. The
            # kernel-resolved ``dev`` is unreliable for matching
            # because the project's interface name (user-typed,
            # ``eth2``) doesn't match the kernel's auto-assigned
            # name (``eth3``). We pick the egress link by finding
            # the adjacent link whose peer's IP equals the route's
            # gateway. If the gateway is empty (a directly-attached
            # route) fall back to matching by link subnet.
            best_net, best_gw, best_dev = best
            for neighbor, link, my_iface, peer_iface in adjacency.get(current_node.id, []):
                if best_gw and peer_iface.ip_address == best_gw:
                    next_link = link
                    next_neighbor = neighbor
                    next_egress_iface = my_iface
                    next_peer_iface = peer_iface
                    break
                if not best_gw and link.subnet_cidr:
                    try:
                        if dst in ipaddress.ip_network(link.subnet_cidr, strict=False):
                            next_link = link
                            next_neighbor = neighbor
                            next_egress_iface = my_iface
                            next_peer_iface = peer_iface
                            break
                    except ValueError:
                        continue
            if next_link is None:
                # Final fallback: the gateway IP might be the
                # directly-attached subnet's broadcast / any-IP
                # (e.g. the bridge gateway). Match by link subnet
                # containing the dst.
                for neighbor, link, my_iface, peer_iface in adjacency.get(current_node.id, []):
                    if link.subnet_cidr:
                        try:
                            if dst in ipaddress.ip_network(link.subnet_cidr, strict=False):
                                next_link = link
                                next_neighbor = neighbor
                                next_egress_iface = my_iface
                                next_peer_iface = peer_iface
                                break
                        except ValueError:
                            continue
            if next_link is None:
                raise RouteError(
                    f"router {current_node.name!r} routes to {dst_ip} via "
                    f"gateway {best_gw!r} but no adjacent link has that "
                    f"peer IP"
                )
        else:
            # Host / switch / server / attacker: egress is the link
            # whose subnet contains dst.
            best_link: ProjectLink | None = None
            best_peer: ProjectNode | None = None
            best_egress: ProjectInterface | None = None
            best_in: ProjectInterface | None = None
            for neighbor, link, my_iface, peer_iface in adjacency.get(current_node.id, []):
                if link.subnet_cidr is None:
                    continue
                try:
                    net = ipaddress.ip_network(link.subnet_cidr, strict=False)
                except ValueError:
                    continue
                if dst in net:
                    best_link = link
                    best_peer = neighbor
                    best_egress = my_iface
                    best_in = peer_iface
                    break
            if best_link is None:
                # No directly-attached subnet matches the dst. If
                # the current node is non-router and has at least
                # one router neighbor, route via that router's
                # attached subnet (implicit default route to the
                # gateway). This matches how hosts behave in
                # real networks: they have a default gateway.
                for neighbor, link, my_iface, peer_iface in adjacency.get(current_node.id, []):
                    if _kind_str(neighbor.kind) == "router":
                        best_link = link
                        best_peer = neighbor
                        best_egress = my_iface
                        best_in = peer_iface
                        break
                if best_link is None:
                    raise RouteError(
                        f"{current_node.name!r} ({_kind_str(current_node.kind)}) "
                        f"has no route to {dst_ip} and no router neighbor "
                        f"to use as a default gateway"
                    )
            next_link = best_link
            next_neighbor = best_peer
            next_egress_iface = best_egress
            next_peer_iface = best_in

        # 3) Switches: don't consume a hop, just walk through.
        if next_neighbor.kind == "switch":
            visited.append(next_neighbor.id)
            # Add the switch hop to the list (so the UI can show
            # the path), but continue the loop from there.
            hops.append(Hop(
                node_id=next_neighbor.id,
                node_name=next_neighbor.name,
                node_kind="switch",
                iface_name=next_peer_iface.name if next_peer_iface else None,
                iface_ip=next_peer_iface.ip_address if next_peer_iface else None,
                link_id=next_link.id,
                link_subnet=next_link.subnet_cidr,
            ))
            current_node = next_neighbor
            prev_link = next_link
            continue

        # 4) Walk the link to the next node.
        visited.append(next_neighbor.id)
        hops.append(Hop(
            node_id=next_neighbor.id,
            node_name=next_neighbor.name,
            node_kind=_kind_str(next_neighbor.kind),
            iface_name=next_peer_iface.name if next_peer_iface else None,
            iface_ip=next_peer_iface.ip_address if next_peer_iface else None,
            link_id=next_link.id,
            link_subnet=next_link.subnet_cidr,
        ))
        current_node = next_neighbor
        prev_link = next_link

        # 5) If the new current_node is the destination (matched
        #    on iface_ip), we're done.
        for iface, _ in node_subnets.get(current_node.id, []):
            if iface.ip_address and str(dst) == iface.ip_address:
                return hops


# ─── helpers ──────────────────────────────────────────────────────────

def _kind_str(kind) -> str:
    """Normalize a NodeKind enum (or str) to its lowercase value."""
    if hasattr(kind, "value"):
        return kind.value
    return str(kind)


def _iface_by_id(project: Project, iface_id: str | None) -> ProjectInterface | None:
    if iface_id is None:
        return None
    for n in project.nodes:
        for i in n.interfaces:
            if i.id == iface_id:
                return i
    return None


async def _load_topology(
    session: AsyncSession, project_id: str
) -> Project | None:
    """Load the project with all topology eagerly joined."""
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.nodes).selectinload(ProjectNode.interfaces),
            selectinload(Project.links),
        )
    )
    return (await session.execute(stmt)).scalars().first()
