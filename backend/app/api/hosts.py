"""Hosts listing endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session
from app.schemas.host import HostListResponse, HostOut
from app.services import host_service

router = APIRouter(prefix="/hosts", tags=["hosts"])


@router.get("", response_model=HostListResponse)
async def get_hosts(session: AsyncSession = Depends(get_session)):
    hosts = await host_service.list_hosts(session)
    out = []
    for h in hosts:
        status_value = h.status.value if hasattr(h.status, "value") else h.status
        out.append(
            HostOut(
                id=h.id,
                host_id=h.host_id,
                hostname=h.hostname,
                ip_address=h.ip_address,
                status=status_value,
                last_seen=h.last_seen,
                created_at=h.created_at,
            )
        )
    return HostListResponse(
        hosts=out,
        total=len(out),
        online=sum(1 for h in out if h.status == "online"),
        offline=sum(1 for h in out if h.status == "offline"),
    )