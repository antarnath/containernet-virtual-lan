"""Anomaly detector — diffs consecutive router states and writes events.

M4 phase 03. The detector runs in a background asyncio task (one
per project, started by the lifespan). Every 2s it:

  1. Iterates over the project's router nodes whose containers are
     running.
  2. Calls ``router_proxy.get_router_state`` to fetch the current
     ARP table (cached 1.5s).
  3. Compares against the previous ARP snapshot for that router.
  4. For every IP whose MAC changed (i.e. the resolver returned a
     different MAC than before), writes an ``AnomalyEvent`` row
     and broadcasts an ``anomaly`` event over the project's
     WebSocket.

The detector is the "MITM is happening" sensor: an attacker on the
same wire replying to ARP for ``10.0.0.1`` (the router) with their
own MAC, the host's ARP table will flip, and the next poll diff
will see ``10.0.0.1 -> <attacker-mac>`` and raise an alert.

A user "Dismiss" on the banner resolves the anomaly (sets
``resolved_at``); the next diff for the same (ip, old_mac, new_mac)
triple won't re-fire because the snapshot has been advanced to
the new state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import (
    AnomalyEvent,
    AnomalyKind,
    AnomalySeverity,
    NodeKind,
    Project,
    ProjectNode,
    ProjectStatus,
)
from app.services import router_proxy
from app.services.realtime import broadcast_project_event

log = logging.getLogger(__name__)

# Poll interval. The router panel also polls every 2s; matching the
# interval here keeps the UI's "Last updated" timestamp honest.
POLL_INTERVAL_SEC = 2.0

# In-process snapshot store: {node_id: {ip: (mac, state)}}.
# The snapshot is per-process (not per-database) so a backend
# restart clears the baseline; the next poll establishes a fresh
# one. This is the right behaviour — the detector shouldn't fire
# anomalies for state changes that happened while we were down.
_snapshots: dict[str, dict[str, tuple[str, str]]] = {}

# Tasks per project: {project_id: asyncio.Task}. The lifespan
# starts / stops these as projects move between draft / running.
_tasks: dict[str, asyncio.Task] = {}


# ─── public API ───────────────────────────────────────────────────────

def start_polling(project_id: str) -> None:
    """Start (or restart) the polling task for a project."""
    stop_polling(project_id)
    task = asyncio.create_task(_poll_loop(project_id), name=f"anomaly-{project_id[:8]}")
    _tasks[project_id] = task
    log.info("[anomaly] started polling for project %s", project_id)


def stop_polling(project_id: str) -> None:
    """Stop the polling task for a project (no-op if not running)."""
    task = _tasks.pop(project_id, None)
    if task is not None and not task.done():
        task.cancel()
        _snapshots.pop(project_id, None)
        log.info("[anomaly] stopped polling for project %s", project_id)


def stop_all() -> None:
    for pid in list(_tasks.keys()):
        stop_polling(pid)


# ─── the loop ─────────────────────────────────────────────────────────

async def _poll_loop(project_id: str) -> None:
    """Per-project poll loop. Runs until cancelled."""
    # Give the lifecycle a beat to settle before the first poll —
    # we don't want to flag "no MAC yet" as an anomaly.
    await asyncio.sleep(POLL_INTERVAL_SEC)
    while True:
        try:
            await _poll_once(project_id)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log.exception("[anomaly] poll failed for %s: %s", project_id, exc)
        await asyncio.sleep(POLL_INTERVAL_SEC)


async def _poll_once(project_id: str) -> None:
    async with AsyncSessionLocal() as session:
        # Eagerly load the nodes + their kind (an SAEnum) so we can
        # filter on `n.kind` without triggering a lazy load after the
        # session is closed.
        from sqlalchemy.orm import selectinload
        # NB: rename the param to avoid any chance of clashing with
        # the column attribute `Project.id`. The `where(...)` line
        # below was occasionally being mis-resolved as an ORM
        # attribute access, triggering a lazy load in a sync context
        # and surfacing as MissingGreenlet.
        pid = project_id
        stmt = (
            select(Project)
            .where(Project.id == pid)
            .options(selectinload(Project.nodes))
        )
        project = (await session.execute(stmt)).scalars().first()
        if project is None:
            return
        # Touch `.status` while the session is open; it may not have
        # been hydrated if the row came back with deferred columns.
        proj_status = (
            project.status.value
            if hasattr(project.status, "value")
            else project.status
        )
        if proj_status != ProjectStatus.RUNNING.value:
            return
        # Snapshot the router info while the session is open; we
        # only need (id, container_id) for the proxy call. Touch
        # `.kind` (SAEnum) here too so we don't lazy-load later.
        routers: list[tuple[str, str]] = []
        for n in project.nodes:
            kind_val = n.kind.value if hasattr(n.kind, "value") else n.kind
            if kind_val == NodeKind.ROUTER.value and n.container_id:
                routers.append((n.id, n.container_id))
    for node_id, container_id in routers:
        await _check_router(project_id, node_id, container_id)


async def _check_router(project_id: str, node_id: str, container_id: str) -> None:
    state = await router_proxy.get_router_state(node_id, container_id)
    if state.error:
        return
    current = {n.ip: (n.mac, n.state) for n in state.neigh if n.ip and n.mac}
    previous = _snapshots.get(node_id)

    if previous is None:
        # First poll — establish baseline, don't fire any alerts.
        _snapshots[node_id] = current
        return

    diffs: list[dict[str, Any]] = []
    for ip, (new_mac, new_state) in current.items():
        old = previous.get(ip)
        if old is None:
            continue
        old_mac, _ = old
        if old_mac and new_mac and old_mac != new_mac:
            diffs.append({
                "ip": ip,
                "old_mac": old_mac,
                "new_mac": new_mac,
                "state": new_state,
            })

    # Update the snapshot regardless of whether we fired.
    _snapshots[node_id] = current

    if not diffs:
        return

    # Write events + broadcast.
    async with AsyncSessionLocal() as session:
        for d in diffs:
            event = AnomalyEvent(
                project_id=project_id,
                node_id=node_id,
                kind=AnomalyKind.ARP_MAC_CHANGE.value,
                severity=AnomalySeverity.DANGER.value,
                summary=(
                    f"ARP for {d['ip']} changed: {d['old_mac']} -> {d['new_mac']} "
                    f"(state={d['state']})"
                ),
                detail=d,
            )
            session.add(event)
        await session.commit()
        # Re-fetch to get the persisted ids for the broadcast.
        events = (await session.execute(
            select(AnomalyEvent)
            .where(
                AnomalyEvent.project_id == project_id,
                AnomalyEvent.node_id == node_id,
                AnomalyEvent.resolved_at.is_(None),
            )
            .order_by(AnomalyEvent.created_at.desc())
            .limit(len(diffs))
        )).scalars().all()

    for ev in events:
        await broadcast_project_event(project_id, {
            "type": "anomaly",
            "id": ev.id,
            "node_id": ev.node_id,
            "kind": ev.kind,
            "severity": ev.severity,
            "summary": ev.summary,
            "detail": ev.detail,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        })

        # M4 phase 07 — also write to the unified project_events log so
        # the LogsView shows this anomaly in the same timeline as
        # lifecycle / link / bridge events.
        try:
            from app.services import event_service
            async with AsyncSessionLocal() as es_sess:
                await event_service.emit_anomaly(
                    es_sess,
                    project_id,
                    anomaly_id=ev.id,
                    node_id=ev.node_id,
                    kind=ev.kind,
                    severity=ev.severity,
                    summary=ev.summary,
                    detail=ev.detail,
                )
        except Exception:
            log.exception("[anomaly] failed to emit project_event for %s", ev.id)


# ─── helpers ──────────────────────────────────────────────────────────
