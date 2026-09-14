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
  ProjectListResponse,
  TopologyResponse,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

export const HostsAPI = {
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
  list: async (): Promise<CommunicationListResponse> => {
    const { data } = await api.get<CommunicationListResponse>('/communications');
    return data;
  },
  trigger: async (body: CommunicationCreate): Promise<Communication> => {
    const { data } = await api.post<Communication>('/communications', body);
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
};

export default api;