"""Communications API — list + trigger."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_session
from app.schemas.communication import (
    CommunicationCreate,
    CommunicationListResponse,
    CommunicationOut,
)
from app.services import communication_service

router = APIRouter(prefix="/communications", tags=["communications"])


def _to_out(c) -> CommunicationOut:
    return CommunicationOut(
        id=c.id,
        source_host_id=c.source_host_id,
        dest_host_id=c.dest_host_id,
        protocol=c.protocol,
        payload=c.payload,
        data_size=c.data_size,
        latency_ms=c.latency_ms,
        status=c.status.value if hasattr(c.status, "value") else c.status,
        timestamp=c.timestamp,
    )


@router.get("", response_model=CommunicationListResponse)
async def list_comms(session: AsyncSession = Depends(get_session)):
    comms = await communication_service.list_communications(session)
    out = [_to_out(c) for c in comms]
    return CommunicationListResponse(communications=out, total=len(out))


@router.post("", response_model=CommunicationOut, status_code=201)
async def trigger_comm(
    data: CommunicationCreate,
    session: AsyncSession = Depends(get_session),
):
    try:
        comm = await communication_service.trigger_communication(session, data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _to_out(comm)