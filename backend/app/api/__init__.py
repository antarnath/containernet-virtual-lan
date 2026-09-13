from fastapi import APIRouter

from . import admin, communications, health, hosts, projects, topology

api_router = APIRouter()
api_router.include_router(admin.router, prefix="")
api_router.include_router(health.router, prefix="")
api_router.include_router(hosts.router, prefix="")
api_router.include_router(projects.router, prefix="")
api_router.include_router(topology.router, prefix="")
api_router.include_router(communications.router, prefix="")

__all__ = ["api_router"]
