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
