"""Network service — per-project Docker bridge lifecycle.

Each ContainerNet project owns exactly one Docker bridge network so that
hosts from different projects can never see each other's traffic, even
though they all coexist on the same Docker host.

Network naming
--------------
``proj_<project_uuid_short>_lan`` — short UUID keeps the bridge name under
Docker's 64-char limit while staying practically unique.

Subnets
-------
The bridge's subnet comes straight from the project's ``subnet`` field
(e.g. ``10.50.0.0/24``). The gateway is auto-assigned at the second IP of
the subnet (``10.50.0.1``).

When a project is deleted, the bridge is removed. If containers are still
attached, Docker refuses the removal — we force-remove containers first
in ``project_service.delete_project`` before calling ``remove_project_network``.
"""

from __future__ import annotations

import docker
from docker.errors import APIError, NotFound

from app.core.docker_client import get_docker_client
from app.models import Project


# Network labels so orphan sweepers can find our bridges.
LABEL_PROJECT = "containernet.project"          # = project UUID
LABEL_BRIDGE  = "containernet.bridge=true"


# ─── naming ─────────────────────────────────────────────────────────────────

def network_name_for(project_id: str) -> str:
    """Return the deterministic Docker network name for a project.

    Uses the first 12 chars of the UUID — collision probability is
    negligible for an academic project, and it keeps us well under
    Docker's 64-char name limit.
    """
    short = project_id.replace("-", "")[:12]
    return f"proj_{short}_lan"


# ─── create ─────────────────────────────────────────────────────────────────

def create_project_network(project: Project) -> str:
    """Create the per-project bridge network. Returns its Docker name.

    Idempotent: if a network with this name already exists (e.g. left over
    from a previous run), we re-use it.
    """
    client = get_docker_client()
    name = network_name_for(project.id)
    try:
        existing = client.networks.get(name)
        existing.reload()
        return existing.name
    except NotFound:
        pass

    # ipam expects subnet strings per network
    ipam_config = docker.types.IPAMConfig(
        pool_configs=[
            docker.types.IPAMPool(
                subnet=project.subnet,
                gateway=project.gateway,
            )
        ]
    )

    network = client.networks.create(
        name=name,
        driver="bridge",
        labels={
            LABEL_PROJECT.split("=")[0]: project.id,
            LABEL_BRIDGE.split("=")[0]: "true",
        },
        ipam=ipam_config,
        # Inter-container communication is on by default for bridges, so we
        # only pass through options that Docker actually accepts as strings.
        options={"icc": "true"},
    )
    return network.name


# ─── remove ─────────────────────────────────────────────────────────────────

def remove_project_network(project_id: str) -> bool:
    """Remove the project's bridge. Returns True if removed, False if absent.

    If containers are still attached the API will raise an error; the caller
    is expected to remove those containers first.
    """
    client = get_docker_client()
    name = network_name_for(project_id)
    try:
        network = client.networks.get(name)
    except NotFound:
        return False
    try:
        network.reload()
        network.remove()
        return True
    except APIError:
        return False


# ─── queries ────────────────────────────────────────────────────────────────

def list_project_networks() -> list[dict]:
    """Return all bridges we created (labeled containernet.bridge=true)."""
    client = get_docker_client()
    networks = client.networks.list(
        filters={"label": LABEL_BRIDGE}
    )
    return [
        {
            "id": n.id,
            "name": n.name,
            "labels": n.attrs.get("Labels", {}),
        }
        for n in networks
    ]


def network_for_project(project_id: str) -> str | None:
    """Return the network name for a project, or None if not created yet."""
    client = get_docker_client()
    name = network_name_for(project_id)
    try:
        net = client.networks.get(name)
        return net.name
    except NotFound:
        return None
