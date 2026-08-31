"""Heartbeat endpoint — host agents POST here every few seconds."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session
from app.schemas.heartbeat import HeartbeatIn, HeartbeatOut
from app.services import host_service

router = APIRouter(tags=["health"])


@router.post("/health", response_model=HeartbeatOut)
async def receive_heartbeat(
    hb: HeartbeatIn,
    session: AsyncSession = Depends(get_session),
):
    host = await host_service.upsert_heartbeat(session, hb)
    return HeartbeatOut(
        status="ok",
        host_id=host.host_id,
        message=f"{host.hostname} marked {host.status.value}",
    )