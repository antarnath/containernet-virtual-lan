"""Topology endpoint — returns nodes + edges for the future frontend."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session
from app.services import host_service

router = APIRouter(prefix="/topology", tags=["topology"])


@router.get("")
async def get_topology(session: AsyncSession = Depends(get_session)):
    return await host_service.get_topology(session)