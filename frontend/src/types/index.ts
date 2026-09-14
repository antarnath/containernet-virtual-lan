// TypeScript types mirroring the FastAPI backend's Pydantic schemas.
// Keeping these in sync with the backend prevents silent type drift.

export type HostStatus = 'online' | 'offline' | 'unknown';

export interface Host {
  id: string;
  host_id: string;
  hostname: string;
  ip_address: string;
  status: HostStatus;
  last_seen: string | null;
  created_at: string;
}

export interface HostListResponse {
  hosts: Host[];
  total: number;
  online: number;
  offline: number;
}

export interface TopologyNode {
  id: string;
  label: string;
  ip: string;
  status: HostStatus;
}

export interface TopologyEdge {
  source: string;
  target: string;
}

export interface TopologyResponse {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

// ─── Communications ────────────────────────────────────────
export type CommStatus = 'pending' | 'delivered' | 'failed';

export interface Communication {
  id: string;
  project_id: string | null;
  source_host_id: string;
  dest_host_id: string;
  protocol: string;
  payload: string;
  data_size: number;
  latency_ms: number | null;
  status: CommStatus;
  timestamp: string;
}

export interface CommunicationCreate {
  source_host_id: string;
  destination_host_id: string;
  protocol: string;
  payload: string;
  project_id?: string | null;
}

export interface CommunicationListResponse {
  communications: Communication[];
  total: number;
}

// ─── Projects (Phase 02-04) ────────────────────────────────────

export type TopologyType = 'mesh' | 'star' | 'ring' | 'bus' | 'tree';

export type ProjectStatus =
  | 'draft'
  | 'running'
  | 'partial'
  | 'stopped'
  | 'error';

export type ProjectHostStatus = 'online' | 'offline' | 'unknown';

export interface ProjectHost {
  id: string;
  host_id: string;
  hostname: string;
  ip_address: string;
  container_id: string | null;
  position_x: number;
  position_y: number;
  status: ProjectHostStatus;
  last_seen: string | null;
  created_at: string;
}

export interface ProjectEdge {
  id: string;
  source_host_id: string;
  dest_host_id: string;
}

export interface Project {
  id: string;
  name: string;
  topology_type: TopologyType;
  host_count: number;
  subnet: string;
  gateway: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends Project {
  hosts: ProjectHost[];
  edges: ProjectEdge[];
}

export interface ProjectListResponse {
  projects: Project[];
  total: number;
}

export interface ProjectCreate {
  name: string;
  topology_type: TopologyType;
  host_count: number;
  subnet: string;
}

export interface NodePosition {
  position_x: number;
  position_y: number;
}

// ─── Per-project hosts (Phase 05) ───────────────────────────────────────

export interface ProjectHostListResponse {
  hosts: ProjectHost[];
  total: number;
  online: number;
  offline: number;
}

/** Parsed snapshot of a host's Prometheus /metrics endpoint. */
export interface HostMetricsSnapshot {
  cpu_percent: number | null;
  memory_percent: number | null;
  network_rx_bytes: number | null;
  network_tx_bytes: number | null;
  uptime_seconds: number | null;
  fetched_at: number;
  error?: string;
}

// ─── Per-host messages (Phase 08) ───────────────────────────────────────

export type MessageDirection = 'in' | 'out';

export interface MessageRecord {
  id: number;
  project_id: string;
  host_id: string;
  direction: MessageDirection;
  peer_host_id: string | null;
  comm_id: string | null;
  payload: string;
  protocol: string;
  timestamp: string;
}

export interface MessageListResponse {
  messages: MessageRecord[];
  total: number;
}

// ─── Platform stats (Phase 09) ────────────────────────────────────────────

export interface StatsSummary {
  projects: {
    total: number;
    running: number;
    stopped: number;
    other: number;
  };
  hosts: {
    total: number;
    online: number;
    offline: number;
  };
  recent_communications: Array<{
    id: string;
    project_id: string | null;
    source_host_id: string;
    dest_host_id: string;
    protocol: string;
    payload: string;
    status: string;
    latency_ms: number | null;
    timestamp: string | null;
  }>;
}
