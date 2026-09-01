// Global store for hosts and topology. Components subscribe to slices of
// this store instead of fetching on their own — keeps state consistent.

import { create } from 'zustand';
import { HostsAPI, TopologyAPI } from '../api/client';
import type { HostListResponse, TopologyResponse } from '../types';

interface HostState {
  hosts: HostListResponse | null;
  topology: TopologyResponse | null;
  error: string | null;
  loading: boolean;

  fetchHosts: () => Promise<void>;
  fetchTopology: () => Promise<void>;
}

export const useHostStore = create<HostState>((set) => ({
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
}));
