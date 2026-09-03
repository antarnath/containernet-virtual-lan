// Tracks live WebSocket connection status + which communications are
// currently in flight (so the topology can animate their edges).
//
// Each in-flight entry has a `visibleUntil` timestamp. We guarantee the edge
// stays highlighted for at least MIN_VISIBLE_MS so the user can see the
// animation, even if the actual backend round-trip is <10ms.

import { create } from 'zustand';

export type WsStatus = 'connecting' | 'open' | 'closed';

export const MIN_VISIBLE_MS = 1500;

interface ActiveComm {
  id: string;
  source: string;
  target: string;
  startedAt: number;
  visibleUntil: number;
}

interface RealtimeState {
  wsStatus: WsStatus;
  inFlight: ActiveComm[];

  setStatus: (s: WsStatus) => void;
  markInFlight: (c: Omit<ActiveComm, 'visibleUntil'>) => void;
  clearInFlight: (id: string) => void;
  clearAll: () => void;
}

export const useRealtimeStore = create<RealtimeState>((set, get) => {
  // Pending timers keyed by comm id, so we can cancel them if needed.
  const pendingTimers = new Map<string, ReturnType<typeof setTimeout>>();

  function scheduleExpiry(id: string, visibleUntil: number) {
    const delay = Math.max(0, visibleUntil - Date.now());
    const t = setTimeout(() => {
      pendingTimers.delete(id);
      set((state) => ({
        inFlight: state.inFlight.filter((c) => c.id !== id),
      }));
    }, delay);
    pendingTimers.set(id, t);
  }

  return {
    wsStatus: 'connecting',
    inFlight: [],

    setStatus: (s) => set({ wsStatus: s }),

    markInFlight: (c) => {
      const visibleUntil = Date.now() + MIN_VISIBLE_MS;
      set((state) => {
        // Don't duplicate if already tracked.
        if (state.inFlight.some((x) => x.id === c.id)) return state;
        return {
          inFlight: [
            ...state.inFlight,
            { ...c, visibleUntil },
          ],
        };
      });
      scheduleExpiry(c.id, visibleUntil);
    },

    clearInFlight: (id) => {
      // If a complete event arrives, don't clear immediately — let the
      // minimum-visible timer handle it. Only clear if there's no timer.
      if (pendingTimers.has(id)) return;
      set((state) => ({ inFlight: state.inFlight.filter((c) => c.id !== id) }));
    },

    clearAll: () => {
      pendingTimers.forEach((t) => clearTimeout(t));
      pendingTimers.clear();
      set({ inFlight: [] });
    },
  };
});