// Singleton WebSocket connection that auto-reconnects with backoff.
// Routes incoming events to the relevant Zustand stores.
//
// Phase 07 — per-project subscriptions:
//   * Right after `onopen` (and after every reconnect), if the user is
//     currently viewing a project, we send
//     `{type: "subscribe", project_id: "<id>"}` so the server only routes
//     project-scoped events to us. Legacy/global viewers send nothing.
//   * When the user navigates to a different project, a second effect
//     re-sends the subscribe envelope on the existing socket — the
//     server replaces the previous subscription in place.
//   * `markInFlight` now requires `project_id` so the store can bucket
//     in-flight comms per project (so TopologyCanvas only lights up
//     edges that belong to the project it is rendering).

import { useEffect, useRef } from 'react';
import { useRealtimeStore } from '../store/realtimeStore';
import { useHostStore } from '../store/hostStore';
import { useCommStore } from '../store/commStore';
import { useProjectStore } from '../store/projectStore';
import { useToastStore } from '../store/toastStore';
import type { Communication, HostStatus } from '../types';

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000, 30000];

function wsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/ws`;
}

interface EventEnvelope {
  type: string;
  // Phase 07 — project_id may now also appear at the envelope top level
  // (added by `publish_to_project`). We don't strictly need to read it
  // here because the same value is also stamped into `data` by the helper,
  // but accepting it makes the type honest.
  project_id?: string;
  data: any;
  ts: string;
}

export function useWebSocket() {
  const setStatus = useRealtimeStore((s) => s.setStatus);
  const markInFlight = useRealtimeStore((s) => s.markInFlight);
  const clearInFlight = useRealtimeStore((s) => s.clearInFlight);

  // Live reference to the currently-open socket. We use a ref (not state)
  // so the resubscribe-on-project-change effect can read the freshest
  // socket without re-running the connect effect.
  const socketRef = useRef<WebSocket | null>(null);

  // ─── Effect 1: connect + reconnect ──────────────────────────────────────
  useEffect(() => {
    let attempt = 0;
    let reconnectTimer: number | null = null;
    let cancelled = false;

    const sendSubscribeIfNeeded = (sock: WebSocket) => {
      // Only subscribe if we are currently viewing a project. The legacy
      // global dashboard (no current project) doesn't subscribe — it
      // still receives project-less broadcasts like the old phase.
      const current = useProjectStore.getState().current;
      if (!current) return;
      try {
        sock.send(
          JSON.stringify({ type: 'subscribe', project_id: current.id }),
        );
      } catch {
        // Socket may have closed between the readyState check and send;
        // onclose will handle the reconnect.
      }
    };

    const connect = () => {
      if (cancelled) return;
      setStatus('connecting');
      let s: WebSocket;
      try {
        s = new WebSocket(wsUrl());
      } catch {
        scheduleReconnect();
        return;
      }
      socketRef.current = s;

      s.onopen = () => {
        attempt = 0;
        setStatus('open');
        // (Re-)subscribe on every open — covers first connect AND every
        // reconnect, since the server's per-socket subscription map is
        // cleared on disconnect.
        sendSubscribeIfNeeded(s);
      };

      s.onmessage = (ev) => {
        let env: EventEnvelope;
        try {
          env = JSON.parse(ev.data);
        } catch {
          return;
        }
        handleEvent(env, markInFlight, clearInFlight);
        // Surface important events as toasts (Phase 6 feedback).
        surfaceToasts(env);
      };

      s.onclose = () => {
        if (socketRef.current === s) socketRef.current = null;
        setStatus('closed');
        scheduleReconnect();
      };

      s.onerror = () => {
        try {
          s.close();
        } catch {}
      };
    };

    const scheduleReconnect = () => {
      if (cancelled) return;
      const delay = RECONNECT_DELAYS[Math.min(attempt, RECONNECT_DELAYS.length - 1)];
      attempt++;
      reconnectTimer = window.setTimeout(connect, delay);
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      const s = socketRef.current;
      socketRef.current = null;
      try {
        s?.close();
      } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Effect 2: resubscribe when the active project changes ─────────────
  // If the socket is open and the user just navigated from project A to
  // project B, send a fresh subscribe frame so the server starts routing
  // B's events here and stops routing A's. The active project id can change
  // without this hook re-rendering (the project store is independent), so
  // we read it inside a Zustand `subscribe` and forward a subscribe frame
  // on every change.
  useEffect(() => {
    let lastProjectId: string | null = useProjectStore.getState().current?.id ?? null;
    const off = useProjectStore.subscribe((state) => {
      const nextId = state.current?.id ?? null;
      if (nextId === lastProjectId) return;
      lastProjectId = nextId;
      const sock = socketRef.current;
      if (!sock || sock.readyState !== WebSocket.OPEN) return;
      // For a project-to-project switch we still send `subscribe`; the
      // server replaces the previous subscription in place. For a
      // project->null transition (e.g. back to global dashboard) we
      // simply stop subscribing — the server doesn't have an explicit
      // unsubscribe envelope yet (Phase 08+ may add one).
      if (nextId) {
        try {
          sock.send(JSON.stringify({ type: 'subscribe', project_id: nextId }));
        } catch {
          // ignore — onclose will fire and we'll resubscribe after reconnect
        }
      }
    });
    return off;
  }, []);
}

function handleEvent(
  env: EventEnvelope,
  markInFlight: (c: {
    id: string;
    project_id: string;
    source: string;
    target: string;
    startedAt: number;
  }) => void,
  clearInFlight: (id: string) => void,
) {
  switch (env.type) {
    case 'host_status_change': {
      // Phase 05 — events carry `project_id`. Filter by the currently
      // loaded project so a status change in Project A doesn't perturb
      // Project B's display.
      const d = env.data as {
        host_id: string;
        status: HostStatus;
        project_id?: string | null;
      };
      const current = useProjectStore.getState().current;
      const targetProjectId =
        d.project_id ?? (current ? current.id : undefined);
      if (targetProjectId) {
        if (!current || current.id === targetProjectId) {
          useHostStore
            .getState()
            .applyHostStatusChange(d.host_id, d.status, targetProjectId);
          useProjectStore.getState().applyHostStatus(d.host_id, d.status);
        }
      } else {
        // Pure legacy event (pre-Phase-03 hosts): patch the global view.
        useHostStore
          .getState()
          .applyHostStatusChange(d.host_id, d.status, undefined);
      }
      break;
    }
    case 'communication_start': {
      const d = env.data as {
        id: string;
        project_id?: string | null;
        source_host_id: string;
        dest_host_id: string;
      };
      // Phase 06/07 — events carry project_id. With server-side scoping
      // we shouldn't ever see a start event for a project we're not
      // subscribed to, but we still fall back to the current project for
      // legacy/global viewers. Either way, we now stamp `project_id`
      // into the in-flight record so the realtime store can bucket it
      // correctly.
      const current = useProjectStore.getState().current;
      const targetProjectId = d.project_id ?? (current ? current.id : null);
      if (targetProjectId) {
        if (!current || current.id === targetProjectId) {
          markInFlight({
            id: d.id,
            project_id: targetProjectId,
            source: d.source_host_id,
            target: d.dest_host_id,
            startedAt: Date.now(),
          });
        }
      } else {
        // Project-less event (legacy/global): route into a sentinel
        // bucket so the legacy TopologyView still shows it. We use the
        // empty string as the project key — the store treats any string
        // as a valid bucket name.
        markInFlight({
          id: d.id,
          project_id: '',
          source: d.source_host_id,
          target: d.dest_host_id,
          startedAt: Date.now(),
        });
      }
      break;
    }
    case 'communication_complete': {
      const d = env.data as Communication & { timestamp: string };
      // Phase 06/07 — comm events carry project_id. The store's
      // `upsertCommunication` writes the comm into the right per-project
      // bucket automatically. We DO clear the in-flight indicator only
      // when the event belongs to the project we currently care about
      // (the realtime store keeps the entry visible for MIN_VISIBLE_MS
      // even after clearInFlight is called, so timing isn't racy).
      const current = useProjectStore.getState().current;
      const targetProjectId = d.project_id ?? (current ? current.id : null);
      if (
        !targetProjectId ||
        !current ||
        current.id === targetProjectId
      ) {
        clearInFlight(d.id);
      }
      useCommStore.getState().upsertCommunication(d);
      break;
    }
    case 'subscribed':
    case 'pong':
      // Phase 07 control acks — no-op. The "subscribed" envelope confirms
      // the server registered our subscription; "pong" answers our
      // keepalive ping. Neither carries domain data.
      break;
    default:
      // Ignore unknown event types.
      break;
  }
}

/**
 * Surface selected WS events as toast notifications.
 * Phase 6 deliverable — small toast system for important events.
 */
function surfaceToasts(env: EventEnvelope) {
  const push = useToastStore.getState().push;
  switch (env.type) {
    case 'host_status_change': {
      const d = env.data as {
        host_id: string;
        status: HostStatus;
        project_id?: string | null;
      };
      if (d.status === 'offline') {
        push({
          kind: 'warning',
          title: `${d.host_id} went offline`,
          message: d.project_id
            ? `Project ${shortId(d.project_id)}: no heartbeat for 15+ s`
            : 'No heartbeat received for 15+ seconds.',
        });
      }
      break;
    }
    case 'communication_complete': {
      const d = env.data as { source_host_id: string; dest_host_id: string; status: string };
      if (d.status === 'failed') {
        push({
          kind: 'error',
          title: `Delivery failed`,
          message: `${d.source_host_id} → ${d.dest_host_id}`,
        });
      }
      break;
    }
    default:
      break;
  }
}

function shortId(id: string): string {
  return id.replace(/-/g, '').slice(0, 8);
}
