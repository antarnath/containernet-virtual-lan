"""event_service — the single point for emitting project events.

M4 phase 07. Every significant backend action calls one of these
``emit_*`` helpers, which:

  1. Inserts a row in ``project_events`` (the audit log).
  2. Broadcasts the same payload over the project's WebSocket so
     the LogsView updates live.

The shape of the WS payload is exactly ``to_dict()`` of the row,
prefixed with ``type: "event"`` for routing. The LogsView's WS
handler reads ``type === "event"`` and treats the rest as the
row dict.

Why not just have each caller do ``INSERT ... RETURNING *`` then
broadcast? Two reasons:

  * Centralised summary formatting. The same "lifecycle: starting"
    string is used in the DB and the WS payload, so the timeline
    is consistent.
  * The realtime broadcast is best-effort: a disconnected WS client
    shouldn't fail the caller. Wrapping the call here keeps that
    invariant in one spot.

Notes on errors:
  * DB failures are logged but do NOT propagate. The caller's
    business logic (start/stop/start attack/etc.) is more important
    than the log row.
  * Broadcast failures are swallowed by ``broadcast_project_event``
    itself.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ProjectEvent,
    ProjectEventKind,
)
from app.services.realtime import broadcast_project_event

log = logging.getLogger(__name__)


async def emit_event(
    session: AsyncSession,
    project_id: str,
    kind: ProjectEventKind,
    summary: str,
    *,
    detail: dict[str, Any] | None = None,
    node_id: str | None = None,
    link_id: str | None = None,
    broadcast: bool = True,
) -> ProjectEvent | None:
    """Insert a project_event row and broadcast it.

    Returns the inserted row, or None on DB error. The caller never
    has to handle the failure — this is an audit log, not a critical
    write path.
    """
    row = ProjectEvent(
        project_id=project_id,
        kind=kind.value,
        summary=summary,
        detail=detail,
        node_id=node_id,
        link_id=link_id,
    )
    try:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    except Exception:
        log.exception("[events] insert failed kind=%s summary=%r", kind.value, summary)
        try:
            await session.rollback()
        except Exception:
            pass
        return None

    if broadcast:
        try:
            await broadcast_project_event(
                project_id,
                {"type": "event", **row.to_dict()},
            )
        except Exception:
            log.exception("[events] broadcast failed kind=%s", kind.value)
    return row


# ─── high-level helpers ─────────────────────────────────────────────
# These are the names the rest of the codebase calls. They set the
# ``summary`` string in one canonical place so the timeline reads
# consistently.

async def emit_lifecycle(
    session: AsyncSession,
    project_id: str,
    *,
    state: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """``lifecycle: <state>`` — start/stop/restart/error transitions."""
    await emit_event(
        session,
        project_id,
        ProjectEventKind.LIFECYCLE,
        f"Project {state}",
        detail=detail,
    )


async def emit_node_started(
    session: AsyncSession,
    project_id: str,
    node_id: str,
    node_name: str,
    node_kind: str,
) -> None:
    await emit_event(
        session,
        project_id,
        ProjectEventKind.NODE_STARTED,
        f"{node_kind} {node_name!r} started",
        node_id=node_id,
        detail={"name": node_name, "kind": node_kind},
    )


async def emit_node_stopped(
    session: AsyncSession,
    project_id: str,
    node_id: str,
    node_name: str,
    node_kind: str,
) -> None:
    await emit_event(
        session,
        project_id,
        ProjectEventKind.NODE_STOPPED,
        f"{node_kind} {node_name!r} stopped",
        node_id=node_id,
        detail={"name": node_name, "kind": node_kind},
    )


async def emit_link_created(
    session: AsyncSession,
    project_id: str,
    link_id: str,
    iface_a_id: str,
    iface_b_id: str,
    subnet_cidr: str | None = None,
) -> None:
    summary = "Wire created"
    detail = {"iface_a_id": iface_a_id, "iface_b_id": iface_b_id}
    if subnet_cidr:
        detail["subnet_cidr"] = subnet_cidr
    await emit_event(
        session,
        project_id,
        ProjectEventKind.LINK_CREATED,
        summary,
        link_id=link_id,
        detail=detail,
    )


async def emit_link_deleted(
    session: AsyncSession,
    project_id: str,
    link_id: str,
) -> None:
    await emit_event(
        session,
        project_id,
        ProjectEventKind.LINK_CREATED,  # reuse LINK_CREATED kind — the
        # frontend differentiates by summary, but the per-direction
        # kinds (link_created vs link_deleted) are intentionally merged
        # into a single "wire" channel for the timeline.
        "Wire deleted",
        link_id=link_id,
    )


async def emit_bridge_created(
    session: AsyncSession,
    project_id: str,
    link_id: str,
    bridge_name: str,
    subnet_cidr: str | None = None,
) -> None:
    detail: dict[str, Any] = {"bridge_name": bridge_name}
    if subnet_cidr:
        detail["subnet_cidr"] = subnet_cidr
    await emit_event(
        session,
        project_id,
        ProjectEventKind.BRIDGE_CREATED,
        f"Bridge {bridge_name} up",
        link_id=link_id,
        detail=detail,
    )


async def emit_message_sent(
    session: AsyncSession,
    project_id: str,
    *,
    src_node_id: str,
    src_node_name: str,
    dst_node_id: str,
    dst_node_name: str,
    protocol: str,
    detail_extra: dict[str, Any] | None = None,
) -> None:
    summary = f"{protocol} {src_node_name} → {dst_node_name}"
    detail = {
        "src_node_id": src_node_id,
        "dst_node_id": dst_node_id,
        "src_node_name": src_node_name,
        "dst_node_name": dst_node_name,
        "protocol": protocol,
    }
    if detail_extra:
        detail.update(detail_extra)
    await emit_event(
        session,
        project_id,
        ProjectEventKind.MESSAGE_SENT,
        summary,
        node_id=src_node_id,
        detail=detail,
    )


async def emit_anomaly(
    session: AsyncSession,
    project_id: str,
    *,
    anomaly_id: str,
    node_id: str | None,
    kind: str,
    severity: str,
    summary: str,
    detail: dict[str, Any] | None = None,
) -> None:
    """An anomaly from the detector — links to the anomaly_event row."""
    detail = dict(detail or {})
    detail["anomaly_id"] = anomaly_id
    detail["severity"] = severity
    detail["anomaly_kind"] = kind
    await emit_event(
        session,
        project_id,
        ProjectEventKind.ANOMALY,
        summary,
        node_id=node_id,
        detail=detail,
    )


async def emit_attack_signal(
    session: AsyncSession,
    project_id: str,
    *,
    signal_id: str,
    attacker_node_id: str,
    victim_node_id: str | None,
    signal_kind: str,
    value: float,
    threshold: float,
    window_sec: int,
) -> None:
    detail = {
        "signal_id": signal_id,
        "signal_kind": signal_kind,
        "value": value,
        "threshold": threshold,
        "window_sec": window_sec,
        "victim_node_id": victim_node_id,
    }
    summary = f"{signal_kind} ({value:.2f} > {threshold:.2f})"
    await emit_event(
        session,
        project_id,
        ProjectEventKind.ATTACK_SIGNAL,
        summary,
        node_id=attacker_node_id,
        detail=detail,
    )


async def emit_error(
    session: AsyncSession,
    project_id: str,
    *,
    summary: str,
    detail: dict[str, Any] | None = None,
    node_id: str | None = None,
) -> None:
    await emit_event(
        session,
        project_id,
        ProjectEventKind.ERROR,
        summary,
        detail=detail,
        node_id=node_id,
    )