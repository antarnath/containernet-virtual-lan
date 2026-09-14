// Project store — owns the list of projects and the currently-loaded
// project (with topology + hosts + edges). Pages read from this store
// instead of fetching on their own.

import { create } from 'zustand';
import { ProjectsAPI } from '../api/client';
import type {
  NodePosition,
  Project,
  ProjectCreate,
  ProjectDetail,
} from '../types';

interface ProjectState {
  // List view (summary cards on /projects)
  projects: Project[];
  projectsLoading: boolean;
  projectsError: string | null;

  // Currently-loaded project (full detail, including hosts + edges)
  current: ProjectDetail | null;
  currentLoading: boolean;
  currentError: string | null;

  // Last lifecycle action in flight (so buttons can show a spinner)
  actionInFlight: string | null;

  // ─── actions ─────────────────────────────────────────────────
  fetchProjects: () => Promise<void>;
  fetchProject: (projectId: string) => Promise<ProjectDetail | null>;
  createProject: (body: ProjectCreate) => Promise<ProjectDetail | null>;
  startProject: (projectId: string) => Promise<ProjectDetail | null>;
  stopProject: (projectId: string) => Promise<ProjectDetail | null>;
  deleteProject: (projectId: string) => Promise<boolean>;
  setNodePosition: (
    projectId: string,
    hostId: string,
    pos: NodePosition,
  ) => Promise<void>;
  applyHostStatus: (
    hostId: string,
    status: 'online' | 'offline' | 'unknown',
  ) => void;
  clearCurrent: () => void;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  projectsLoading: false,
  projectsError: null,

  current: null,
  currentLoading: false,
  currentError: null,

  actionInFlight: null,

  fetchProjects: async () => {
    set({ projectsLoading: true, projectsError: null });
    try {
      const res = await ProjectsAPI.list();
      set({ projects: res.projects, projectsLoading: false });
    } catch (e) {
      set({ projectsError: (e as Error).message, projectsLoading: false });
    }
  },

  fetchProject: async (projectId) => {
    set({ currentLoading: true, currentError: null });
    try {
      const project = await ProjectsAPI.get(projectId);
      set({ current: project, currentLoading: false });
      return project;
    } catch (e) {
      set({ currentError: (e as Error).message, currentLoading: false });
      return null;
    }
  },

  createProject: async (body) => {
    set({ actionInFlight: 'create' });
    try {
      const project = await ProjectsAPI.create(body);
      set((s) => ({
        projects: [project, ...s.projects],
        current: project,
        actionInFlight: null,
      }));
      return project;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  startProject: async (projectId) => {
    set({ actionInFlight: 'start' });
    try {
      const project = await ProjectsAPI.start(projectId);
      // Patch the list entry as well.
      set((s) => ({
        current: project,
        projects: s.projects.map((p) => (p.id === projectId ? project : p)),
        actionInFlight: null,
      }));
      return project;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  stopProject: async (projectId) => {
    set({ actionInFlight: 'stop' });
    try {
      const project = await ProjectsAPI.stop(projectId);
      set((s) => ({
        current: project,
        projects: s.projects.map((p) => (p.id === projectId ? project : p)),
        actionInFlight: null,
      }));
      return project;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  deleteProject: async (projectId) => {
    set({ actionInFlight: 'delete' });
    try {
      await ProjectsAPI.delete(projectId);
      set((s) => ({
        projects: s.projects.filter((p) => p.id !== projectId),
        current: s.current?.id === projectId ? null : s.current,
        actionInFlight: null,
      }));
      return true;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  setNodePosition: async (projectId, hostId, pos) => {
    // Optimistic local update so the drag feels instant.
    const current = get().current;
    if (current && current.id === projectId) {
      set({
        current: {
          ...current,
          hosts: current.hosts.map((h) =>
            h.host_id === hostId
              ? { ...h, position_x: pos.position_x, position_y: pos.position_y }
              : h,
          ),
        },
      });
    }
    try {
      await ProjectsAPI.updateNodePosition(projectId, hostId, pos);
    } catch (e) {
      // On error, refetch to resync with server truth.
      await get().fetchProject(projectId);
      throw e;
    }
  },

  applyHostStatus: (hostId, status) => {
    const current = get().current;
    if (!current) return;
    set({
      current: {
        ...current,
        hosts: current.hosts.map((h) =>
          h.host_id === hostId ? { ...h, status } : h,
        ),
      },
    });
  },

  clearCurrent: () => set({ current: null, currentError: null }),
}));
