// Thin Axios wrapper. The base URL is "/api" — both Vite (dev) and
// Nginx (prod) forward /api/* to the backend container.

import axios from 'axios';
import type {
  Communication,
  CommunicationCreate,
  CommunicationListResponse,
  HostListResponse,
  NodePosition,
  Project,
  ProjectCreate,
  ProjectDetail,
  ProjectHost,
  ProjectHostListResponse,
  ProjectListResponse,
  TopologyResponse,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

export const HostsAPI = {
  /** Legacy flat list across every project. Deprecated — use ProjectsAPI.hosts.list. */
  list: async (): Promise<HostListResponse> => {
    const { data } = await api.get<HostListResponse>('/hosts');
    return data;
  },
};

export const TopologyAPI = {
  get: async (): Promise<TopologyResponse> => {
    const { data } = await api.get<TopologyResponse>('/topology');
    return data;
  },
};

export const CommunicationsAPI = {
  /** Legacy flat list across every project. Deprecated — use ProjectsAPI.communications.list. */
  list: async (): Promise<CommunicationListResponse> => {
    const { data } = await api.get<CommunicationListResponse>('/communications');
    return data;
  },
};

export const ProjectsAPI = {
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
  start: async (projectId: string): Promise<ProjectDetail> => {
    const { data } = await api.post<ProjectDetail>(`/projects/${projectId}/start`);
    return data;
  },
  stop: async (projectId: string): Promise<ProjectDetail> => {
    const { data } = await api.post<ProjectDetail>(`/projects/${projectId}/stop`);
    return data;
  },
  delete: async (projectId: string): Promise<void> => {
    await api.delete(`/projects/${projectId}`);
  },
  updateNodePosition: async (
    projectId: string,
    hostId: string,
    body: NodePosition,
  ): Promise<ProjectHost> => {
    const { data } = await api.patch<ProjectHost>(
      `/projects/${projectId}/nodes/${hostId}`,
      body,
    );
    return data;
  },
  // ─── per-project hosts (Phase 05) ──────────────────────────────────────
  hosts: {
    list: async (projectId: string): Promise<ProjectHostListResponse> => {
      const { data } = await api.get<ProjectHostListResponse>(
        `/projects/${projectId}/hosts`,
      );
      return data;
    },
    get: async (projectId: string, hostId: string): Promise<ProjectHost> => {
      const { data } = await api.get<ProjectHost>(
        `/projects/${projectId}/hosts/${hostId}`,
      );
      return data;
    },
    metricsText: async (
      projectId: string,
      hostId: string,
    ): Promise<string> => {
      // We can't use api.get<…>() because the response body is plain text
      // (Prometheus format), not JSON. Issue a raw request via Axios and
      // return the text body.
      const { data } = await api.get<string>(
        `/projects/${projectId}/hosts/${hostId}/metrics`,
        { responseType: 'text', transformResponse: [(d) => d] },
      );
      return data;
    },
  },
  // ─── per-project communications (Phase 06) ────────────────────────────
  communications: {
    list: async (
      projectId: string,
      limit = 100,
    ): Promise<CommunicationListResponse> => {
      const { data } = await api.get<CommunicationListResponse>(
        `/projects/${projectId}/communications`,
        { params: { limit } },
      );
      return data;
    },
    get: async (
      projectId: string,
      commId: string,
    ): Promise<Communication> => {
      const { data } = await api.get<Communication>(
        `/projects/${projectId}/communications/${commId}`,
      );
      return data;
    },
    trigger: async (
      projectId: string,
      body: CommunicationCreate,
    ): Promise<Communication> => {
      const { data } = await api.post<Communication>(
        `/projects/${projectId}/communications`,
        body,
      );
      return data;
    },
  },
};

export default api;