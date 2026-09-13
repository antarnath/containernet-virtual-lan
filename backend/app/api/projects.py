"""REST endpoints for /api/projects.

Phase 02 endpoints
------------------
  POST   /api/projects                       create a project (no containers yet)
  GET    /api/projects                       list all projects (summary)
  GET    /api/projects/{project_id}          fetch one project + topology
  PATCH  /api/projects/{project_id}/nodes/{host_id}   update a node position
  DELETE /api/projects/{project_id}          delete a project + topology

Phase 03 endpoints
------------------
  POST   /api/projects/{project_id}/start    spawn containers
  POST   /api/projects/{project_id}/stop     stop containers (keep project)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session
from app.schemas.project import (
    NodePositionIn,
    ProjectCreateIn,
    ProjectDetailOut,
    ProjectEdgeOut,
    ProjectHostOut,
    ProjectListResponse,
    ProjectOut,
)
from app.services import project_service
from app.services.topology_generator import BadSubnetError


router = APIRouter(prefix="/projects", tags=["projects"])


# ─── helpers ────────────────────────────────────────────────────────────────

def _status_value(p) -> str:
    return p.status.value if hasattr(p.status, "value") else p.status


def _project_out(p) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        name=p.name,
        topology_type=p.topology_type,
        host_count=p.host_count,
        subnet=p.subnet,
        gateway=p.gateway,
        status=_status_value(p),
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _host_out(h) -> ProjectHostOut:
    return ProjectHostOut(
        id=h.id,
        host_id=h.host_id,
        hostname=h.hostname,
        ip_address=h.ip_address,
        container_id=h.container_id,
        position_x=h.position_x,
        position_y=h.position_y,
        status=h.status.value if hasattr(h.status, "value") else h.status,
        last_seen=h.last_seen,
        created_at=h.created_at,
    )


def _edge_out(e) -> ProjectEdgeOut:
    return ProjectEdgeOut(
        id=e.id,
        source_host_id=e.source_host_id,
        dest_host_id=e.dest_host_id,
    )


# ─── endpoints ──────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=ProjectDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    body: ProjectCreateIn,
    session: AsyncSession = Depends(get_session),
):
    """Create a new project. Generates topology graph + persists."""
    try:
        project = await project_service.create_project(session, body)
    except BadSubnetError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Re-fetch with eager-loaded relationships for the response.
    project = await project_service.get_project(session, project.id)
    assert project is not None  # we just created it

    return ProjectDetailOut(
        **_project_out(project).model_dump(),
        hosts=[_host_out(h) for h in project.hosts],
        edges=[_edge_out(e) for e in project.edges],
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(session: AsyncSession = Depends(get_session)):
    """List all projects (summary view, no topology)."""
    projects = await project_service.list_projects(session)
    return ProjectListResponse(
        projects=[_project_out(p) for p in projects],
        total=len(projects),
    )


@router.get("/{project_id}", response_model=ProjectDetailOut)
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Fetch one project with full topology (hosts + edges)."""
    project = await project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectDetailOut(
        **_project_out(project).model_dump(),
        hosts=[_host_out(h) for h in project.hosts],
        edges=[_edge_out(e) for e in project.edges],
    )


@router.patch(
    "/{project_id}/nodes/{host_id}",
    response_model=ProjectHostOut,
)
async def update_node_position(
    project_id: str,
    host_id: str,
    body: NodePositionIn,
    session: AsyncSession = Depends(get_session),
):
    """Persist a drag-and-drop position update. Idempotent."""
    row = await project_service.update_node_position(
        session,
        project_id=project_id,
        host_id=host_id,
        position_x=body.position_x,
        position_y=body.position_y,
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"host {host_id!r} not found in project {project_id!r}",
        )
    return _host_out(row)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a project: stops+removes containers, removes bridge, deletes DB."""
    deleted = await project_service.delete_project(session, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="project not found")
    # 204 No Content: empty body
    return None


@router.post("/{project_id}/start", response_model=ProjectDetailOut)
async def start_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Spawn containers for every host on the project's bridge.

    Idempotent: re-running just re-uses existing containers if any.
    Status field becomes ``running`` (or ``partial`` if some hosts failed).
    """
    project = await project_service.start_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectDetailOut(
        **_project_out(project).model_dump(),
        hosts=[_host_out(h) for h in project.hosts],
        edges=[_edge_out(e) for e in project.edges],
    )


@router.post("/{project_id}/stop", response_model=ProjectDetailOut)
async def stop_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Gracefully stop every container in the project. Keeps project + DB rows."""
    project = await project_service.stop_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectDetailOut(
        **_project_out(project).model_dump(),
        hosts=[_host_out(h) for h in project.hosts],
        edges=[_edge_out(e) for e in project.edges],
    )
