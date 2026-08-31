from fastapi import APIRouter

from . import health, hosts, topology

api_router = APIRouter()
api_router.include_router(health.router, prefix="")
api_router.include_router(hosts.router, prefix="")
api_router.include_router(topology.router, prefix="")

__all__ = ["api_router"]