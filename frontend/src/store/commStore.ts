// Global store for communications history + trigger action.

import { create } from 'zustand';
import { CommunicationsAPI } from '../api/client';
import type { Communication, CommunicationCreate } from '../types';

interface CommState {
  communications: Communication[];
  loading: boolean;
  error: string | null;

  fetchComms: () => Promise<void>;
  trigger: (body: CommunicationCreate) => Promise<Communication | null>;
  upsertCommunication: (comm: Communication) => void;
}

export const useCommStore = create<CommState>((set, get) => ({
  communications: [],
  loading: false,
  error: null,

  fetchComms: async () => {
    try {
      const data = await CommunicationsAPI.list();
      set({ communications: data.communications, error: null });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  trigger: async (body) => {
    set({ loading: true });
    try {
      const comm = await CommunicationsAPI.trigger(body);
      // Optimistically prepend to the list, then refresh from server.
      set({ communications: [comm, ...get().communications], loading: false });
      // Re-fetch shortly after so the orchestrator's final latency/status is reflected.
      setTimeout(() => get().fetchComms(), 500);
      return comm;
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
      return null;
    }
  },

  // Used by the WebSocket hook when a "communication_complete" event arrives.
  // If the comm already exists, replace it (status went from pending ->
  // delivered/failed). Otherwise prepend it.
  upsertCommunication: (comm) => {
    const existing = get().communications;
    const idx = existing.findIndex((c) => c.id === comm.id);
    if (idx === -1) {
      set({ communications: [comm, ...existing] });
    } else {
      const copy = [...existing];
      copy[idx] = comm;
      set({ communications: copy });
    }
  },
}));