// Singleton WebSocket connection that auto-reconnects with backoff.
// Routes incoming events to the relevant Zustand stores.

import { useEffect } from 'react';
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
  data: any;
  ts: string;
}

export function useWebSocket() {
  const setStatus = useRealtimeStore((s) => s.setStatus);
  const markInFlight = useRealtimeStore((s) => s.markInFlight);
  const clearInFlight = useRealtimeStore((s) => s.clearInFlight);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let attempt = 0;
    let reconnectTimer: number | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      setStatus('connecting');
      try {
        socket = new WebSocket(wsUrl());
      } catch (e) {
        scheduleReconnect();
        return;
      }

      socket.onopen = () => {
        attempt = 0;
        setStatus('open');
      };

      socket.onmessage = (ev) => {
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

      socket.onclose = () => {
        setStatus('closed');
        scheduleReconnect();
      };

      socket.onerror = () => {
        try {
          socket?.close();
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
      try {
        socket?.close();
      } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

function handleEvent(
  env: EventEnvelope,
  markInFlight: (c: { id: string; source: string; target: string; startedAt: number }) => void,
  clearInFlight: (id: string) => void,
) {
  switch (env.type) {
    case 'host_status_change': {
      // Phase 05 — events now carry `project_id`. We filter by the currently
      // loaded project so a status change in Project A doesn't perturb
      // Project B's display. We also patch the per-project host list and
      // the projectStore.current so the topology LEDs stay in sync.
      const d = env.data as {
        host_id: string;
        status: HostStatus;
        project_id?: string | null;
      };
      const current = useProjectStore.getState().current;
      const targetProjectId =
        d.project_id ?? (current ? current.id : undefined);
      // Only apply to the per-project store if the event is for the project
      // we are currently viewing, OR if we have no current project loaded
      // (legacy global dashboard).
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
        source_host_id: string;
        dest_host_id: string;
      };
      markInFlight({
        id: d.id,
        source: d.source_host_id,
        target: d.dest_host_id,
        startedAt: Date.now(),
      });
      break;
    }
    case 'communication_complete': {
      const d = env.data as Communication & { timestamp: string };
      clearInFlight(d.id);
      useCommStore.getState().upsertCommunication(d);
      break;
    }
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