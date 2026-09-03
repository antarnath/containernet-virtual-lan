// Thin Axios wrapper. The base URL is "/api" — both Vite (dev) and
// Nginx (prod) forward /api/* to the backend container.

import axios from 'axios';
import type {
  Communication,
  CommunicationCreate,
  CommunicationListResponse,
  HostListResponse,
  TopologyResponse,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 5000,
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

export default api;