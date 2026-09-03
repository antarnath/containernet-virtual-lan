// Global store for hosts and topology. Components subscribe to slices of
// this store instead of fetching on their own — keeps state consistent.

import { create } from 'zustand';
import { HostsAPI, TopologyAPI } from '../api/client';
import type { HostListResponse, HostStatus, TopologyResponse } from '../types';

interface HostState {
  hosts: HostListResponse | null;
  topology: TopologyResponse | null;
  error: string | null;
  loading: boolean;

  fetchHosts: () => Promise<void>;
  fetchTopology: () => Promise<void>;
  applyHostStatusChange: (hostId: string, status: HostStatus) => void;
}

export const useHostStore = create<HostState>((set, get) => ({
  hosts: null,
  topology: null,
  error: null,
  loading: false,

  fetchHosts: async () => {
    set({ loading: true });
    try {
      const hosts = await HostsAPI.list();
      set({ hosts, error: null, loading: false });
    } catch (e) {
      // Keep stale data visible; just record the error.
      set({ error: (e as Error).message, loading: false });
    }
  },

  fetchTopology: async () => {
    try {
      const topology = await TopologyAPI.get();
      set({ topology, error: null });
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  applyHostStatusChange: (hostId, status) => {
    const current = get().hosts;
    if (!current) return;
    const updated = current.hosts.map((h) =>
      h.host_id === hostId ? { ...h, status } : h,
    );
    const online = updated.filter((h) => h.status === 'online').length;
    const offline = updated.filter((h) => h.status === 'offline').length;
    set({
      hosts: {
        hosts: updated,
        total: updated.length,
        online,
        offline,
      },
    });
    // Also patch topology nodes so the topology view updates in real time.
    const topo = get().topology;
    if (topo) {
      set({
        topology: {
          nodes: topo.nodes.map((n) =>
            n.id === hostId ? { ...n, status } : n,
          ),
          edges: topo.edges,
        },
      });
    }
  },
}));