// Thin Axios wrapper. The base URL is "/api" — both Vite (dev) and
// Nginx (prod) forward /api/* to the backend container.
//
// M4 — 5-primitive model. The ProjectsAPI exposes the full canvas
// surface: project CRUD, node CRUD, interface CRUD, link CRUD.

import axios from 'axios';
import type {
  Project,
  ProjectCreate,
  ProjectDetail,
  ProjectInterface,
  ProjectInterfaceCreate,
  ProjectInterfaceUpdate,
  ProjectLink,
  ProjectLinkCreate,
  ProjectListResponse,
  ProjectNode,
  ProjectNodeCreate,
  ProjectNodeUpdate,
  ProjectUpdate,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

export const ProjectsAPI = {
  // ─── Project CRUD ────────────────────────────────────────────────
  list: async (): Promise<ProjectListResponse> => {
    const { data } = await api.get<ProjectListResponse>('/projects');
    return data;
  },
  get: async (projectId: string): Promise<ProjectDetail> => {
    const { data } = await api.get<ProjectDetail>(`/projects/${projectId}`);
    return data;
  },
  create: async (body: ProjectCreate): Promise<ProjectDetail> => {
    const { data } = await api.post<ProjectDetail>('/projects', body);
    return data;
  },
  update: async (
    projectId: string,
    body: ProjectUpdate,
  ): Promise<Project> => {
    const { data } = await api.patch<Project>(`/projects/${projectId}`, body);
    return data;
  },
  delete: async (projectId: string): Promise<void> => {
    await api.delete(`/projects/${projectId}`);
  },

  // ─── Lifecycle (phase 02) ────────────────────────────────────────
  // start, stop, restart all return the updated ProjectDetail
  // (project + nodes + links) so the canvas can refresh its state
  // in one round-trip. `state` is a lighter-weight snapshot used
  // for the status pills and error toasts.
  start: async (projectId: string): Promise<ProjectDetail> => {
    const { data } = await api.post<ProjectDetail>(`/projects/${projectId}/start`);
    return data;
  },
  stop: async (projectId: string): Promise<ProjectDetail> => {
    const { data } = await api.post<ProjectDetail>(`/projects/${projectId}/stop`);
    return data;
  },
  restart: async (projectId: string): Promise<ProjectDetail> => {
    const { data } = await api.post<ProjectDetail>(`/projects/${projectId}/restart`);
    return data;
  },
  state: async (
    projectId: string,
  ): Promise<{
    project_id: string;
    status: string;
    nodes: Array<{
      id: string;
      name: string;
      kind: string;
      container_id: string | null;
      container_status: string;
      container: {
        id: string;
        name: string;
        status: string;
        image: string;
      } | null;
    }>;
    links: Array<{
      id: string;
      iface_a_id: string;
      iface_b_id: string;
      docker_bridge_name: string | null;
      bridge: {
        network_id: string;
        name: string;
        short_name: string;
        subnet_cidr: string;
      } | null;
    }>;
  }> => {
    const { data } = await api.get(`/projects/${projectId}/state`);
    return data;
  },

  // ─── Node CRUD ──────────────────────────────────────────────────
  nodes: {
    create: async (
      projectId: string,
      body: ProjectNodeCreate,
    ): Promise<ProjectNode> => {
      const { data } = await api.post<ProjectNode>(
        `/projects/${projectId}/nodes`,
        body,
      );
      return data;
    },
    get: async (
      projectId: string,
      nodeId: string,
    ): Promise<ProjectNode> => {
      const { data } = await api.get<ProjectNode>(
        `/projects/${projectId}/nodes/${nodeId}`,
      );
      return data;
    },
    update: async (
      projectId: string,
      nodeId: string,
      body: ProjectNodeUpdate,
    ): Promise<ProjectNode> => {
      const { data } = await api.patch<ProjectNode>(
        `/projects/${projectId}/nodes/${nodeId}`,
        body,
      );
      return data;
    },
    delete: async (
      projectId: string,
      nodeId: string,
    ): Promise<void> => {
      await api.delete(`/projects/${projectId}/nodes/${nodeId}`);
    },
    // Live state for a single node (phase 03). For routers, includes
    // the cached /state/all payload from the agent. Always includes
    // the open + recent anomalies list.
    state: async (
      projectId: string,
      nodeId: string,
    ): Promise<NodeLiveState> => {
      const { data } = await api.get<NodeLiveState>(
        `/projects/${projectId}/nodes/${nodeId}/state`,
      );
      return data;
    },
  },

  // ─── Interface CRUD ─────────────────────────────────────────────
  interfaces: {
    create: async (
      projectId: string,
      nodeId: string,
      body: ProjectInterfaceCreate,
    ): Promise<ProjectInterface> => {
      const { data } = await api.post<ProjectInterface>(
        `/projects/${projectId}/nodes/${nodeId}/interfaces`,
        body,
      );
      return data;
    },
    update: async (
      projectId: string,
      ifaceId: string,
      body: ProjectInterfaceUpdate,
    ): Promise<ProjectInterface> => {
      const { data } = await api.patch<ProjectInterface>(
        `/projects/${projectId}/interfaces/${ifaceId}`,
        body,
      );
      return data;
    },
    delete: async (
      projectId: string,
      ifaceId: string,
    ): Promise<void> => {
      await api.delete(`/projects/${projectId}/interfaces/${ifaceId}`);
    },
  },

  // ─── Link CRUD ─────────────────────────────────────────────────
  links: {
    create: async (
      projectId: string,
      body: ProjectLinkCreate,
    ): Promise<ProjectLink> => {
      const { data } = await api.post<ProjectLink>(
        `/projects/${projectId}/links`,
        body,
      );
      return data;
    },
    delete: async (
      projectId: string,
      linkId: string,
    ): Promise<void> => {
      await api.delete(`/projects/${projectId}/links/${linkId}`);
    },
  },

  // ─── Anomalies (phase 03) ─────────────────────────────────────
  anomalies: {
    list: async (
      projectId: string,
      includeResolved = false,
    ): Promise<{ project_id: string; anomalies: AnomalyEvent[] }> => {
      const { data } = await api.get<{
        project_id: string;
        anomalies: AnomalyEvent[];
      }>(`/projects/${projectId}/anomalies`, {
        params: { include_resolved: includeResolved },
      });
      return data;
    },
    dismiss: async (
      projectId: string,
      anomalyId: string,
    ): Promise<{ id: string; resolved_at: string }> => {
      const { data } = await api.post<{ id: string; resolved_at: string }>(
        `/projects/${projectId}/anomalies/${anomalyId}/dismiss`,
      );
      return data;
    },
  },
};

export default api;

// ─── Phase 03 — live node state + anomaly shapes ─────────────────────

export interface AnomalyEvent {
  id: string;
  /** The anomaly kind, e.g. "arp_mac_change", "neigh_stale". */
  kind: string;
  /** "info" | "warn" | "danger". */
  severity: 'info' | 'warn' | 'danger';
  summary: string;
  detail: Record<string, unknown>;
  created_at: string;
  resolved_at: string | null;
  /** Only present on list endpoints. */
  node_id?: string;
}

export interface NodeLiveState {
  node_id: string;
  name: string;
  kind: string;
  container_id: string | null;
  container_status: string;
  anomalies: AnomalyEvent[];
  /** null for non-router nodes. */
  router: {
    routes: Array<{
      destination: string;
      gateway: string;
      iface: string;
      protocol: string;
      scope: string;
      source: string;
    }>;
    neigh: Array<{
      ip: string;
      iface: string;
      mac: string;
      state: string;
      age: string;
    }>;
    ifaces: Array<{
      name: string;
      state: string;
      ip_mask: string;
      mac: string;
    }>;
    fetched_at: number;
    error: string | null;
  } | null;
}
