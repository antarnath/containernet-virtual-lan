// Thin Axios wrapper. The base URL is "/api" — both Vite (dev) and
// Nginx (prod) forward /api/* to the backend container.

import axios from 'axios';
import type { HostListResponse, TopologyResponse } from '../types';

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

export default api;
