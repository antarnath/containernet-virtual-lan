from fastapi import APIRouter

from . import projects

api_router = APIRouter()
api_router.include_router(projects.router, prefix="")

__all__ = ["api_router"]
