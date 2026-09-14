from fastapi import APIRouter

from . import admin, communications, health, hosts, projects, topology

api_router = APIRouter()
api_router.include_router(admin.router, prefix="")
api_router.include_router(health.router, prefix="")
# `hosts` exposes BOTH legacy /hosts and per-project /projects/{id}/hosts.
api_router.include_router(hosts.legacy_router, prefix="")
api_router.include_router(hosts.project_router, prefix="")
api_router.include_router(projects.router, prefix="")
api_router.include_router(topology.router, prefix="")
# `communications` exposes BOTH legacy /communications and per-project
# /projects/{id}/communications.
api_router.include_router(communications.legacy_router, prefix="")
api_router.include_router(communications.project_router, prefix="")

__all__ = ["api_router"]
