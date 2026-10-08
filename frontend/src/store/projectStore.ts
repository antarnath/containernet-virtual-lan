// M4 project store — owns the list of projects and the currently-loaded
// canvas (project + nodes + interfaces + links). The canvas page hydrates
// from `current` on mount; every CRUD action updates both the local
// `current` and the matching summary in `projects` so the list page
// stays accurate without a refetch.

import { create } from 'zustand';
import { ProjectsAPI } from '../api/client';
import type {
  Project,
  ProjectCreate,
  ProjectDetail,
  ProjectInterface,
  ProjectInterfaceCreate,
  ProjectInterfaceUpdate,
  ProjectLink,
  ProjectLinkCreate,
  ProjectNode,
  ProjectNodeCreate,
  ProjectNodeUpdate,
  ProjectUpdate,
} from '../types';

interface ProjectState {
  // List view (cards on /projects)
  projects: Project[];
  projectsLoading: boolean;
  projectsError: string | null;

  // Currently-loaded project (full canvas: project + nodes + links)
  current: ProjectDetail | null;
  currentLoading: boolean;
  currentError: string | null;

  // Last lifecycle / mutation in flight (so buttons can show a spinner)
  actionInFlight: string | null;

  // ─── list + project ─────────────────────────────────────────
  fetchProjects: () => Promise<void>;
  fetchProject: (projectId: string) => Promise<ProjectDetail | null>;
  createProject: (body: ProjectCreate) => Promise<ProjectDetail | null>;
  updateProject: (
    projectId: string,
    body: ProjectUpdate,
  ) => Promise<ProjectDetail | null>;
  deleteProject: (projectId: string) => Promise<boolean>;
  setViewport: (
    projectId: string,
    viewport: { viewport_x: number; viewport_y: number; viewport_zoom: number },
  ) => Promise<void>;
  clearCurrent: () => void;

  // ─── node mutations ─────────────────────────────────────────
  addNode: (
    projectId: string,
    body: ProjectNodeCreate,
  ) => Promise<ProjectNode | null>;
  updateNode: (
    projectId: string,
    nodeId: string,
    body: ProjectNodeUpdate,
  ) => Promise<ProjectNode | null>;
  deleteNode: (projectId: string, nodeId: string) => Promise<boolean>;
  moveNode: (
    projectId: string,
    nodeId: string,
    canvas: { canvas_x: number; canvas_y: number },
  ) => Promise<void>;

  // ─── interface mutations ────────────────────────────────────
  addInterface: (
    projectId: string,
    nodeId: string,
    body: ProjectInterfaceCreate,
  ) => Promise<ProjectInterface | null>;
  updateInterface: (
    projectId: string,
    ifaceId: string,
    body: ProjectInterfaceUpdate,
  ) => Promise<ProjectInterface | null>;
  deleteInterface: (projectId: string, ifaceId: string) => Promise<boolean>;

  // ─── link mutations ─────────────────────────────────────────
  addLink: (
    projectId: string,
    body: ProjectLinkCreate,
  ) => Promise<ProjectLink | null>;
  deleteLink: (projectId: string, linkId: string) => Promise<boolean>;
}

// ─── helpers ─────────────────────────────────────────────────────────────

function patchProjectList(
  projects: Project[],
  updated: Project,
): Project[] {
  return projects.map((p) => (p.id === updated.id ? updated : p));
}

function patchCurrentNode(
  current: ProjectDetail,
  nodeId: string,
  patch: Partial<ProjectNode>,
): ProjectDetail {
  return {
    ...current,
    nodes: current.nodes.map((n) => (n.id === nodeId ? { ...n, ...patch } : n)),
  };
}

function patchCurrentInterface(
  current: ProjectDetail,
  ifaceId: string,
  patch: Partial<ProjectInterface>,
): ProjectDetail {
  return {
    ...current,
    nodes: current.nodes.map((n) => ({
      ...n,
      interfaces: n.interfaces.map((i) =>
        i.id === ifaceId ? { ...i, ...patch } : i,
      ),
    })),
  };
}

function recomputeCounts(detail: ProjectDetail): ProjectDetail {
  return {
    ...detail,
    node_count: detail.nodes.length,
    link_count: detail.links.length,
  };
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  projectsLoading: false,
  projectsError: null,

  current: null,
  currentLoading: false,
  currentError: null,

  actionInFlight: null,

  // ─── list + project ─────────────────────────────────────────

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
        projects: [
          {
            id: project.id,
            name: project.name,
            status: project.status,
            viewport_x: project.viewport_x,
            viewport_y: project.viewport_y,
            viewport_zoom: project.viewport_zoom,
            node_count: project.node_count,
            link_count: project.link_count,
            created_at: project.created_at,
            updated_at: project.updated_at,
          },
          ...s.projects,
        ],
        current: project,
        actionInFlight: null,
      }));
      return project;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  updateProject: async (projectId, body) => {
    set({ actionInFlight: 'update' });
    try {
      const project = await ProjectsAPI.update(projectId, body);
      set((s) => ({
        projects: patchProjectList(s.projects, project),
        current:
          s.current && s.current.id === projectId
            ? { ...s.current, ...project }
            : s.current,
        actionInFlight: null,
      }));
      const after = get().current;
      return after && after.id === projectId ? after : null;
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

  setViewport: async (projectId, viewport) => {
    // Optimistic local update so pan/zoom stays smooth.
    const current = get().current;
    if (current && current.id === projectId) {
      set({
        current: { ...current, ...viewport },
        projects: get().projects.map((p) =>
          p.id === projectId ? { ...p, ...viewport } : p,
        ),
      });
    }
    try {
      await ProjectsAPI.update(projectId, viewport);
    } catch (e) {
      // Resync on failure.
      await get().fetchProject(projectId);
      throw e;
    }
  },

  clearCurrent: () => set({ current: null, currentError: null }),

  // ─── node mutations ─────────────────────────────────────────

  addNode: async (projectId, body) => {
    set({ actionInFlight: 'add-node' });
    try {
      const node = await ProjectsAPI.nodes.create(projectId, body);
      set((s) => {
        if (!s.current || s.current.id !== projectId) return s;
        return {
          current: recomputeCounts({
            ...s.current,
            nodes: [...s.current.nodes, node],
          }),
          actionInFlight: null,
        };
      });
      // Refresh the list-card counts.
      void get().fetchProjects();
      return node;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  updateNode: async (projectId, nodeId, body) => {
    set({ actionInFlight: 'update-node' });
    try {
      const node = await ProjectsAPI.nodes.update(projectId, nodeId, body);
      set((s) => {
        if (!s.current || s.current.id !== projectId) return s;
        return {
          current: patchCurrentNode(s.current, nodeId, node),
          actionInFlight: null,
        };
      });
      return node;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  deleteNode: async (projectId, nodeId) => {
    set({ actionInFlight: 'delete-node' });
    try {
      await ProjectsAPI.nodes.delete(projectId, nodeId);
      set((s) => {
        if (!s.current || s.current.id !== projectId) return s;
        const current = s.current;
        const live = new Set(
          current.nodes.flatMap((n) => n.interfaces.map((i) => i.id)),
        );
        return {
          current: recomputeCounts({
            ...current,
            nodes: current.nodes.filter((n) => n.id !== nodeId),
            links: current.links.filter(
              (l) => live.has(l.iface_a_id) && live.has(l.iface_b_id),
            ),
          }),
          actionInFlight: null,
        };
      });
      void get().fetchProjects();
      return true;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  moveNode: async (projectId, nodeId, canvas) => {
    // Optimistic update so dragging stays smooth.
    const current = get().current;
    if (current && current.id === projectId) {
      set({
        current: patchCurrentNode(current, nodeId, canvas),
      });
    }
    try {
      await ProjectsAPI.nodes.update(projectId, nodeId, canvas);
    } catch (e) {
      // Resync on failure.
      await get().fetchProject(projectId);
      throw e;
    }
  },

  // ─── interface mutations ────────────────────────────────────

  addInterface: async (projectId, nodeId, body) => {
    set({ actionInFlight: 'add-iface' });
    try {
      const iface = await ProjectsAPI.interfaces.create(
        projectId,
        nodeId,
        body,
      );
      set((s) => {
        if (!s.current || s.current.id !== projectId) return s;
        return {
          current: {
            ...s.current,
            nodes: s.current.nodes.map((n) =>
              n.id === nodeId
                ? { ...n, interfaces: [...n.interfaces, iface] }
                : n,
            ),
          },
          actionInFlight: null,
        };
      });
      return iface;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  updateInterface: async (projectId, ifaceId, body) => {
    set({ actionInFlight: 'update-iface' });
    try {
      const iface = await ProjectsAPI.interfaces.update(
        projectId,
        ifaceId,
        body,
      );
      set((s) => {
        if (!s.current || s.current.id !== projectId) return s;
        return {
          current: patchCurrentInterface(s.current, ifaceId, iface),
          actionInFlight: null,
        };
      });
      return iface;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  deleteInterface: async (projectId, ifaceId) => {
    set({ actionInFlight: 'delete-iface' });
    try {
      await ProjectsAPI.interfaces.delete(projectId, ifaceId);
      set((s) => {
        if (!s.current || s.current.id !== projectId) return s;
        return {
          current: {
            ...s.current,
            nodes: s.current.nodes.map((n) => ({
              ...n,
              interfaces: n.interfaces.filter((i) => i.id !== ifaceId),
            })),
          },
          actionInFlight: null,
        };
      });
      return true;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  // ─── link mutations ─────────────────────────────────────────

  addLink: async (projectId, body) => {
    set({ actionInFlight: 'add-link' });
    try {
      const link = await ProjectsAPI.links.create(projectId, body);
      set((s) => {
        if (!s.current || s.current.id !== projectId) return s;
        return {
          current: recomputeCounts({
            ...s.current,
            links: [...s.current.links, link],
          }),
          actionInFlight: null,
        };
      });
      void get().fetchProjects();
      return link;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },

  deleteLink: async (projectId, linkId) => {
    set({ actionInFlight: 'delete-link' });
    try {
      await ProjectsAPI.links.delete(projectId, linkId);
      set((s) => {
        if (!s.current || s.current.id !== projectId) return s;
        return {
          current: recomputeCounts({
            ...s.current,
            links: s.current.links.filter((l) => l.id !== linkId),
          }),
          actionInFlight: null,
        };
      });
      void get().fetchProjects();
      return true;
    } catch (e) {
      set({ actionInFlight: null });
      throw e;
    }
  },
}));
