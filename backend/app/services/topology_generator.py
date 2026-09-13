"""Topology generators — pure functions that turn a topology name + host count
+ subnet into a `{nodes, edges}` graph.

These functions do NOT touch the database. They are pure: same inputs →
same outputs. The caller is responsible for persisting the result.

Supported topologies
--------------------
- ``mesh``   fully connected: every node links to every other node
- ``star``   one center node (host-1) connected to all others
- ``ring``   closed loop: each node has exactly two neighbours
- ``bus``    linear chain: host 1 — host 2 — … — host N
- ``tree``   balanced binary tree (root is host 1; child i connects to parent)

Layout
------
``generate_topology`` returns nodes with ``position_x``/``position_y`` so the
frontend React Flow canvas can render them without needing Dagre on the
first paint. The user can drag a node to a new position; the layout here is
just a sensible starting point.

IP allocation
-------------
For a project with subnet ``10.20.0.0/24``:
    gateway   = 10.20.0.1
    host 1    = 10.20.0.11
    host 2    = 10.20.0.12
    …
    host N    = 10.20.0.{10 + N}

The ``+10`` offset leaves 10.20.0.2 … 10.20.0.10 free for the gateway and
future infrastructure. Anything outside the /24 is rejected as a bad subnet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from ipaddress import IPv4Network
from typing import Literal


TopologyType = Literal["mesh", "star", "ring", "bus", "tree"]
SUPPORTED_TOPOLOGIES: tuple[str, ...] = ("mesh", "star", "ring", "bus", "tree")

# Reasonable defaults for the canvas. Tuned so a 5-node mesh actually looks
# like a mesh on a 1280×800 viewport.
CANVAS_CENTER_X = 400.0
CANVAS_CENTER_Y = 300.0
OUTER_RADIUS = 220.0


@dataclass(frozen=True)
class GeneratedNode:
    """One node in a generated topology, before the database is touched."""
    host_id: str              # e.g. "host-1"
    hostname: str             # e.g. "pc-1"
    ip_address: str           # e.g. "10.20.0.11"
    position_x: float
    position_y: float
    index: int                # 1-based position in the topology


@dataclass(frozen=True)
class GeneratedEdge:
    """One edge in a generated topology, before the database is touched."""
    source_host_id: str       # "host-1"
    dest_host_id: str         # "host-2"
    # Edges are undirected in the visual graph but stored with a canonical
    # (source, dest) ordering where source_index < dest_index. That keeps
    # SELECT DISTINCT semantics sane.


# ─── subnet / IP helpers ────────────────────────────────────────────────────

class BadSubnetError(ValueError):
    """The provided subnet cannot host the requested number of hosts."""


def _validate_subnet(subnet: str, host_count: int) -> IPv4Network:
    """Parse ``subnet`` as CIDR and ensure it can fit ``host_count`` hosts.

    Adds the gateway slot, leaves room for ``+10`` offset.
    """
    try:
        network = IPv4Network(subnet, strict=False)
    except Exception as exc:
        raise BadSubnetError(f"invalid CIDR: {subnet!r}") from exc

    if network.version != 4:
        raise BadSubnetError("only IPv4 subnets are supported")

    # Need at least host_count + 10 usable addresses (offset 10, plus gateway).
    usable = network.num_addresses - 2  # subtract network + broadcast
    needed = host_count + 10
    if usable < needed:
        raise BadSubnetError(
            f"subnet {subnet} has only {usable} usable addresses, "
            f"need {needed} (host_count={host_count} + offset 10)"
        )

    # Reject subnets that clash with Docker's default bridge — creating a
    # project with one of these would make the backend's containers
    # unreachable from the rest of the LAN.
    blocked = (
        IPv4Network("172.17.0.0/16"),   # docker0 default bridge
        IPv4Network("10.10.0.0/24"),    # the static pc1/pc2/pc3 LAN
    )
    for block in blocked:
        if network.overlaps(block):
            raise BadSubnetError(
                f"subnet {subnet} overlaps with reserved range {block}"
            )

    return network


def _ip_for(network: IPv4Network, host_index: int) -> str:
    """Return the IP address for ``host_index`` (1-based) within ``network``.

    The first 10 addresses after the network address are reserved; the
    gateway conventionally lives at index 1, so host N gets ``+10+N``.
    """
    if host_index < 1:
        raise ValueError("host_index must be 1-based")
    base = int(network.network_address)
    return str(IPv4Network((base + 10 + host_index)).network_address.__class__(
        base + 10 + host_index
    ))


def _ip_for_index(network: IPv4Network, host_index: int) -> str:
    """Internal: same as ``_ip_for`` but uses IPv4Address directly."""
    from ipaddress import IPv4Address
    return str(IPv4Address(int(network.network_address) + 10 + host_index))


# ─── per-topology layout functions ─────────────────────────────────────────

def _ring_positions(n: int) -> list[tuple[float, float]]:
    """Place ``n`` points evenly around a circle."""
    if n == 1:
        return [(CANVAS_CENTER_X, CANVAS_CENTER_Y)]
    return [
        (
            CANVAS_CENTER_X + OUTER_RADIUS * math.cos(2 * math.pi * i / n),
            CANVAS_CENTER_Y + OUTER_RADIUS * math.sin(2 * math.pi * i / n),
        )
        for i in range(n)
    ]


def _star_positions(n: int) -> list[tuple[float, float]]:
    """Center at first node; others on a ring around it."""
    if n == 1:
        return [(CANVAS_CENTER_X, CANVAS_CENTER_Y)]
    if n == 2:
        # Two nodes: centre on the left, satellite on the right.
        return [
            (CANVAS_CENTER_X - 60, CANVAS_CENTER_Y),
            (CANVAS_CENTER_X + 160, CANVAS_CENTER_Y),
        ]
    center = (CANVAS_CENTER_X, CANVAS_CENTER_Y)
    positions: list[tuple[float, float]] = [center]
    others = n - 1
    for i in range(others):
        angle = 2 * math.pi * i / others - math.pi / 2  # start at top
        positions.append((
            CANVAS_CENTER_X + OUTER_RADIUS * math.cos(angle),
            CANVAS_CENTER_Y + OUTER_RADIUS * math.sin(angle),
        ))
    return positions


def _bus_positions(n: int) -> list[tuple[float, float]]:
    """Linear chain horizontally; second row if too many for one row."""
    cols = max(3, math.ceil(math.sqrt(n * 2)))  # wider than tall
    positions: list[tuple[float, float]] = []
    for i in range(n):
        row = i // cols
        col = i % cols
        x = 80 + col * (OUTER_RADIUS * 1.5)
        y = CANVAS_CENTER_Y + row * 130 - 65
        positions.append((x, y))
    return positions


def _tree_positions(n: int) -> list[tuple[float, float]]:
    """Balanced binary tree; root in the middle, children spread downward."""
    if n == 1:
        return [(CANVAS_CENTER_X, CANVAS_CENTER_Y)]
    depth = math.ceil(math.log2(n + 1))           # tree depth (root at 0)
    positions: list[tuple[float, float]] = []
    for i in range(n):
        level = math.floor(math.log2(i + 1))       # 0-based depth of node i
        index_in_level = i - (2 ** level - 1)      # 0-based position in row
        nodes_at_level = 2 ** level
        # spread evenly across the canvas
        x = (
            CANVAS_CENTER_X
            + (index_in_level - (nodes_at_level - 1) / 2)
            * (700.0 / max(nodes_at_level - 1, 1))
        )
        y = 60 + level * 130
        positions.append((x, y))
    return positions


def _mesh_positions(n: int) -> list[tuple[float, float]]:
    """Mesh: same outer ring as ring topology, easier to read than a grid."""
    return _ring_positions(n)


# ─── edge generators ────────────────────────────────────────────────────────

def _complete_pairs(n: int) -> list[tuple[int, int]]:
    """All unique unordered pairs (i, j) with i < j."""
    return [(i, j) for i in range(1, n + 1) for j in range(i + 1, n + 1)]


def _star_edges(n: int) -> list[tuple[int, int]]:
    """Center (1) to every other node."""
    return [(1, k) for k in range(2, n + 1)]


def _ring_edges(n: int) -> list[tuple[int, int]]:
    """Closed loop: (1,2), (2,3), … (n-1,n), (n,1)."""
    if n < 2:
        return []
    edges = [(i, i + 1) for i in range(1, n)]
    edges.append((n, 1))
    return edges


def _bus_edges(n: int) -> list[tuple[int, int]]:
    """Linear chain."""
    if n < 2:
        return []
    return [(i, i + 1) for i in range(1, n)]


def _tree_edges(n: int) -> list[tuple[int, int]]:
    """Balanced binary tree: child i's parent is (i // 2)."""
    if n < 2:
        return []
    return [(i // 2, i) for i in range(2, n + 1)]


# ─── public entry point ─────────────────────────────────────────────────────

def generate_topology(
    topology_type: str,
    host_count: int,
    subnet: str,
) -> tuple[list[GeneratedNode], list[GeneratedEdge]]:
    """Generate the node + edge graph for a topology.

    Returns
    -------
    (nodes, edges)
        ``nodes`` length = ``host_count``
        ``edges`` length depends on topology

    Raises
    ------
    ValueError
        Unknown topology or invalid host count.
    BadSubnetError
        Subnet cannot fit the requested host count.
    """
    if topology_type not in SUPPORTED_TOPOLOGIES:
        raise ValueError(
            f"unknown topology {topology_type!r}; "
            f"supported: {SUPPORTED_TOPOLOGIES}"
        )
    if host_count < 1:
        raise ValueError("host_count must be >= 1")
    if host_count > 32:
        # Soft cap — see overview.md risks section. Surface a clear error.
        raise ValueError("host_count must be <= 32")

    network = _validate_subnet(subnet, host_count)

    layout_fns = {
        "mesh": _mesh_positions,
        "star": _star_positions,
        "ring": _ring_positions,
        "bus":  _bus_positions,
        "tree": _tree_positions,
    }
    edge_fns = {
        "mesh": _complete_pairs,
        "star": _star_edges,
        "ring": _ring_edges,
        "bus":  _bus_edges,
        "tree": _tree_edges,
    }

    positions = layout_fns[topology_type](host_count)
    edges = edge_fns[topology_type](host_count)

    nodes = [
        GeneratedNode(
            host_id=f"host-{idx}",
            hostname=f"pc-{idx}",
            ip_address=_ip_for_index(network, idx),
            position_x=pos[0],
            position_y=pos[1],
            index=idx,
        )
        for idx, pos in enumerate(positions, start=1)
    ]
    id_lookup = {n.index: n.host_id for n in nodes}

    generated_edges = [
        GeneratedEdge(
            source_host_id=id_lookup[a],
            dest_host_id=id_lookup[b],
        )
        for a, b in edges
    ]
    return nodes, generated_edges
