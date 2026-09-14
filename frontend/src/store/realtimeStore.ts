// Tracks live WebSocket connection status + which communications are
// currently in flight per project (so each project's topology can animate
// its own edges).
//
// Phase 07:
//   * `inFlightByProject` is the single source of truth, keyed by
//     `project_id`. Each entry has a `visibleUntil` timestamp so the
//     corresponding edge stays highlighted for at least MIN_VISIBLE_MS
//     even if the actual backend round-trip is <10ms.
//   * `getInFlight(projectId?)` is a derived helper used by both the new
//     per-project topology view (pass a projectId) and the legacy global
//     `/topology` page (omit the projectId to get the flattened union).
//
// We don't keep a separate top-level `inFlight` field — every consumer
// either asks for one project's array or asks for the union, and the
// union is computed on demand from the map.

import { create } from 'zustand';

export type WsStatus = 'connecting' | 'open' | 'closed';

export const MIN_VISIBLE_MS = 1500;

interface ActiveComm {
  id: string;
  project_id: string;
  source: string;
  target: string;
  startedAt: number;
  visibleUntil: number;
}

interface RealtimeState {
  wsStatus: WsStatus;
  /** Single source of truth: project_id -> in-flight comms. */
  inFlightByProject: Record<string, ActiveComm[]>;

  setStatus: (s: WsStatus) => void;
  markInFlight: (c: Omit<ActiveComm, 'visibleUntil'>) => void;
  clearInFlight: (id: string) => void;
  clearAll: () => void;
}

export const useRealtimeStore = create<RealtimeState>((set, get) => {
  // Pending timers keyed by comm id, so we can cancel them if needed.
  // The map is module-scoped (lives across renders) so timers survive
  // every selector subscription change.
  const pendingTimers = new Map<string, ReturnType<typeof setTimeout>>();

  function scheduleExpiry(id: string, projectId: string, visibleUntil: number) {
    const delay = Math.max(0, visibleUntil - Date.now());
    const t = setTimeout(() => {
      pendingTimers.delete(id);
      set((state) => {
        const bucket = state.inFlightByProject[projectId] ?? [];
        const next = bucket.filter((c) => c.id !== id);
        // Compact: drop empty buckets so the map doesn't grow forever.
        if (next.length === 0) {
          const { [projectId]: _gone, ...rest } = state.inFlightByProject;
          return { inFlightByProject: rest };
        }
        return {
          inFlightByProject: { ...state.inFlightByProject, [projectId]: next },
        };
      });
    }, delay);
    pendingTimers.set(id, t);
  }

  return {
    wsStatus: 'connecting',
    inFlightByProject: {},

    setStatus: (s) => set({ wsStatus: s }),

    markInFlight: (c) => {
      const visibleUntil = Date.now() + MIN_VISIBLE_MS;
      set((state) => {
        const bucket = state.inFlightByProject[c.project_id] ?? [];
        // Don't duplicate if already tracked for this project.
        if (bucket.some((x) => x.id === c.id)) return state;
        return {
          inFlightByProject: {
            ...state.inFlightByProject,
            [c.project_id]: [...bucket, { ...c, visibleUntil }],
          },
        };
      });
      scheduleExpiry(c.id, c.project_id, visibleUntil);
    },

    clearInFlight: (id) => {
      // If a `complete` event arrives before the visibility timer fires,
      // we still want the edge to stay highlighted for MIN_VISIBLE_MS,
      // so we don't drop the row here — let the timer handle expiry.
      if (pendingTimers.has(id)) return;
      set((state) => {
        const next: Record<string, ActiveComm[]> = {};
        let changed = false;
        for (const [pid, bucket] of Object.entries(state.inFlightByProject)) {
          const filtered = bucket.filter((c) => c.id !== id);
          if (filtered.length === bucket.length) {
            next[pid] = bucket;
          } else if (filtered.length === 0) {
            changed = true;
          } else {
            next[pid] = filtered;
            changed = true;
          }
        }
        return changed ? { inFlightByProject: next } : state;
      });
    },

    clearAll: () => {
      pendingTimers.forEach((t) => clearTimeout(t));
      pendingTimers.clear();
      set({ inFlightByProject: {} });
    },
  };
});

/**
 * Return the in-flight comms for one project, or the flat union across
 * every project when ``projectId`` is omitted. Used by:
 *
 *   * ``TopologyCanvas`` (per-project view) → ``getInFlight(projectId)``
 *   * ``TopologyView`` (legacy global view) → ``getInFlight()``
 *
 * Always returns a fresh array so consumers can safely `.length`, `.some`,
 * etc. without re-subscribing to the whole map.
 */
export function getInFlight(projectId?: string): ActiveComm[] {
  const map = useRealtimeStore.getState().inFlightByProject;
  if (projectId !== undefined) {
    return map[projectId] ?? [];
  }
  const out: ActiveComm[] = [];
  for (const bucket of Object.values(map)) {
    out.push(...bucket);
  }
  return out;
}

/**
 * React hook variant of ``getInFlight`` — re-renders the consumer whenever
 * the in-flight map changes. Use this inside React components; use the
 * standalone ``getInFlight`` helper from event handlers / effects.
 */
export function useInFlight(projectId?: string): ActiveComm[] {
  return useRealtimeStore((s) => {
    if (projectId !== undefined) {
      return s.inFlightByProject[projectId] ?? ([] as ActiveComm[]);
    }
    const out: ActiveComm[] = [];
    for (const bucket of Object.values(s.inFlightByProject)) {
      out.push(...bucket);
    }
    return out;
  });
}
