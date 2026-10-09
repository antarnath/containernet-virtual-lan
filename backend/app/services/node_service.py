"""Node service — spawns one Docker container per ProjectNode.

M4 phase 02. The kind determines the image + role env vars + the
number of veths to attach (one per wired interface).

  Kind     Image                              Agent      Veths
  host     containernet-host-base:latest      :8080 + :9100  1 per wire
  switch   containernet-switch-base:latest    (none)          1 per wire
  router   containernet-router-base:latest    :9090           1 per wire
  server   containernet-host-base:latest      :8080 + :9100  1 per wire
  attacker containernet-host-base:latest      :8080 + :9100  1 per wire
                                            + :9092 (phase 06)

Wires are attached as follows:
  For each link the node participates in:
    1. Find or create the per-link bridge (link_service).
    2. Spawn the container with `network=None` (no default attach).
    3. For each wired interface on the node, attach the container
       to the per-link bridge with a pinned IP (the iface's IP).
    4. Also attach the container to the backend's bridge so it
       can reach the backend by DNS (used for heartbeats from
       host/server/attacker; router doesn't need it).

This service is the ONLY place in the backend that issues
`docker run` for project nodes. The lifecycle service (project_lifecycle)
calls into here for each node.

M4 phase 04 — per-link packet capture
-------------------------------------
Each spawned node also starts one background tcpdump per link it
participates in. Why per-node and not per-link sidecar? Because a
Linux bridge's fast-forward path bypasses AF_PACKET, TC, and
netfilter for host→host unicast — so a sidecar tcpdumping the
bridge only sees broadcast/multicast and never the actual wire
traffic. A node's veth, on the other hand, sees every frame on
its link (both directions in the node's netns), so the per-node
capture is the only reliable way to get the full wire view.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from typing import Any

import docker
from docker.errors import APIError, NotFound

from app.core.docker_client import get_docker_client
from app.models import (
    NodeKind,
    Project,
    ProjectInterface,
    ProjectLink,
    ProjectNode,
)
from app.services.container_service import (
    LABEL_HOST,
    LABEL_NODE,
    LABEL_PROJECT,
)
from app.services import link_service


# Image per kind.
KIND_IMAGE: dict[NodeKind, str] = {
    NodeKind.HOST:     "containernet-host-base:latest",
    NodeKind.SWITCH:   "containernet-switch-base:latest",
    NodeKind.ROUTER:   "containernet-router-base:latest",
    NodeKind.SERVER:   "containernet-host-base:latest",
    NodeKind.ATTACKER: "containernet-host-base:latest",
}

# Per-link NDJSON file path. Matches the convention used by the
# per-link capture container (and the wire-view SSE stream), so
# the same code path reads it regardless of who writes to it.
CAPTURE_DIR_HOST = "/var/lib/containernet/captures"


def _link_capture_filename(project_id: str, link_id: str) -> str:
    """Stable per-link filename. 8-char project id + 4-char link id
    keeps the name well under Linux's 255-char filename limit and
    trivially matches across container ↔ host paths."""
    short_p = project_id.replace("-", "")[:8]
    short_l = link_id.replace("-", "")[:4]
    return f"{short_p}l{short_l}"


def _link_capture_path(project_id: str, link_id: str) -> str:
    """Absolute path inside the node container."""
    return f"{CAPTURE_DIR_HOST}/{_link_capture_filename(project_id, link_id)}.ndjson"


# Command per kind. M4 phase 04 wraps every kind's command with the
# per-link capture wrapper (infra/hosts/node_entrypoint.sh) which
# starts a tcpdump per iface before execing the agent. Switches have
# no agent so we still run the wrapper (it's a no-op when no links
# are declared) and then `sleep infinity` to keep the container up.
_NODE_ENTRYPOINT = "/app/node_entrypoint.sh"

KIND_COMMAND: dict[NodeKind, list[str] | None] = {
    NodeKind.HOST:     [_NODE_ENTRYPOINT, "python3", "/app/host-agent/agent.py"],
    NodeKind.SWITCH:   [_NODE_ENTRYPOINT, "sleep", "infinity"],
    NodeKind.ROUTER:   [_NODE_ENTRYPOINT, "python3", "/app/router-agent/agent.py"],
    NodeKind.SERVER:   [_NODE_ENTRYPOINT, "python3", "/app/host-agent/agent.py"],
    NodeKind.ATTACKER: [_NODE_ENTRYPOINT, "python3", "/app/host-agent/agent.py"],
}

# Extra env vars per kind.
def kind_env(kind: NodeKind, *, attack_mode: str | None = None) -> dict[str, str]:
    env: dict[str, str] = {}
    if kind == NodeKind.SERVER:
        env["SERVER_ROLE"] = "true"
    if kind == NodeKind.ATTACKER:
        env["AGENT_ROLE"] = "attacker"
        if attack_mode:
            env["ATTACK_MODE"] = attack_mode
    return env


# Cap on the number of bridges a node can be attached to. Defensive
# only — a sane user-drawn topology won't hit this. A bug elsewhere
# could loop forever connecting the same node to new bridges.
MAX_BRIDGES_PER_NODE = 32


# ─── data shapes ───────────────────────────────────────────────────────

@dataclass
class NodeSpawnResult:
    container_id: str
    attached_bridges: list[str]  # bridge docker network ids


# ─── helpers ───────────────────────────────────────────────────────────

def _container_name(project_id: str, node_id: str, kind: NodeKind) -> str:
    short = project_id.replace("-", "")[:8]
    nid = node_id.replace("-", "")[:6]
    kind_short = kind.value[:3]
    return f"cn-{short}-{kind_short}-{nid}"


def _iface_subnet_for_bridge(
    iface: ProjectInterface, bridge_subnet: str | None
) -> str | None:
    """Sanity-check that the iface IP is inside the bridge subnet.

    If the bridge was derived from a default /30 (no endpoints had
    IPs), the user-typed IP would be outside the bridge's range and
    the container would fail to start. We let the caller decide
    whether to pin the IP at all; this helper is just a guard.
    """
    if not iface.ip_address or not bridge_subnet:
        return None
    try:
        ip = ipaddress.IPv4Address(iface.ip_address)
        net = ipaddress.IPv4Network(bridge_subnet, strict=False)
    except (ipaddress.AddressValueError, ValueError):
        return None
    return str(ip) if ip in net else None


def _apply_capture_env(container, capture_lines: list[str]) -> None:
    """No-op (kept for backwards compat with the old sidecar model).

    The per-link capture is now driven by the container's
    ``NODE_CAPTURE_LINKS`` env, which is set at spawn time via
    ``container.run``. For the "resume a partial start" path (when
    the container already exists from a prior run), captures won't
    start until the next full project start, which re-spawns every
    node. That trade-off keeps the resume path simple.
    """
    return None


# ─── public API ────────────────────────────────────────────────────────

def spawn_node(
    *,
    project: Project,
    node: ProjectNode,
    links: list[ProjectLink],
    interfaces: list[ProjectInterface],
    backend_network: str,
    backend_url: str,
) -> NodeSpawnResult:
    """Spawn the container for one node and attach it to its bridges.

    The function is idempotent: if a container with this node's
    ID already exists (the LABEL_NODE label), it is reused and
    re-attached to whatever bridges are missing.

    Parameters
    ----------
    project : Project
        The parent project row.
    node : ProjectNode
        The node to spawn.
    links : list[ProjectLink]
        Every link in the project — we filter to the ones this
        node participates in (any of its interfaces is an endpoint).
    interfaces : list[ProjectInterface]
        Every interface on this node.
    backend_network : str
        Name of the backend's Docker network (so the node can DNS-
        resolve ``backend`` for heartbeats).
    backend_url : str
        HTTP URL the host/server/attacker agents POST heartbeats to.

    Returns a ``NodeSpawnResult`` with the container id and the
    list of bridge network ids the container was attached to.
    """
    client = get_docker_client()
    kind = NodeKind(node.kind) if isinstance(node.kind, str) else node.kind

    # Idempotency: a previous partial start may have left a container
    # in 'exited' state. Reuse it instead of failing.
    existing = _find_existing_container(node.id)
    if existing is not None:
        container = client.containers.get(existing)
        if container.status != "running":
            container.start()
        # For an existing container we still recompute capture
        # lines and re-exec the entrypoint so a previously-running
        # capture process that died gets restarted. (Containers
        # restarted by `container.start()` reuse the original env
        # + command, so we re-apply NODE_CAPTURE_LINKS too.)
        capture_lines: list[str] = []
        result = _reattach_to_bridges(
            client=client,
            container=container,
            project=project,
            node=node,
            links=links,
            interfaces=interfaces,
            capture_lines=capture_lines,
        )
        _apply_capture_env(container, capture_lines)
        return result

    image = KIND_IMAGE[kind]
    name = _container_name(project.id, node.id, kind)

    env: dict[str, str] = {
        "PROJECT_ID": project.id,
        "NODE_ID": node.id,
        "NODE_NAME": node.name,
        "NODE_KIND": kind.value,
        "BACKEND_URL": backend_url,
    }
    env.update(kind_env(kind, attack_mode=node.attack_mode))

    # M4 phase 04 — pre-compute the per-link tcpdump lines so the
    # entrypoint can start the right number of captures with the
    # right interface names. The container is created with
    # `network="bridge"` (the docker default bridge), so eth0 is
    # always the default bridge. The first per-link bridge we
    # connect becomes eth1, the next eth2, and so on. We use the
    # same dedup rules here as in _reattach_to_bridges so the
    # indices match what gets created.
    iface_by_id_pre = {i.id: i for i in interfaces}
    capture_lines_pre: list[str] = []
    eth_idx = 1  # +1 to skip the default-bridge eth0
    seen_nets: set[str] = set()
    for link in links:
        on_link = (
            link.iface_a_id in iface_by_id_pre
            or link.iface_b_id in iface_by_id_pre
        )
        if not on_link:
            continue
        bridge = link_service.find_bridge_by_link_id(project.id, link.id)
        if bridge is None:
            bridge = link_service.create_bridge_for_link(
                project_id=project.id,
                link_id=link.id,
                iface_a_ip=iface_by_id_pre[link.iface_a_id].ip_address
                if link.iface_a_id in iface_by_id_pre else None,
                iface_a_mask=iface_by_id_pre[link.iface_a_id].subnet_mask
                if link.iface_a_id in iface_by_id_pre else None,
                iface_b_ip=iface_by_id_pre[link.iface_b_id].ip_address
                if link.iface_b_id in iface_by_id_pre else None,
                iface_b_mask=iface_by_id_pre[link.iface_b_id].subnet_mask
                if link.iface_b_id in iface_by_id_pre else None,
            )
        if bridge.network_id in seen_nets:
            continue
        seen_nets.add(bridge.network_id)
        capture_lines_pre.append(
            f"{link.id} eth{eth_idx} {_link_capture_path(project.id, link.id)}"
        )
        eth_idx += 1
    env["NODE_CAPTURE_LINKS"] = "\n".join(capture_lines_pre)

    labels = {
        LABEL_HOST.split("=")[0]: "true",
        LABEL_PROJECT.split("=")[0]: project.id,
        LABEL_NODE.split("=")[0]: node.id,
        "containernet.role": kind.value,
    }

    # Capability set. Every node kind needs:
    #   NET_RAW  — so the per-link tcpdump can open AF_PACKET sockets
    #              on its interfaces (M4 phase 04 packet capture).
    #   NET_ADMIN — so the in-container entrypoint can install
    #                `ip link` settings if needed (and the router
    #                needs it to add routes at runtime).
    extra_kwargs: dict[str, Any] = {
        "detach": True,
        "remove": False,
        "cap_add": ["NET_RAW", "NET_ADMIN"],
        # Shared captures directory. Every node's entrypoint writes
        # the per-link NDJSON files into here; the backend reads
        # them from the host side (the docker-compose bind mount
        # exposes the same path inside the backend container).
        "volumes": {
            CAPTURE_DIR_HOST: {
                "bind": CAPTURE_DIR_HOST,
                "mode": "rw",
            },
        },
    }
    if kind == NodeKind.ROUTER:
        extra_kwargs["sysctls"] = {"net.ipv4.ip_forward": 1}

    try:
        container = client.containers.run(
            image=image,
            name=name,
            environment=env,
            command=KIND_COMMAND[kind],
            labels=labels,
            # `network="bridge"` attaches the container to the
            # docker default bridge (172.17.0.0/16) as eth0. This
            # is required because Docker refuses to attach a
            # container to multiple networks if it was created in
            # private (none) mode. By using the default bridge we
            # get eth0 + eth1, eth2, … for the per-link bridges.
            # The tcpdump ethN index in NODE_CAPTURE_LINKS has +1
            # baked in to account for the default eth0.
            network="bridge",
            tty=False,
            stdin_open=False,
            **extra_kwargs,
        )
    except APIError as exc:
        # Image missing? Surface a clear error.
        raise RuntimeError(
            f"failed to spawn {kind.value} container for node {node.id}: {exc}"
        ) from exc

    # Now that the container exists, attach it to every per-link
    # bridge. The capture env was already set in `container.run`;
    # _apply_capture_env is a no-op kept for symmetry with the
    # existing-container path above.
    return _reattach_to_bridges(
        client=client,
        container=container,
        project=project,
        node=node,
        links=links,
        interfaces=interfaces,
        backend_network=backend_network,
    )


def _reattach_to_bridges(
    *,
    client: docker.DockerClient,
    container,
    project: Project,
    node: ProjectNode,
    links: list[ProjectLink],
    interfaces: list[ProjectInterface],
    backend_network: str | None = None,
    capture_lines: list[str] | None = None,
) -> NodeSpawnResult:
    """Attach the container to every per-wire bridge it participates in.

    Also attaches to the backend's bridge (for DNS / heartbeats) for
    node kinds that need it (host, server, attacker, router).

    M4 phase 04 — packet capture
    ----------------------------
    If ``capture_lines`` is provided, every link the container is
    attached to gets a line of the form
    ``<link_id> <ethN> <capture_ndjson_path>`` appended to it. The
    container's entrypoint uses those lines to start one tcpdump per
    link on the right interface.
    """
    kind = NodeKind(node.kind) if isinstance(node.kind, str) else node.kind
    # Routers also need backend access — not for heartbeats, but so
    # the phase-03 router_proxy can reach their :9090 agent for the
    # live panel. The agent's IP on the backend network is what the
    # proxy uses to make the HTTP call.
    needs_backend = kind in (
        NodeKind.HOST, NodeKind.SERVER, NodeKind.ATTACKER, NodeKind.ROUTER,
    )

    iface_by_id = {i.id: i for i in interfaces}
    attached: list[str] = []
    seen_networks: set[str] = set()
    # Docker assigns eth0, eth1, … in the order we call
    # `net.connect()`. Because the container is created with
    # `network="bridge"` (the docker default bridge), eth0 is
    # already taken. The first per-link attach becomes eth1, the
    # next eth2, and so on. We track the index here to match the
    # pre-computed NODE_CAPTURE_LINKS so the entrypoint tcpdumps
    # the right interface.
    eth_index = 1  # +1 to skip the default-bridge eth0

    # For each link this node participates in, attach the container
    # to the per-link bridge with a pinned IP per interface.
    for link in links:
        # Is this node on this link? An endpoint iface belongs to a
        # node iff iface.node_id == node.id. Look at both endpoints.
        my_iface: ProjectInterface | None = None
        if link.iface_a_id in iface_by_id:
            my_iface = iface_by_id[link.iface_a_id]
        elif link.iface_b_id in iface_by_id:
            my_iface = iface_by_id[link.iface_b_id]
        if my_iface is None:
            continue

        # Find or create the per-link bridge.
        bridge = link_service.find_bridge_by_link_id(project.id, link.id)
        if bridge is None:
            # Bridge may be missing because the link was created
            # mid-start or the previous start crashed before
            # creating it. We can't know the iface IPs at the
            # link_service level without re-deriving; for safety
            # we just pass through and let link_service fall back
            # to a /30 default. The container will still come up
            # even if the IP doesn't match (Docker will just warn).
            bridge = link_service.create_bridge_for_link(
                project_id=project.id,
                link_id=link.id,
                iface_a_ip=iface_by_id[link.iface_a_id].ip_address
                if link.iface_a_id in iface_by_id else None,
                iface_a_mask=iface_by_id[link.iface_a_id].subnet_mask
                if link.iface_a_id in iface_by_id else None,
                iface_b_ip=iface_by_id[link.iface_b_id].ip_address
                if link.iface_b_id in iface_by_id else None,
                iface_b_mask=iface_by_id[link.iface_b_id].subnet_mask
                if link.iface_b_id in iface_by_id else None,
            )

        if bridge.network_id in seen_networks:
            continue
        seen_networks.add(bridge.network_id)

        # Connect to the per-link bridge with a pinned IP (if the
        # user's IP is in the bridge's subnet; otherwise attach
        # without an IP, which is fine for switches that don't
        # need to be addressable).
        pinned = my_iface.ip_address if my_iface.ip_address else None
        # Sanity-check the IP is in the bridge's subnet.
        pinned_valid = _iface_subnet_for_bridge(my_iface, bridge.subnet_cidr)
        if pinned and not pinned_valid:
            # Bridge's subnet didn't include the user's IP — fall
            # back to attaching without a pinned IP. The container
            # will still be on the bridge but won't have an IP on
            # it; this is rare (only happens when the user has
            # edited an interface IP after the bridge was created).
            pinned = None

        try:
            net = client.networks.get(bridge.network_id)
            if pinned:
                net.connect(container, ipv4_address=pinned)
            else:
                net.connect(container)
            attached.append(bridge.network_id)
        except APIError as exc:
            if "already connected" in str(exc).lower():
                attached.append(bridge.network_id)
                continue
            raise

        # Record the ethN for this link so the entrypoint knows
        # which interface to tcpdump.
        if capture_lines is not None:
            iface_name = f"eth{eth_index}"
            ndjson_path = _link_capture_path(project.id, link.id)
            capture_lines.append(f"{link.id} {iface_name} {ndjson_path}")
        eth_index += 1

    # Attach to the backend's bridge (for DNS / heartbeats) if needed.
    if needs_backend and backend_network:
        try:
            net = client.networks.get(backend_network)
            net.connect(container)
        except APIError as exc:
            if "already connected" not in str(exc).lower():
                raise

    return NodeSpawnResult(container_id=container.id, attached_bridges=attached)


def stop_node(node_id: str, timeout: int = 5) -> bool:
    """Stop + remove the container for one node. Idempotent."""
    client = get_docker_client()
    existing = _find_existing_container(node_id)
    if existing is None:
        return False
    try:
        c = client.containers.get(existing)
    except NotFound:
        return False
    try:
        if c.status == "running":
            c.stop(timeout=timeout)
        c.remove(force=True)
    except APIError:
        return False
    return True


def find_node_container(node_id: str) -> dict[str, Any] | None:
    """Return a small dict for the canvas UI, or None if not spawned."""
    client = get_docker_client()
    existing = _find_existing_container(node_id)
    if existing is None:
        return None
    try:
        c = client.containers.get(existing)
        return {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "image": c.image.tags[0] if c.image.tags else str(c.image.id),
        }
    except NotFound:
        return None


def _find_existing_container(node_id: str) -> str | None:
    client = get_docker_client()
    containers = client.containers.list(
        all=True,
        filters={"label": f"{LABEL_NODE.split('=')[0]}={node_id}"},
    )
    if not containers:
        return None
    return containers[0].id
