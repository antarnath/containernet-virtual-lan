"""Hosts listing endpoints.

Phase 05 surface
----------------

We expose BOTH:

* The legacy global ``GET /api/hosts`` — flat list across every project
  (also still picks up legacy static pc1/pc2/pc3 rows). Kept for backwards
  compatibility with the original dashboard; marked deprecated in OpenAPI.

* The new per-project endpoints:

    GET /api/projects/{project_id}/hosts
        -> ProjectHostListResponse — hosts of ONE project

    GET /api/projects/{project_id}/hosts/{host_id}
        -> ProjectHostOut — one host row

    GET /api/projects/{project_id}/hosts/{host_id}/metrics
        -> Prometheus-style text body fetched from the host's own agent
           (proxied so the browser doesn't need to reach into the LAN).

The per-project endpoints are what the new ``/projects/:id/hosts`` page and
the topology LED wiring consume.
"""

from __future__ import annotations

import httpx

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session
from app.schemas.host import HostListResponse, HostOut
from app.schemas.project import ProjectHostListResponse, ProjectHostOut
from app.services import host_service


# Two routers — one for each URL prefix — keeps the legacy /hosts working
# while the per-project endpoints live under /projects.
legacy_router = APIRouter(prefix="/hosts", tags=["hosts (legacy)"])
project_router = APIRouter(prefix="/projects", tags=["hosts (per project)"])


# ─── helpers ────────────────────────────────────────────────────────────────

def _status_str(s) -> str:
    return s.value if hasattr(s, "value") else s


def _host_out(h) -> ProjectHostOut:
    return ProjectHostOut(
        id=h.id,
        host_id=h.host_id,
        hostname=h.hostname,
        ip_address=h.ip_address,
        container_id=h.container_id,
        position_x=h.position_x,
        position_y=h.position_y,
        status=_status_str(h.status),
        last_seen=h.last_seen,
        created_at=h.created_at,
    )


def _legacy_host_out(h) -> HostOut:
    return HostOut(
        id=h.id,
        host_id=h.host_id,
        hostname=h.hostname,
        ip_address=h.ip_address,
        status=_status_str(h.status),
        last_seen=h.last_seen,
        created_at=h.created_at,
    )


# ─── legacy global endpoints (kept for transition) ─────────────────────────

@legacy_router.get("", response_model=HostListResponse, deprecated=True)
async def get_hosts(session: AsyncSession = Depends(get_session)):
    """Flat list of every host across every project.

    .. deprecated::
        Use ``GET /api/projects/{project_id}/hosts`` instead. Kept during
        the dynamic-edition transition; will be removed in Phase 09.
    """
    rows = await host_service.list_all_projects_hosts(session)
    # Also include legacy global ``Host`` rows so the static pc1/pc2/pc3
    # still appear in the dashboard during dev.
    legacy_rows = await host_service.list_hosts(session)
    out = [_legacy_host_out(h) for h in legacy_rows]
    out.extend(_legacy_host_out(h) for h in rows)
    return HostListResponse(
        hosts=out,
        total=len(out),
        online=sum(1 for h in out if h.status == "online"),
        offline=sum(1 for h in out if h.status == "offline"),
    )


# ─── per-project endpoints (Phase 05) ──────────────────────────────────────

@project_router.get(
    "/{project_id}/hosts",
    response_model=ProjectHostListResponse,
)
async def list_project_hosts(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """List every host in the given project, with live online/offline counts."""
    rows = await host_service.list_project_hosts(session, project_id)
    out = [_host_out(h) for h in rows]
    return ProjectHostListResponse(
        hosts=out,
        total=len(out),
        online=sum(1 for h in out if h.status == "online"),
        offline=sum(1 for h in out if h.status == "offline"),
    )


@project_router.get(
    "/{project_id}/hosts/{host_id}",
    response_model=ProjectHostOut,
)
async def get_project_host(
    project_id: str,
    host_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Fetch a single host row by (project_id, host_id). 404 if missing."""
    row = await host_service.get_project_host(session, project_id, host_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"host {host_id!r} not found in project {project_id!r}",
        )
    return _host_out(row)


@project_router.get(
    "/{project_id}/hosts/{host_id}/metrics",
    responses={200: {"content": {"text/plain": {}}}},
)
async def get_project_host_metrics(
    project_id: str,
    host_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Proxy the host agent's ``/metrics`` endpoint.

    The browser asks the backend, the backend asks the host container (on
    its LAN IP, port 9100) and forwards the response verbatim. This way
    CORS / firewall topology between the user's browser and the per-project
    LAN is irrelevant.

    Returns:
        * 200 + text/plain (Prometheus format) on success
        * 404 if the project / host pair doesn't exist
        * 400 if the host has no IP assigned yet
        * 502 if the agent can't be reached (e.g. host offline)
    """
    row = await host_service.get_project_host(session, project_id, host_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"host {host_id!r} not found in project {project_id!r}",
        )
    if not row.ip_address:
        raise HTTPException(
            status_code=400,
            detail="host has no IP assigned yet",
        )
    metrics_url = f"http://{row.ip_address}:9100/metrics"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(metrics_url)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"could not reach host agent at {metrics_url}: {exc}",
        )
    if resp.status_code != 200:
        # Don't raise — forward the response so the frontend can show the raw
        # Prometheus error (helpful for debugging).
        return JSONResponse(
            status_code=resp.status_code,
            content={"error": "host metrics fetch failed", "agent_status": resp.status_code},
        )
    return Response(content=resp.text, media_type="text/plain; version=0.0.4")
