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
}

export interface CommunicationListResponse {
  communications: Communication[];
  total: number;
}
