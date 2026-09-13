"""Project service — orchestrates the project lifecycle.

The service is the single source of truth for what happens when a project
is created, fetched, updated, or deleted. The API layer (api/projects.py)
is a thin wrapper that just calls these functions.

Phase 02 responsibilities
  * create_project — generate topology graph + persist
  * get_project    — fetch with eager-loaded hosts + edges
  * list_projects  — summary listing
  * delete_project — remove (DB rows; cascade to hosts + edges)
  * update_node_position — drag-and-drop persistence

Phase 03 responsibilities
  * start_project  — create bridge + spawn containers for every host
  * stop_project   — stop every container, keep project + DB rows
  * delete_project — stop+remove containers, remove bridge, delete DB rows
"""

from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Project,
    ProjectEdge,
    ProjectHost,
    ProjectStatus,
)
from app.schemas.project import ProjectCreateIn
from app.services import container_service, network_service
from app.services.topology_generator import (
    BadSubnetError,
    generate_topology,
)


# The backend's own Docker network. Spawned hosts are attached to this so
# they can DNS-resolve `backend:8000` for heartbeats. Docker Compose
# prefixes the directory name to user-defined network names, so the
# container-level network is ``containernet_containernet_lan``.
BACKEND_NETWORK = "containernet_containernet_lan"


# ─── create ─────────────────────────────────────────────────────────────────

async def create_project(
    session: AsyncSession,
    body: ProjectCreateIn,
) -> Project:
    """Generate topology + persist a new project. Returns the Project row.

    Raises
    ------
    ValueError
        Topology type unknown.
    BadSubnetError
        Subnet can't fit the requested host count or overlaps a reserved
        range.
    """
    try:
        nodes, edges = generate_topology(
            topology_type=body.topology_type,
            host_count=body.host_count,
            subnet=body.subnet,
        )
    except (BadSubnetError, ValueError):
        raise

    network = IPv4Network(body.subnet, strict=False)
    gateway = str(IPv4Address(int(network.network_address) + 1))

    project = Project(
        name=body.name,
        topology_type=body.topology_type,
        host_count=body.host_count,
        subnet=body.subnet,
        gateway=gateway,
        status=ProjectStatus.DRAFT,
    )
    session.add(project)
    await session.flush()  # we need project.id for the FK

    for node in nodes:
        session.add(ProjectHost(
            project_id=project.id,
            host_id=node.host_id,
            hostname=node.hostname,
            ip_address=node.ip_address,
            position_x=node.position_x,
            position_y=node.position_y,
        ))

    for edge in edges:
        session.add(ProjectEdge(
            project_id=project.id,
            source_host_id=edge.source_host_id,
            dest_host_id=edge.dest_host_id,
        ))

    await session.commit()
    await session.refresh(project)
    return project


# ─── reads ──────────────────────────────────────────────────────────────────

async def list_projects(session: AsyncSession) -> list[Project]:
    """Return all projects, newest first. No eager loads (summary view)."""
    result = await session.execute(
        select(Project).order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())


async def get_project(session: AsyncSession, project_id: str) -> Project | None:
    """Return a project with its hosts + edges eagerly loaded, or None."""
    result = await session.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.hosts),  # type: ignore[attr-defined]
            selectinload(Project.edges),  # type: ignore[attr-defined]
        )
    )
    return result.scalars().first()


# ─── update ─────────────────────────────────────────────────────────────────

async def update_node_position(
    session: AsyncSession,
    project_id: str,
    host_id: str,
    position_x: float,
    position_y: float,
) -> ProjectHost | None:
    """Persist a drag-and-drop position update. Returns the updated row
    (or None if the project / host doesn't exist)."""
    result = await session.execute(
        select(ProjectHost).where(
            ProjectHost.project_id == project_id,
            ProjectHost.host_id == host_id,
        )
    )
    row = result.scalars().first()
    if row is None:
        return None
    row.position_x = position_x
    row.position_y = position_y
    await session.commit()
    await session.refresh(row)
    return row


# ─── lifecycle: start ───────────────────────────────────────────────────────

async def start_project(session: AsyncSession, project_id: str) -> Project | None:
    """Create bridge + spawn containers for every host. Returns updated Project.

    Steps
    -----
    1. Load project + hosts.
    2. Create (or re-attach to) the per-project bridge network.
    3. Spawn one container per host, attaching each to both the project
       bridge (with a pinned IP) and the backend's network.
    4. Update each ProjectHost row with its container_id.
    5. Set project status to RUNNING.

    Idempotent: if containers already exist for this project (e.g. partial
    state from a previous run), we don't double-spawn — we record their IDs.
    """
    project = await get_project(session, project_id)
    if project is None:
        return None

    # 1. Bridge
    net_name = network_service.create_project_network(project)

    # 2. Spawn
    hosts_data = [
        {
            "host_id": h.host_id,
            "hostname": h.hostname,
            "ip_address": h.ip_address,
        }
        for h in project.hosts
    ]
    spawn_results = container_service.spawn_project_hosts(
        project_id=project.id,
        project_network=net_name,
        backend_network=BACKEND_NETWORK,
        hosts=hosts_data,
    )

    # 3. Persist container_ids back to DB rows
    by_host_id = {r["host_id"]: r for r in spawn_results}
    for h in project.hosts:
        result = by_host_id.get(h.host_id)
        if result and result.get("container_id"):
            h.container_id = result["container_id"]
            h.status = "online"  # will be corrected by first heartbeat

    # 4. Status — partial if any host failed to spawn
    any_failed = any(r.get("error") for r in spawn_results)
    project.status = ProjectStatus.PARTIAL if any_failed else ProjectStatus.RUNNING

    await session.commit()
    await session.refresh(project)
    return project


# ─── lifecycle: stop ────────────────────────────────────────────────────────

async def stop_project(session: AsyncSession, project_id: str) -> Project | None:
    """Stop every container belonging to the project. Keeps project + DB rows.

    Status transitions to STOPPED. ProjectHost.container_id is preserved so
    the user can hit /start again to re-attach to the same containers.
    """
    project = await get_project(session, project_id)
    if project is None:
        return None

    stopped = container_service.stop_project_hosts(project_id)
    project.status = ProjectStatus.STOPPED
    await session.commit()
    await session.refresh(project)
    return project


# ─── lifecycle: delete ──────────────────────────────────────────────────────

async def delete_project(session: AsyncSession, project_id: str) -> bool:
    """Tear down everything: containers, bridge, DB rows. Idempotent.

    Order matters:
      1. Force-remove containers (so the bridge isn't left dangling).
      2. Remove the bridge network.
      3. Delete the project row (cascade removes hosts + edges).
    """
    # 1. Containers
    container_service.remove_project_hosts(project_id, force=True)

    # 2. Network
    network_service.remove_project_network(project_id)

    # 3. DB
    result = await session.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()
    if project is None:
        return False
    await session.delete(project)
    await session.commit()
    return True
