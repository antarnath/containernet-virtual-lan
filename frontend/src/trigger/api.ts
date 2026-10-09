// API client for the trigger & message console (M4 phase 05).
//
// All endpoints live under /api/projects/{id}/...; we add three
// new ones here:
//   GET  /route?src=&dst=     — resolve a route
//   POST /communications      — send a message
//   GET  /messages?node_id=&  — list message history

import axios from 'axios';
import type {
  MessagesResponse,
  RouteError,
  RouteResponse,
  SendResult,
} from './types';

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

export const TriggerAPI = {
  /** Resolve the route from `srcNodeId` to `dstIp`. The 422
   * response carries a RouteError in `response.data.detail`;
   * the 200 (with `error: 'routing_loop'`) is also possible. */
  resolveRoute: async (
    projectId: string,
    srcNodeId: string,
    dstIp: string,
  ): Promise<RouteResponse> => {
    try {
      const { data } = await api.get<RouteResponse>(
        `/projects/${projectId}/route`,
        { params: { src: srcNodeId, dst: dstIp } },
      );
      return data;
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 422) {
        const detail = (err.response.data?.detail || {}) as RouteError;
        return {
          project_id: projectId,
          src_node_id: srcNodeId,
          dst_ip: dstIp,
          hops: [],
          error: 'unreachable',
          detail,
        };
      }
      throw err;
    }
  },

  /** Send a message. Returns the SendResult from the backend. */
  send: async (
    projectId: string,
    body: {
      src_node_id: string;
      dst_ip: string;
      protocol: string;
      payload: string;
      dst_node_id?: string | null;
    },
  ): Promise<SendResult> => {
    const { data } = await api.post<SendResult>(
      `/projects/${projectId}/communications`,
      body,
    );
    return data;
  },

  /** Get message history. Optionally filtered to messages
   * touching `nodeId`. */
  listMessages: async (
    projectId: string,
    nodeId: string | null = null,
    limit = 50,
  ): Promise<MessagesResponse> => {
    const { data } = await api.get<MessagesResponse>(
      `/projects/${projectId}/messages`,
      {
        params: {
          node_id: nodeId ?? undefined,
          limit,
        },
      },
    );
    return data;
  },
};
