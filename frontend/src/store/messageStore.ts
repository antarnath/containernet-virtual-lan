// Per-project, per-host message console state (Phase 08).
//
// Storage shape:
//   byProjectHost[project_id][host_id] = MessageRecord[] (newest LAST — the
//   console renders newest at the bottom and auto-scrolls there).
//
// Two upsert paths feed this store:
//   1. Initial history fetch (GET …/hosts/<id>/messages) — newest first from
//   the backend; we reverse on insert so the in-memory order is newest last.
//   2. WebSocket "message" events — already newest last by arrival order.
//
// Both paths dedupe by `id` so a network blip that re-delivers the same row
// doesn't grow the array.

import { create } from 'zustand';
import { ProjectsAPI } from '../api/client';
import type { MessageRecord } from '../types';

interface MessageState {
  /** Indexed by project_id -> host_id -> messages (newest last). */
  byProjectHost: Record<string, Record<string, MessageRecord[]>>;

  /** Per-(project, host) hydrate from REST. */
  fetchHostHistory: (projectId: string, hostId: string) => Promise<void>;
  /** Hydrate every host of a project in one pass. */
  fetchProjectHistory: (projectId: string, hostIds: string[]) => Promise<void>;

  /** WebSocket event hook — append one message into the right bucket. */
  addMessage: (msg: MessageRecord) => void;

  /** Optimistic local clears (don't re-fetch). */
  clearHostMessages: (projectId: string, hostId: string) => void;
  clearProjectMessages: (projectId: string) => void;
}

const MAX_PER_HOST = 200; // cap so 30-host projects don't grow forever

function _appendInPlace(bucket: MessageRecord[], msg: MessageRecord): MessageRecord[] {
  // Dedup by id.
  if (bucket.some((m) => m.id === msg.id)) return bucket;
  const next = [...bucket, msg];
  if (next.length > MAX_PER_HOST) {
    // Drop the oldest entries.
    return next.slice(next.length - MAX_PER_HOST);
  }
  return next;
}

export const useMessageStore = create<MessageState>((set, get) => ({
  byProjectHost: {},

  fetchHostHistory: async (projectId, hostId) => {
    try {
      const data = await ProjectsAPI.messages.list(projectId, hostId);
      // Backend returns newest first — flip to oldest first (newest last)
      // so the console reads top→bottom in chronological order.
      const ordered = [...data.messages].reverse();
      set((state) => {
        const projectMap = state.byProjectHost[projectId] ?? {};
        return {
          byProjectHost: {
            ...state.byProjectHost,
            [projectId]: { ...projectMap, [hostId]: ordered },
          },
        };
      });
    } catch (e) {
      console.warn(`[messageStore] fetch failed for ${projectId}/${hostId}:`, e);
    }
  },

  fetchProjectHistory: async (projectId, hostIds) => {
    await Promise.all(
      hostIds.map((hostId) => get().fetchHostHistory(projectId, hostId)),
    );
  },

  addMessage: (msg) => {
    const { project_id, host_id } = msg;
    if (!project_id || !host_id) return;
    set((state) => {
      const projectMap = state.byProjectHost[project_id] ?? {};
      const bucket = projectMap[host_id] ?? [];
      return {
        byProjectHost: {
          ...state.byProjectHost,
          [project_id]: {
            ...projectMap,
            [host_id]: _appendInPlace(bucket, msg),
          },
        },
      };
    });
  },

  clearHostMessages: (projectId, hostId) => {
    set((state) => {
      const projectMap = state.byProjectHost[projectId];
      if (!projectMap) return state;
      return {
        byProjectHost: {
          ...state.byProjectHost,
          [projectId]: { ...projectMap, [hostId]: [] },
        },
      };
    });
  },

  clearProjectMessages: (projectId) => {
    set((state) => {
      if (!state.byProjectHost[projectId]) return state;
      const { [projectId]: _gone, ...rest } = state.byProjectHost;
      return { byProjectHost: rest };
    });
  },
}));

// Convenience hook — grab the message list for one (project, host) pair.
export function useHostMessages(projectId: string, hostId: string): MessageRecord[] {
  return useMessageStore(
    (s) => s.byProjectHost[projectId]?.[hostId] ?? EMPTY,
  );
}

const EMPTY: MessageRecord[] = [];