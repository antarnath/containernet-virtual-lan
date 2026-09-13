"""Admin endpoints — development only.

These endpoints exist to let you exercise the Docker orchestration layer
with curl while you build Phase 01. They accept arbitrary image names and
commands, so in production they would be a remote-code-execution goldmine.

They are protected by an ADMIN_TOKEN environment variable:

  - ADMIN_TOKEN unset (production default) → every request gets 403
  - ADMIN_TOKEN set + correct X-Admin-Token header → request proceeds
  - ADMIN_TOKEN set + missing/wrong header → 403

After Phase 09 these endpoints are deleted entirely. The user-facing
container-creation path is `POST /api/projects/{id}/start`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.core import docker_client
from app.services import container_service


router = APIRouter(prefix="/admin", tags=["admin"])


# ─── token gate ──────────────────────────────────────────────────────────────

async def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """FastAPI dependency: refuse the request unless the X-Admin-Token header
    matches the ADMIN_TOKEN env var (and that env var is non-empty).

    Declared as `dependencies=[Depends(require_admin)]` on every endpoint below.
    """
    expected = docker_client.settings.ADMIN_TOKEN if hasattr(docker_client, "settings") else ""
    # We import settings here to avoid a circular import at module load time.
    from app.core.config import settings as _settings
    expected = _settings.ADMIN_TOKEN

    if not expected:
        # No token configured at all → the admin surface is OFF. This is
        # the safe default for any deployment that didn't explicitly opt in.
        raise HTTPException(status_code=403, detail="admin endpoints disabled")
    if x_admin_token != expected:
        raise HTTPException(status_code=403, detail="invalid admin token")


# ─── schemas ─────────────────────────────────────────────────────────────────

class CreateContainerIn(BaseModel):
    """Body for POST /api/admin/containers."""
    image: str = Field(..., description="Docker image to run, e.g. 'alpine:3.19'")
    name: str = Field(..., description="Container name; must be unique on the host")
    command: list[str] | None = Field(default=None, description="Override the container's CMD")
    env: dict[str, str] | None = Field(default=None, description="Environment variables")


# ─── endpoints ───────────────────────────────────────────────────────────────

@router.get("/docker/ping", dependencies=[Depends(require_admin)])
async def docker_ping() -> dict[str, bool]:
    """Return {reachable: true} if the Docker daemon is reachable."""
    return {"reachable": docker_client.ping()}


@router.post("/containers", dependencies=[Depends(require_admin)])
async def create_test_container(body: CreateContainerIn) -> dict[str, str]:
    """Create and start a container from any image. Dev/testing only."""
    container_id = container_service.create_container(
        image=body.image,
        name=body.name,
        env=body.env or {},
        command=body.command,
    )
    return {"container_id": container_id, "name": body.name}


@router.get("/containers", dependencies=[Depends(require_admin)])
async def list_our_containers(all_states: bool = False) -> list[dict[str, Any]]:
    """List all containers this backend has created (label containernet.host=true).

    Pass ?all_states=true to include stopped containers too.
    """
    return container_service.list_running_containers(all_states=all_states)


@router.post("/containers/{container_id}/stop", dependencies=[Depends(require_admin)])
async def stop_test_container(container_id: str) -> dict[str, str]:
    """Gracefully stop a container created by this backend."""
    container_service.stop_container(container_id)
    return {"status": "stopped", "container_id": container_id}


@router.delete("/containers/{container_id}", dependencies=[Depends(require_admin)])
async def remove_test_container(container_id: str, force: bool = False) -> dict[str, str]:
    """Stop (if running) and remove a container. Pass ?force=true to remove even if running."""
    container_service.remove_container(container_id, force=force)
    return {"status": "removed", "container_id": container_id}
