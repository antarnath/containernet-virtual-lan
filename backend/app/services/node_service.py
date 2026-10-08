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
"""

from __future__ import annotations

import ipaddress
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

# Command per kind. None means "use the image's default CMD/ENTRYPOINT".
KIND_COMMAND: dict[NodeKind, list[str] | None] = {
    NodeKind.HOST:     ["python3", "/app/host-agent/agent.py"],
    NodeKind.SWITCH:   None,  # image's ENTRYPOINT (sleep infinity)
    NodeKind.ROUTER:   None,  # image's ENTRYPOINT runs the router agent
    NodeKind.SERVER:   ["python3", "/app/host-agent/agent.py"],
    NodeKind.ATTACKER: ["python3", "/app/host-agent/agent.py"],
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
        return _reattach_to_bridges(
            client=client,
            container=container,
            project=project,
            node=node,
            links=links,
            interfaces=interfaces,
        )

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

    labels = {
        LABEL_HOST.split("=")[0]: "true",
        LABEL_PROJECT.split("=")[0]: project.id,
        LABEL_NODE.split("=")[0]: node.id,
        "containernet.role": kind.value,
    }

    # Routers need IP forwarding + NET_ADMIN to add routes at runtime.
    extra_kwargs: dict[str, Any] = {"detach": True, "remove": False}
    if kind == NodeKind.ROUTER:
        extra_kwargs["sysctls"] = {"net.ipv4.ip_forward": 1}
        extra_kwargs["cap_add"] = ["NET_ADMIN"]

    try:
        container = client.containers.run(
            image=image,
            name=name,
            environment=env,
            command=KIND_COMMAND[kind],
            labels=labels,
            network=None,  # we'll attach manually below
            tty=False,
            stdin_open=False,
            **extra_kwargs,
        )
    except APIError as exc:
        # Image missing? Surface a clear error.
        raise RuntimeError(
            f"failed to spawn {kind.value} container for node {node.id}: {exc}"
        ) from exc

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
) -> NodeSpawnResult:
    """Attach the container to every per-wire bridge it participates in.

    Also attaches to the backend's bridge (for DNS / heartbeats) for
    node kinds that need it (host, server, attacker).
    """
    kind = NodeKind(node.kind) if isinstance(node.kind, str) else node.kind
    needs_backend = kind in (NodeKind.HOST, NodeKind.SERVER, NodeKind.ATTACKER)

    iface_by_id = {i.id: i for i in interfaces}
    attached: list[str] = []
    seen_networks: set[str] = set()

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
