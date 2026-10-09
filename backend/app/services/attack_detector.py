"""attack_detector — polls every attacker's /state once per second.

M4 phase 06. One asyncio task per project, started by
``project_lifecycle.start_project`` and torn down by
``stop_project``. Mirrors ``anomaly_detector.py`` line for line so
the two share the same lifecycle plumbing.

For each running project:
  1. Load the project's attacker-kind ProjectNode rows whose containers
     are up.
  2. For each, GET ``http://<backend-lan-ip>:9092/state`` (3s timeout).
  3. If the response has ``running=True`` and the attacker mode maps
     to a signal kind, compare ``packets_per_sec`` to the threshold.
  4. On exceed, write an ``AttackSignal`` row + broadcast a
     ``attack_signal`` WS event.

This is the v1 design (the agent self-reports). v2 (M5+) can swap to
inspecting the per-link capture NDJSON to compute the rate off the
wire — but the agent-reported number is what the user actually
generated, so it's a tighter signal anyway.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models import (
    AttackSignal,
    AttackSignalKind,
    NodeKind,
    Project,
    ProjectNode,
    ProjectStatus,
    SIGNAL_THRESHOLDS,
)
from app.services import attack_proxy
from app.services.realtime import broadcast_project_event

log = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 1.0
WINDOW_SEC = 5
# Min seconds between two signals of the same kind from the same
# attacker. Without this the table fills with one signal/sec per
# running attack, which is noise.
SIGNAL_COOLDOWN_SEC = 10

# Map attack mode → signal kind emitted while it's running. Modes
# without a 1:1 signal (e.g. unknown_host) emit no per-poll signal;
# they surface via the anomaly detector's new_mac detection.
_MODE_TO_SIGNAL: dict[str, str] = {
    "arp_spoof": AttackSignalKind.ARP_RATE.value,
    "tcp_flood": AttackSignalKind.SYN_RATE.value,
    "http_flood": AttackSignalKind.HTTP_RATE.value,
    "duplicate_ip": AttackSignalKind.DUPLICATE_IP.value,
    "unknown_host": AttackSignalKind.NEW_MAC.value,
}

_tasks: dict[str, asyncio.Task] = {}
# Cooldown tracker: (attacker_id, signal_kind) -> last_fired_ts.
# Lets us throttle so the table doesn't fill with one row per second.
_last_signal_at: dict[tuple[str, str], float] = {}


# ─── public API ────────────────────────────────────────────────


def start_polling(project_id: str) -> None:
    stop_polling(project_id)
    task = asyncio.create_task(_poll_loop(project_id), name=f"attack-{project_id[:8]}")
    _tasks[project_id] = task
    log.info("[attack] started polling for project %s", project_id)


def stop_polling(project_id: str) -> None:
    task = _tasks.pop(project_id, None)
    if task is not None and not task.done():
        task.cancel()
    log.info("[attack] stopped polling for project %s", project_id)


def stop_all() -> None:
    for pid in list(_tasks.keys()):
        stop_polling(pid)


# ─── the loop ──────────────────────────────────────────────────


async def _poll_loop(project_id: str) -> None:
    """Per-project poll loop. Runs until cancelled."""
    # Settle: don't fire signals for the first 2 polls — the
    # attacker might still be starting up.
    await asyncio.sleep(POLL_INTERVAL_SEC * 2)
    while True:
        try:
            await _poll_once(project_id)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log.exception("[attack] poll failed for %s: %s", project_id, exc)
        await asyncio.sleep(POLL_INTERVAL_SEC)


async def _poll_once(project_id: str) -> None:
    # 1. Load attackers + their target mapping while the session is open.
    # The eager load pulls nodes + interfaces + links so the in-memory
    # walk in _resolve_targets doesn't trigger lazy loads after the
    # session closes (the classic MissingGreenlet trap).
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Project)
            .where(Project.id == project_id)
            .options(
                selectinload(Project.nodes).selectinload(ProjectNode.interfaces),
                selectinload(Project.links),
            )
        )
        project = (await session.execute(stmt)).scalars().first()
        if project is None:
            return
        proj_status = (
            project.status.value
            if hasattr(project.status, "value")
            else project.status
        )
        if proj_status != ProjectStatus.RUNNING.value:
            return
        attackers: list[ProjectNode] = []
        for n in project.nodes:
            kind_val = n.kind.value if hasattr(n.kind, "value") else n.kind
            if kind_val == NodeKind.ATTACKER.value and n.container_id:
                attackers.append(n)
        # Resolve "victim" = the first non-router, non-self node on
        # the attacker's first link. Must happen INSIDE the session
        # because we touch link.iface_a_id / link.iface_b_id.
        targets = _resolve_targets(project, attackers)

    # 2. For each attacker, ask :9092/state and maybe fire a signal.
    for attacker in attackers:
        state = await attack_proxy.attacker_state(attacker, session=None)
        if not state.get("running"):
            continue
        mode = state.get("mode")
        if not mode:
            continue
        signal_kind = _MODE_TO_SIGNAL.get(mode)
        if not signal_kind:
            continue
        threshold = SIGNAL_THRESHOLDS.get(signal_kind, 0.0)
        # For rate-based signals, compare packets_per_sec. For one-
        # shot signals (NEW_MAC, DUPLICATE_IP), any running > threshold.
        value = float(state.get("packets_per_sec", 0))
        # Allow a small slack (10% of threshold, min 0.1) so a rate
        # hovering at the boundary (e.g. arp_spoof exactly at 1/sec
        # showing 0.9999) doesn't slip through.
        slack = max(threshold * 0.1, 0.1) if threshold > 0 else 0.0
        if value < threshold - slack and threshold > 0:
            continue
        # Cooldown: don't fire the same signal-kind for the same
        # attacker more than once per SIGNAL_COOLDOWN_SEC.
        import time as _t
        now = _t.monotonic()
        key = (attacker.id, signal_kind)
        last = _last_signal_at.get(key)
        if last is not None and (now - last) < SIGNAL_COOLDOWN_SEC:
            continue
        _last_signal_at[key] = now
        # 3. Write the signal row + WS.
        victim_id = targets.get(attacker.id)
        await _fire_signal(
            project_id=project_id,
            attacker_id=attacker.id,
            victim_id=victim_id,
            signal_kind=signal_kind,
            value=value,
            threshold=threshold,
        )


def _resolve_targets(
    project: Project, attackers: list[ProjectNode]
) -> dict[str, str | None]:
    """For each attacker, return a {attacker_id: victim_node_id} map.

    The "victim" is the first non-router, non-self node on the
    attacker's first link. If no such link exists, victim_id is
    None (the signal row will have a NULL victim_id, which is fine
    for global signals like new_mac).

    Loaded eagerly inside the caller session — we don't touch the DB
    here, just walk in-memory relationships.
    """
    out: dict[str, str | None] = {}
    # Build iface_id → node_id map for fast lookups
    iface_to_node: dict[str, str] = {}
    for n in project.nodes:
        for i in n.interfaces:
            iface_to_node[i.id] = n.id

    attacker_ids = {a.id for a in attackers}
    for link in project.links:
        a_id = iface_to_node.get(link.iface_a_id)
        b_id = iface_to_node.get(link.iface_b_id)
        # Is one side an attacker?
        attacker_id = None
        other_id = None
        if a_id in attacker_ids:
            attacker_id = a_id
            other_id = b_id
        elif b_id in attacker_ids:
            attacker_id = b_id
            other_id = a_id
        if attacker_id is None or attacker_id in out:
            continue
        if other_id is None:
            out[attacker_id] = None
            continue
        # Filter: skip routers. (Attacker → router → victim across
        # multiple hops is a v2 problem; v1 only handles direct links.)
        other_node = next((n for n in project.nodes if n.id == other_id), None)
        if other_node is None:
            out[attacker_id] = None
            continue
        kind_val = other_node.kind.value if hasattr(other_node.kind, "value") else other_node.kind
        if kind_val == NodeKind.ROUTER.value:
            out[attacker_id] = None
            continue
        out[attacker_id] = other_id
    # Fill in nulls for attackers with no link
    for a in attackers:
        out.setdefault(a.id, None)
    return out


async def _fire_signal(
    *,
    project_id: str,
    attacker_id: str,
    victim_id: str | None,
    signal_kind: str,
    value: float,
    threshold: float,
) -> None:
    """Persist the signal + broadcast the WS event."""
    async with AsyncSessionLocal() as session:
        sig = AttackSignal(
            project_id=project_id,
            attacker_node_id=attacker_id,
            victim_node_id=victim_id,
            signal_kind=signal_kind,
            value=value,
            threshold=threshold,
            window_sec=WINDOW_SEC,
        )
        session.add(sig)
        await session.commit()
        sig_id = sig.id
        created_at = sig.created_at.isoformat() if sig.created_at else None
    await broadcast_project_event(project_id, {
        "type": "attack_signal",
        "id": sig_id,
        "attacker_node_id": attacker_id,
        "victim_node_id": victim_id,
        "signal_kind": signal_kind,
        "value": value,
        "threshold": threshold,
        "window_sec": WINDOW_SEC,
        "created_at": created_at,
    })

    # M4 phase 07 — also write to the unified project_events log so the
    # LogsView shows this signal in the same timeline as lifecycle /
    # link / anomaly events.
    try:
        from app.services import event_service
        async with AsyncSessionLocal() as es_sess:
            await event_service.emit_attack_signal(
                es_sess,
                project_id,
                signal_id=sig_id,
                attacker_node_id=attacker_id,
                victim_node_id=victim_id,
                signal_kind=signal_kind,
                value=value,
                threshold=threshold,
                window_sec=WINDOW_SEC,
            )
    except Exception:
        log.exception("[attack] failed to emit project_event for %s", sig_id)