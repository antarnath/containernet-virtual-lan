// Per-project host store.
//
// Phase 05: hosts are keyed by `project_id` so two projects in the same
// browser tab never collide. The legacy flat `hosts` field is kept as a
// derived fallback for the original Dashboard / HostCard components — it
// reflects the most-recently-fetched project's hosts.
//
// WebSocket `host_status_change` events are filtered by `currentProject`
// (set elsewhere in the app) so we only mutate the active project's row.

import { create } from 'zustand';
import { HostsAPI, ProjectsAPI, TopologyAPI } from '../api/client';
import type {
  HostListResponse,
  HostStatus,
  ProjectHostListResponse,
  TopologyResponse,
} from '../types';

interface HostState {
  // Legacy global view — populated from the original /api/hosts endpoint.
  // Used by the Dashboard and any legacy component.
  hosts: HostListResponse | null;
  topology: TopologyResponse | null;

  // Phase 05 — keyed by project_id so two coexisting projects don't
  // overwrite each other.
  byProject: Record<string, ProjectHostListResponse>;

  // Per-project metrics snapshots: projectId -> hostId -> parsed metrics.
  metrics: Record<string, Record<string, import('../types').HostMetricsSnapshot>>;

  // Global error / loading state (re-used for whichever fetch is running).
  error: string | null;
  loading: boolean;

  // ─── actions ─────────────────────────────────────────────────────────

  /** Legacy flat fetch — powers the original /hosts page. */
  fetchHosts: () => Promise<void>;
  fetchTopology: () => Promise<void>;

  /** Per-project fetch — used by /projects/:id/hosts and the new HostsPage. */
  fetchProjectHosts: (projectId: string) => Promise<void>;

  /** Fetch metrics for a single host, parse Prometheus text, store snapshot. */
  fetchHostMetrics: (projectId: string, hostId: string) => Promise<void>;
  fetchAllProjectMetrics: (projectId: string) => Promise<void>;

  /** Update host status in both the per-project entry and the legacy view. */
  applyHostStatusChange: (
    hostId: string,
    status: HostStatus,
    projectId?: string,
  ) => void;

  /** Replace a project's per-project host list with a fresh fetch. */
  refreshProjectHosts: (projectId: string) => Promise<void>;

  /** Drop a project's entry (called on project delete). */
  dropProject: (projectId: string) => void;
}

export const useHostStore = create<HostState>((set, get) => ({
  hosts: null,
  topology: null,
  byProject: {},
  metrics: {},
  error: null,
  loading: false,

  fetchHosts: async () => {
    set({ loading: true });
    try {
      const hosts = await HostsAPI.list();
      set({ hosts, error: null, loading: false });
    } catch (e) {
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

  fetchProjectHosts: async (projectId) => {
    try {
      const list = await ProjectsAPI.hosts.list(projectId);
      set((s) => ({
        byProject: { ...s.byProject, [projectId]: list },
        // Keep the legacy `hosts` view in sync so any non-Phase-05
        // component still renders something useful.
        hosts: {
          hosts: list.hosts.map((h) => ({
            id: h.id,
            host_id: h.host_id,
            hostname: h.hostname,
            ip_address: h.ip_address,
            status: h.status,
            last_seen: h.last_seen,
            created_at: h.created_at,
          })),
          total: list.total,
          online: list.online,
          offline: list.offline,
        },
        error: null,
      }));
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  refreshProjectHosts: async (projectId) => {
    await get().fetchProjectHosts(projectId);
  },

  fetchHostMetrics: async (projectId, hostId) => {
    try {
      const text = await ProjectsAPI.hosts.metricsText(projectId, hostId);
      const snap = parsePrometheusText(text);
      set((s) => {
        const prev = s.metrics[projectId] ?? {};
        return {
          metrics: { ...s.metrics, [projectId]: { ...prev, [hostId]: snap } },
        };
      });
    } catch (e) {
      const errSnap: import('../types').HostMetricsSnapshot = {
        cpu_percent: null,
        memory_percent: null,
        network_rx_bytes: null,
        network_tx_bytes: null,
        uptime_seconds: null,
        fetched_at: Date.now(),
        error: (e as Error).message,
      };
      set((s) => {
        const prev = s.metrics[projectId] ?? {};
        return {
          metrics: { ...s.metrics, [projectId]: { ...prev, [hostId]: errSnap } },
        };
      });
    }
  },

  fetchAllProjectMetrics: async (projectId) => {
    const list = get().byProject[projectId];
    if (!list) return;
    await Promise.all(
      list.hosts.map((h) => get().fetchHostMetrics(projectId, h.host_id)),
    );
  },

  applyHostStatusChange: (hostId, status, projectId) => {
    // 1. Per-project entry, if we know which project.
    if (projectId) {
      const proj = get().byProject[projectId];
      if (proj) {
        const updated = proj.hosts.map((h) =>
          h.host_id === hostId ? { ...h, status } : h,
        );
        const next: ProjectHostListResponse = {
          hosts: updated,
          total: updated.length,
          online: updated.filter((h) => h.status === 'online').length,
          offline: updated.filter((h) => h.status === 'offline').length,
        };
        set((s) => ({
          byProject: { ...s.byProject, [projectId]: next },
        }));
      }
    }
    // 2. Legacy `hosts` view — patch if we know about this host.
    const current = get().hosts;
    if (current) {
      const updated = current.hosts.map((h) =>
        h.host_id === hostId ? { ...h, status } : h,
      );
      set({
        hosts: {
          hosts: updated,
          total: updated.length,
          online: updated.filter((h) => h.status === 'online').length,
          offline: updated.filter((h) => h.status === 'offline').length,
        },
      });
    }
    // 3. Topology nodes (legacy global view).
    const topo = get().topology;
    if (topo) {
      set({
        topology: {
          nodes: topo.nodes.map((n) => (n.id === hostId ? { ...n, status } : n)),
          edges: topo.edges,
        },
      });
    }
  },

  dropProject: (projectId) => {
    set((s) => {
      const { [projectId]: _, ...rest } = s.byProject;
      const { [projectId]: __, ...restMetrics } = s.metrics;
      return { byProject: rest, metrics: restMetrics };
    });
  },
}));

// ─── helpers ───────────────────────────────────────────────────────────────

/**
 * Parse a Prometheus text-exposition response into the subset of metrics
 * the HostCard cares about. Anything not present stays null.
 *
 * Example input line:
 *   host_cpu_usage_percent 12.5
 *   host_memory_usage_percent 33.0
 *   host_network_rx_bytes_total 123456
 *   host_network_tx_bytes_total 7890
 *   host_uptime_seconds 3600
 */
function parsePrometheusText(text: string): import('../types').HostMetricsSnapshot {
  const out: import('../types').HostMetricsSnapshot = {
    cpu_percent: null,
    memory_percent: null,
    network_rx_bytes: null,
    network_tx_bytes: null,
    uptime_seconds: null,
    fetched_at: Date.now(),
  };
  if (!text) return out;
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const spaceIdx = line.lastIndexOf(' ');
    if (spaceIdx < 0) continue;
    const metricPart = line.slice(0, spaceIdx);
    const valuePart = line.slice(spaceIdx + 1);
    // Drop labels: only handle the unlabeled gauge variant we emit.
    const metricName = metricPart.split('{')[0].trim();
    const v = Number(valuePart);
    if (Number.isNaN(v)) continue;
    switch (metricName) {
      case 'host_cpu_usage_percent':
        out.cpu_percent = v;
        break;
      case 'host_memory_usage_percent':
        out.memory_percent = v;
        break;
      case 'host_network_rx_bytes_total':
        out.network_rx_bytes = v;
        break;
      case 'host_network_tx_bytes_total':
        out.network_tx_bytes = v;
        break;
      case 'host_uptime_seconds':
        out.uptime_seconds = v;
        break;
      default:
        break;
    }
  }
  return out;
}
