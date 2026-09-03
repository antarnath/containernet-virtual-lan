"""Communication orchestrator.

Coordinates a host-to-host message exchange:
    1. Validate src/dst hosts exist.
    2. Create a Communication row in 'pending' state.
    3. POST to the source host agent's /send endpoint, asking it to
       actually deliver the payload to the destination's :8080/receive.
    4. Time the round-trip; mark delivered/failed; persist latency.
"""

from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Communication, CommStatus, Host
from app.schemas.communication import CommunicationCreate
from app.ws import publish

AGENT_SEND_TIMEOUT = 5.0


def _status_str(s) -> str:
    return s.value if hasattr(s, "value") else s


async def list_communications(session: AsyncSession, limit: int = 100) -> list[Communication]:
    """Return most-recent communications first."""
    result = await session.execute(
        select(Communication).order_by(Communication.timestamp.desc()).limit(limit)
    )
    return list(result.scalars())


def _serialize(comm: Communication) -> dict:
    """Communication row -> JSON-friendly dict."""
    return {
        "id": comm.id,
        "source_host_id": comm.source_host_id,
        "dest_host_id": comm.dest_host_id,
        "protocol": comm.protocol,
        "payload": comm.payload,
        "data_size": comm.data_size,
        "latency_ms": comm.latency_ms,
        "status": _status_str(comm.status),
        "timestamp": comm.timestamp.isoformat() if comm.timestamp else None,
    }


async def trigger_communication(
    session: AsyncSession, data: CommunicationCreate
) -> Communication:
    """Trigger a host-to-host message exchange and return the persisted record."""

    # 1. Resolve source and destination hosts
    src_res = await session.execute(select(Host).where(Host.host_id == data.source_host_id))
    source = src_res.scalar_one_or_none()
    if source is None:
        raise ValueError(f"unknown source host: {data.source_host_id}")

    dst_res = await session.execute(select(Host).where(Host.host_id == data.destination_host_id))
    destination = dst_res.scalar_one_or_none()
    if destination is None:
        raise ValueError(f"unknown destination host: {data.destination_host_id}")

    # 2. Create pending record
    comm = Communication(
        source_host_id=data.source_host_id,
        dest_host_id=data.destination_host_id,
        protocol=data.protocol,
        payload=data.payload,
        data_size=len(data.payload.encode("utf-8")),
        status=CommStatus.PENDING,
        timestamp=datetime.now(timezone.utc),
    )
    session.add(comm)
    await session.commit()
    await session.refresh(comm)

    # Emit "start" event so the frontend can mark the edge as in-flight.
    publish(
        "communication_start",
        {
            "id": comm.id,
            "source_host_id": comm.source_host_id,
            "dest_host_id": comm.dest_host_id,
            "protocol": comm.protocol,
            "payload": comm.payload,
        },
    )

    # 3. Dispatch to source host agent's /send endpoint
    dispatch_url = f"http://{source.ip_address}:8080/send"
    dispatch_body = {
        "comm_id": comm.id,
        "target_host_id": destination.host_id,
        "target_ip": destination.ip_address,
        "payload": data.payload,
        "protocol": data.protocol,
    }

    start = datetime.now(timezone.utc)
    status = CommStatus.FAILED
    error_msg: str | None = None
    try:
        async with httpx.AsyncClient(timeout=AGENT_SEND_TIMEOUT) as client:
            resp = await client.post(dispatch_url, json=dispatch_body)
            try:
                body = resp.json()
            except Exception:
                body = {}
            agent_status = body.get("status") if isinstance(body, dict) else None
            if 200 <= resp.status_code < 300 and agent_status == "sent":
                status = CommStatus.DELIVERED
            else:
                error_msg = (
                    body.get("error")
                    if isinstance(body, dict) and body.get("error")
                    else f"agent returned HTTP {resp.status_code}"
                )
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"

    elapsed_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000.0

    # 4. Update record
    comm.status = status
    comm.latency_ms = round(elapsed_ms, 2)
    await session.commit()
    await session.refresh(comm)

    if error_msg:
        print(
            f"[orchestrator] {data.source_host_id} -> {data.destination_host_id} "
            f"FAILED after {comm.latency_ms}ms: {error_msg}"
        )
    else:
        print(
            f"[orchestrator] {data.source_host_id} -> {data.destination_host_id} "
            f"delivered in {comm.latency_ms}ms"
        )

    # Emit "complete" event with the final record.
    publish("communication_complete", _serialize(comm))

    return comm