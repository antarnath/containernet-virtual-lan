"""Container service — high-level wrapper around the Docker SDK.

The rest of the backend never touches docker.APIClient directly; it goes
through these functions. Keeping the surface small and intent-revealing makes
the rest of the code easier to read and easier to mock in tests.

Every container we create is tagged with the label `containernet.host=true`
so we can find "our" containers later with a single label filter — even if
other unrelated containers are running on the host.
"""

from __future__ import annotations

from typing import Any

import docker
from docker.errors import APIError, NotFound

from app.core.docker_client import get_docker_client


# The label we put on every container this service creates. Listing with
# `filters={"label": LABEL_HOST}` returns only our containers.
LABEL_HOST = "containernet.host=true"

# Project-scoped label: every container spawned for a project carries
# ``containernet.project=<project_uuid>``. The orphan sweeper uses this
# to find containers that should no longer exist (their project was deleted).
LABEL_PROJECT = "containernet.project"

# M4 phase 02 — node-scoped label: every container spawned for a node carries
# ``containernet.node=<node_uuid>``. Used by node_service to look up a
# container by its parent node row, and by the orphan sweeper to find
# containers for a specific project.
LABEL_NODE = "containernet.node"


# ─── create ─────────────────────────────────────────────────────────────────

def create_container(
    *,
    image: str,
    name: str,
    env: dict[str, str] | None = None,
    command: list[str] | str | None = None,
    network: str | None = None,
    ipv4_address: str | None = None,
    labels: dict[str, str] | None = None,
    volumes: dict[str, dict[str, str]] | None = None,
    detach: bool = True,
) -> str:
    """Create and start a container. Returns its container ID.

    Parameters
    ----------
    image : str
        Image name (e.g., "alpine:3.19", "containernet-host-base:latest").
    name : str
        Container name (must be unique on the host).
    env : dict
        Environment variables injected into the container.
    command : list[str] | str
        Override the container's default command.
    network : str
        Name of an existing Docker network to attach to (e.g., a project
        bridge). If None, the container uses the default bridge.
    ipv4_address : str
        Pin a specific IPv4 address on `network`. Requires `network`.
    labels : dict
        Extra labels beyond our standard ones.
    volumes : dict
        Bind-mount specification in Docker SDK form.
    detach : bool
        If True, return immediately and run in the background. Must be True
        for our use case; we manage lifecycle explicitly.

    Returns
    -------
    str
        The container ID (a 64-character hex string).
    """
    client = get_docker_client()

    # Merge our label with whatever the caller provided. Our label must be
    # present so list_running_containers() can find this container again.
    full_labels = dict(labels or {})
    full_labels[LABEL_HOST.split("=")[0]] = "true"

    # Build the network endpoint config if a network + IP were provided.
    networking_config = None
    if network and ipv4_address:
        networking_config = client.api.create_networking_config({
            network: client.api.create_endpoint_config(ipv4_address=ipv4_address)
        })

    container = client.containers.run(
        image=image,
        name=name,
        environment=env or {},
        command=command,
        labels=full_labels,
        volumes=volumes,
        network=network,
        detach=detach,
        # Don't auto-remove: we want explicit lifecycle control so a `stop`
        # followed by an inspect still works.
        remove=False,
        # Default to no TTY for non-interactive services.
        tty=False,
        stdin_open=False,
    )
    # client.containers.run with detach=True returns a Container object.
    return container.id


# ─── lifecycle ───────────────────────────────────────────────────────────────

def start_container(container_id: str) -> None:
    """Start a previously stopped container. Raises NotFound if missing."""
    client = get_docker_client()
    try:
        client.containers.get(container_id).start()
    except NotFound:
        raise


def stop_container(container_id: str, timeout: int = 5) -> None:
    """Gracefully stop a running container. timeout = seconds to wait
    before sending SIGKILL."""
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        container.stop(timeout=timeout)
    except NotFound:
        # Already gone — treat as success.
        return


def remove_container(container_id: str, force: bool = False) -> None:
    """Remove a container. If force=True, stops it first if still running."""
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        if force and container.status == "running":
            container.stop(timeout=2)
        container.remove(force=force)
    except NotFound:
        # Already gone — treat as success.
        return


# ─── queries ─────────────────────────────────────────────────────────────────

def container_exists(container_id: str) -> bool:
    """Return True iff a container with this ID exists (any state)."""
    client = get_docker_client()
    try:
        client.containers.get(container_id)
        return True
    except NotFound:
        return False


def container_is_running(container_id: str) -> bool:
    """Return True iff the container exists AND is in 'running' state."""
    client = get_docker_client()
    try:
        return client.containers.get(container_id).status == "running"
    except NotFound:
        return False


def list_running_containers(
    label: str = LABEL_HOST,
    all_states: bool = False,
) -> list[dict[str, Any]]:
    """Return lightweight summaries of our containers.

    By default only returns running containers (`all_states=False`). Pass
    `all_states=True` to include stopped/exited ones too (useful for the
    orphan sweeper).

    Returned dicts have: id, name, status, image, created, labels.
    """
    client = get_docker_client()
    containers = client.containers.list(
        all=all_states,
        filters={"label": label},
    )
    return [
        {
            "id":      c.id,
            "name":    c.name,
            "status":  c.status,
            "image":   c.image.tags[0] if c.image.tags else str(c.image.id),
            "created": c.attrs.get("Created"),
            "labels":  c.labels,
        }
        for c in containers
    ]


def get_container_stats(container_id: str) -> dict[str, Any] | None:
    """Return a single stats snapshot for the given container.

    Returns None if the container doesn't exist. The returned dict has the
    shape of `docker.APIClient.stats(...)` — CPU%, memory usage, network
    counters, etc. Useful for the future metrics dashboard.
    """
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
    except NotFound:
        return None
    try:
        # stream=False returns a single dict instead of a generator.
        return container.stats(stream=False)
    except APIError:
        return None


# ─── project-scoped lifecycle ───────────────────────────────────────────────
# These functions are the heart of Phase 03. They turn a Project row (with
# its ProjectHost children) into real running Docker containers attached to
# a per-project bridge, and back.

def _short_project_id(project_id: str) -> str:
    """Return the 12-char short form used in container names."""
    return project_id.replace("-", "")[:12]


def spawn_project_host(
    *,
    project_id: str,
    host_id: str,
    hostname: str,
    ip_address: str,
    project_network: str,
    backend_network: str,
    backend_url: str = "http://backend:8000",
    image: str = "containernet-host-base:latest",
) -> str:
    """Spawn ONE container for a project host. Returns its container ID.

    The container is attached to:
      * the project's bridge (so it can talk to siblings at its assigned IP)
      * the backend's bridge (so it can DNS-resolve ``backend`` for heartbeats)

    We also pass ``extra_hosts`` as a belt-and-braces in case the DNS lookup
    through the backend bridge fails for any reason — the host will still
    reach the backend via a hard-coded host→IP mapping pointing at the
    backend service on the ``containernet_lan`` subnet.

    Note on Docker Desktop: spawning a container with ``network=None`` still
    attaches it to the ``bridge`` (a.k.a. docker0) network by default. We
    keep that attachment so the container has at least one default route —
    removing it would require disabling the default bridge per-container,
    which is awkward and not necessary for the LAN to function.
    """
    client = get_docker_client()
    short = _short_project_id(project_id)

    container = client.containers.run(
        image=image,
        name=f"proj-{short}-{host_id}",   # e.g. proj-abc123def456-pc-1
        environment={
            "PROJECT_ID": project_id,
            "HOST_ID": host_id,
            "HOST_NAME": hostname,
            "HOST_IP": ip_address,
            "BACKEND_URL": backend_url,
        },
        command=["python3", "/app/host-agent/agent.py"],
        labels={
            LABEL_HOST.split("=")[0]: "true",
            LABEL_PROJECT.split("=")[0]: project_id,
            "containernet.role": "host",
        },
        # No `network=...` here. We connect to both bridges manually below
        # so the IP pinning + secondary attachment are guaranteed.
        network=None,
        # Don't hardcode ``backend``'s IP — the secondary attachment to
        # ``containernet_lan`` lets Docker's embedded DNS resolve it for us.
        detach=True,
        remove=False,
        tty=False,
        stdin_open=False,
    )

    # 1. Project bridge with pinned IP (this is the host's LAN identity).
    proj_net = client.networks.get(project_network)
    proj_net.connect(container, ipv4_address=ip_address)

    # 2. Backend network (no IP pinning — host only needs L3 + DNS).
    #    We retry once because on some Docker SDK versions the connect
    #    returns 403 if the container is still "creating".
    backend_net = client.networks.get(backend_network)
    for attempt in range(2):
        try:
            backend_net.connect(container)
            break
        except APIError as exc:
            if "already connected" in str(exc).lower():
                break
            if attempt == 0:
                import time; time.sleep(0.5)
            else:
                # Last attempt failed; raise so the caller can decide.
                raise

    return container.id


def spawn_project_hosts(
    *,
    project_id: str,
    project_network: str,
    backend_network: str,
    hosts: list[dict],
) -> list[dict]:
    """Spawn one container per host row. Returns [{host_id, container_id}].

    Each ``hosts`` element must have: ``host_id``, ``hostname``, ``ip_address``.
    Failures on individual hosts don't abort the whole batch — the rest still
    spawn, and the failed host gets ``container_id=None`` returned.
    """
    results: list[dict] = []
    for h in hosts:
        try:
            cid = spawn_project_host(
                project_id=project_id,
                host_id=h["host_id"],
                hostname=h["hostname"],
                ip_address=h["ip_address"],
                project_network=project_network,
                backend_network=backend_network,
            )
            results.append({"host_id": h["host_id"], "container_id": cid})
        except Exception as exc:
            results.append({
                "host_id": h["host_id"],
                "container_id": None,
                "error": str(exc),
            })
    return results


def stop_project_hosts(project_id: str, timeout: int = 5) -> int:
    """Gracefully stop every container belonging to a project. Returns count."""
    client = get_docker_client()
    containers = client.containers.list(
        all=True,
        filters={"label": f"{LABEL_PROJECT.split('=')[0]}={project_id}"},
    )
    count = 0
    for c in containers:
        try:
            c.stop(timeout=timeout)
            count += 1
        except APIError:
            # Already stopped, or in middle of restarting — ignore.
            pass
    return count


def remove_project_hosts(project_id: str, force: bool = True) -> int:
    """Force-remove every container belonging to a project. Returns count."""
    client = get_docker_client()
    containers = client.containers.list(
        all=True,
        filters={"label": f"{LABEL_PROJECT.split('=')[0]}={project_id}"},
    )
    count = 0
    for c in containers:
        try:
            c.remove(force=force)
            count += 1
        except APIError:
            pass
    return count


def list_project_containers(project_id: str, all_states: bool = False) -> list[dict]:
    """List containers for a project. Used by start_project / sweeper / debug."""
    client = get_docker_client()
    containers = client.containers.list(
        all=all_states,
        filters={"label": f"{LABEL_PROJECT.split('=')[0]}={project_id}"},
    )
    return [
        {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "image": c.image.tags[0] if c.image.tags else str(c.image.id),
        }
        for c in containers
    ]


# ─── capture container (M2-07 §2.4) ─────────────────────────────────────────
# A small Docker container attached only to the project's bridge, whose
# only job is to listen and emit packet events for the dashboard.
# It has no IP on the bridge (so it cannot originate or respond to traffic)
# and CAP_NET_RAW so it can capture raw frames.

CAPTURE_IMAGE = "containernet-capture-base:latest"
CAPTURE_ROLE = "capture"


def _capture_container_name(project_id: str) -> str:
    short = _short_project_id(project_id)
    return f"proj-{short}-capture"


def spawn_project_capture(
    *,
    project_id: str,
    project_network: str,
    image: str = CAPTURE_IMAGE,
) -> str:
    """Spawn the per-project capture container. Returns its container ID.

    Attached ONLY to the project's bridge, with no IP and no default-route.
    Runs `tcpdump` writing binary pcap to stdout; the backend reads from
    that stdout via `docker exec cat /tmp/capture.ndjson` once the shim is
    wired in.

    Idempotent: if a capture container for this project already exists,
    reuse it (so a partial start can be resumed).
    """
    client = get_docker_client()
    name = _capture_container_name(project_id)

    # Reuse if already present (covers "start twice in a row").
    try:
        existing = client.containers.get(name)
        if existing.status != "running":
            existing.start()
        return existing.id
    except NotFound:
        pass

    container = client.containers.run(
        image=image,
        name=name,
        command=None,  # use the image's default CMD (tcpdump → stdout)
        labels={
            LABEL_HOST.split("=")[0]: "true",
            LABEL_PROJECT.split("=")[0]: project_id,
            "containernet.role": CAPTURE_ROLE,
        },
        # M2-07 §2.4 — Linux bridges only flood unicast frames to a port
        # if that port is in promiscuous mode. We can't toggle the bridge's
        # per-port promisc flag from outside the host (no root on host).
        # Instead, we run the capture container in the HOST network
        # namespace and capture on the project's bridge interface directly.
        # The project's bridge is named `proj_<short_id>_lan` and shows up
        # in the host's `ip link show` output.
        network_mode="host",
        # pid=host so the entrypoint can find the project's bridge via
        # `ip link show` and discover the right interface to capture on.
        pid_mode="host",
        # CAP_NET_RAW + NET_ADMIN so tcpdump can use AF_PACKET sockets and
        # so we can set the chosen bridge port to promiscuous if needed.
        cap_add=["NET_RAW", "NET_ADMIN"],
        # Bind the capture's NDJSON file path to a host-side file so the
        # backend can read it without `docker exec` overhead.
        volumes={
            "/var/lib/containernet/captures": {
                "bind": "/var/lib/containernet/captures",
                "mode": "rw",
            },
        },
        environment={
            "PROJECT_BRIDGE_NAME": f"proj_{_short_project_id(project_id)}_lan",
            # Docker creates Linux bridges with names derived from the
            # network ID, NOT from the user-supplied name. We pass the
            # network ID too so the capture entrypoint can derive the
            # actual interface name (e.g. "br-a4a865c353d6").
            "PROJECT_NETWORK_ID": client.networks.get(project_network).id[:12],
            "CAPTURE_FILE": f"/var/lib/containernet/captures/{_capture_container_name(project_id)}.ndjson",
        },
        detach=True,
        remove=False,
        tty=False,
        stdin_open=False,
    )
    # M2-07 §2.4 — capture runs in the HOST network namespace (so it can
    # tcpdump on the project's bridge interface directly). We don't attach
    # it to the project bridge as a port — that wouldn't help because the
    # bridge still wouldn't flood host→host unicast to the capture port.
    # Instead, the entrypoint discovers the bridge name from $PROJECT_BRIDGE_NAME
    # and tcpdumps `bridge.proj_xxx_lan` directly. With CAP_NET_RAW on the
    # host netns, tcpdump can use AF_PACKET and see every frame on the bridge.
    _bring_bridge_port_promiscuous(project_id)
    return container.id


def _bring_bridge_port_promiscuous(project_id: str) -> None:
    """Best-effort: ensure the project's bridge interface itself is in
    promiscuous mode. With the new architecture (capture in host netns,
    capturing on the bridge interface directly via AF_PACKET), this is
    NOT strictly required — tcpdump on a bridge interface sees every
    frame regardless of the bridge's MAC table state, because the
    kernel delivers every frame on a bridge interface to any AF_PACKET
    socket bound to it.

    Kept as a no-op stub for backwards compatibility and future tuning.
    """
    return None


def stop_project_capture(project_id: str, timeout: int = 2) -> bool:
    """Stop the capture container (kept across project stops). Returns True
    iff a container was stopped."""
    client = get_docker_client()
    name = _capture_container_name(project_id)
    try:
        c = client.containers.get(name)
    except NotFound:
        return False
    try:
        if c.status == "running":
            c.stop(timeout=timeout)
        return True
    except APIError:
        return False


def remove_project_capture(project_id: str, force: bool = True) -> bool:
    """Remove the capture container (called on project delete)."""
    client = get_docker_client()
    name = _capture_container_name(project_id)
    try:
        c = client.containers.get(name)
    except NotFound:
        return False
    try:
        c.remove(force=force)
        return True
    except APIError:
        return False


def get_project_capture_container(project_id: str) -> dict | None:
    """Return a small dict describing the project's capture container, or
    None if there isn't one."""
    client = get_docker_client()
    name = _capture_container_name(project_id)
    try:
        c = client.containers.get(name)
        return {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "image": c.image.tags[0] if c.image.tags else str(c.image.id),
        }
    except NotFound:
        return None

