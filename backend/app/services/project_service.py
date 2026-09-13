"""Project service — orchestrates the project lifecycle.

The service is the single source of truth for what happens when a project
is created, fetched, updated, or deleted. The API layer (api/projects.py)
is a thin wrapper that just calls these functions.

Phase 2 responsibilities (this file):
  * create_project — generate topology graph + persist
  * get_project    — fetch with eager-loaded hosts + edges
  * list_projects  — summary listing
  * delete_project — remove (Phase 3 will cascade to containers/networks)
  * update_node_position — drag-and-drop persistence

Phase 3 will add start_project / stop_project (container lifecycle).
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
)
from app.schemas.project import ProjectCreateIn
from app.services.topology_generator import (
    BadSubnetError,
    generate_topology,
)


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
    except BadSubnetError:
        raise
    except ValueError:
        raise

    network = IPv4Network(body.subnet, strict=False)
    gateway = str(IPv4Address(int(network.network_address) + 1))

    project = Project(
        name=body.name,
        topology_type=body.topology_type,
        host_count=body.host_count,
        subnet=body.subnet,
        gateway=gateway,
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


# ─── delete ─────────────────────────────────────────────────────────────────

async def delete_project(session: AsyncSession, project_id: str) -> bool:
    """Remove a project and its hosts/edges. Returns True if anything was
    removed. Phase 03 will also stop+remove containers before this fires."""
    result = await session.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalars().first()
    if project is None:
        return False
    await session.delete(project)
    await session.commit()
    return True
