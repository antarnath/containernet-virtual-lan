"""Orphan cleanup — runs once at backend startup.

If the backend is restarted (or crashes and recovers), Docker containers
and networks spawned in a previous run may still exist on the host with no
corresponding project in the DB. This module finds them and tears them
down.

Two classes of orphans:
  1. Containers labeled ``containernet.project=<uuid>`` whose project no
     longer exists in the DB → force-remove.
  2. Networks labeled ``containernet.bridge=true`` whose project no longer
     exists in the DB → remove.

Both are safe to run: each one is a no-op if nothing is orphaned.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.docker_client import get_docker_client
from app.models import Project
from app.services import container_service, network_service
from app.services.container_service import LABEL_PROJECT


async def sweep_orphans(session: AsyncSession) -> dict:
    """Run the full orphan sweep. Returns a stats dict.

    Stats shape:
        removed_containers: int
        removed_networks:   int
        live_projects:      int  (sanity check)
    """
    # 1. Collect live project IDs
    result = await session.execute(select(Project.id))
    live_project_ids = {row[0] for row in result.all()}

    client = get_docker_client()

    # 2. Find orphan containers
    containers = client.containers.list(
        all=True,
        filters={"label": LABEL_PROJECT.split("=")[0]},
    )
    removed_containers = 0
    for c in containers:
        proj_id = c.labels.get(LABEL_PROJECT.split("=")[0])
        if proj_id and proj_id not in live_project_ids:
            try:
                c.remove(force=True)
                removed_containers += 1
            except Exception:
                pass

    # 3. Find orphan networks
    networks = client.networks.list(
        filters={"label": "containernet.bridge"}
    )
    removed_networks = 0
    for n in networks:
        proj_id = n.attrs.get("Labels", {}).get(LABEL_PROJECT.split("=")[0])
        if proj_id and proj_id not in live_project_ids:
            try:
                n.remove()
                removed_networks += 1
            except Exception:
                pass

    return {
        "removed_containers": removed_containers,
        "removed_networks": removed_networks,
        "live_projects": len(live_project_ids),
    }
