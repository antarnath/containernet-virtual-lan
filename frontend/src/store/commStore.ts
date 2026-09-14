// Per-project communications store (Phase 06).
//
// Like hostStore, this is keyed by project_id so the UI naturally isolates
// one project's log from another. The legacy flat list lives behind
// `legacy.comms` for the (now-deprecated) global page.

import { create } from 'zustand';
import { CommunicationsAPI, ProjectsAPI } from '../api/client';
import type { Communication, CommunicationCreate } from '../types';

interface ProjectCommBundle {
  communications: Communication[];
  loading: boolean;
  error: string | null;
}

interface CommState {
  /** Indexed by project_id. */
  byProject: Record<string, ProjectCommBundle>;
  /** Legacy flat list (no project scope). Used only by the legacy page. */
  legacy: {
    communications: Communication[];
    loading: boolean;
    error: string | null;
  };

  /** Load (or refresh) communications for a single project. */
  fetchForProject: (projectId: string, limit?: number) => Promise<void>;
  /** Trigger a new communication scoped to a project. */
  trigger: (
    projectId: string,
    body: CommunicationCreate,
  ) => Promise<Communication | null>;
  /** WebSocket event hook — applies an incoming comm to the right bucket. */
  upsertCommunication: (comm: Communication) => void;

  /** Legacy global fetch (used by the legacy page only). */
  fetchLegacy: () => Promise<void>;
}

const emptyBundle = (): ProjectCommBundle => ({
  communications: [],
  loading: false,
  error: null,
});

export const useCommStore = create<CommState>((set, get) => ({
  byProject: {},
  legacy: { communications: [], loading: false, error: null },

  fetchForProject: async (projectId, limit = 100) => {
    const current = get().byProject[projectId] ?? emptyBundle();
    set({
      byProject: {
        ...get().byProject,
        [projectId]: { ...current, loading: true, error: null },
      },
    });
    try {
      const data = await ProjectsAPI.communications.list(projectId, limit);
      set({
        byProject: {
          ...get().byProject,
          [projectId]: {
            communications: data.communications,
            loading: false,
            error: null,
          },
        },
      });
    } catch (e) {
      set({
        byProject: {
          ...get().byProject,
          [projectId]: {
            ...(get().byProject[projectId] ?? emptyBundle()),
            loading: false,
            error: (e as Error).message,
          },
        },
      });
    }
  },

  trigger: async (projectId, body) => {
    const current = get().byProject[projectId] ?? emptyBundle();
    set({
      byProject: {
        ...get().byProject,
        [projectId]: { ...current, loading: true, error: null },
      },
    });
    try {
      const comm = await ProjectsAPI.communications.trigger(projectId, body);
      const updated = current.communications;
      set({
        byProject: {
          ...get().byProject,
          [projectId]: {
            communications: [comm, ...updated],
            loading: false,
            error: null,
          },
        },
      });
      // Re-fetch shortly after so the orchestrator's final latency/status is
      // reflected. The backend returns DELIVERED/FAILED a moment later.
      setTimeout(() => {
        void get().fetchForProject(projectId);
      }, 500);
      return comm;
    } catch (e) {
      set({
        byProject: {
          ...get().byProject,
          [projectId]: { ...current, loading: false, error: (e as Error).message },
        },
      });
      return null;
    }
  },

  upsertCommunication: (comm) => {
    const projectId = comm.project_id ?? '';
    if (!projectId) {
      // Fall back to the legacy bucket.
      const legacy = get().legacy.communications;
      const idx = legacy.findIndex((c) => c.id === comm.id);
      if (idx === -1) {
        set({ legacy: { ...get().legacy, communications: [comm, ...legacy] } });
      } else {
        const copy = [...legacy];
        copy[idx] = comm;
        set({ legacy: { ...get().legacy, communications: copy } });
      }
      return;
    }
    const bucket = get().byProject[projectId] ?? emptyBundle();
    const idx = bucket.communications.findIndex((c) => c.id === comm.id);
    const nextList =
      idx === -1
        ? [comm, ...bucket.communications]
        : bucket.communications.map((c) => (c.id === comm.id ? comm : c));
    set({
      byProject: {
        ...get().byProject,
        [projectId]: { ...bucket, communications: nextList },
      },
    });
  },

  fetchLegacy: async () => {
    set({ legacy: { ...get().legacy, loading: true, error: null } });
    try {
      const data = await CommunicationsAPI.list();
      set({
        legacy: { communications: data.communications, loading: false, error: null },
      });
    } catch (e) {
      set({
        legacy: {
          ...get().legacy,
          loading: false,
          error: (e as Error).message,
        },
      });
    }
  },
}));
