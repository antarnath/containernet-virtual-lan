from fastapi import APIRouter

from . import projects, realtime

api_router = APIRouter()
api_router.include_router(projects.router, prefix="")
api_router.include_router(realtime.router, prefix="")

__all__ = ["api_router"]
