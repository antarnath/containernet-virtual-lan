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
  /** IPv4 CIDR. Optional when assign_subnet_automatically=true. */
  subnet?: string;
  /** When true, omit subnet / ignore the field and let the backend pick. */
  assign_subnet_automatically?: boolean;
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

// ─── Platform stats (dashboard overview) ───────────────────────────────────

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

// ─── Packets (M2-07 dashboard) ──────────────────────────────────────────────

export interface PacketL2Frame {
  src_mac: string;
  dst_mac: string;
  ethertype: number;
  ethertype_name: string;
  is_broadcast: boolean;
  crc_ok?: boolean;
  linktype?: number;
  _error?: string;
}

export interface PacketL3IPv4 {
  version: number;
  ihl: number;
  dscp: number;
  ecn: number;
  total_length: number;
  identification: string;
  flags: string;
  fragment_offset: number;
  ttl: number;
  protocol: number;
  protocol_name: string;
  checksum: string;
  checksum_ok: boolean;
  src_ip: string;
  dst_ip: string;
}

export interface PacketL4TCP {
  src_port: number;
  dst_port: number;
  seq: number;
  ack: number;
  data_offset: number;
  flags: string[];
  flags_bits: string;
  window: number;
  checksum: string;
  checksum_ok: boolean;
  urgent: number;
  options: Array<Record<string, unknown>>;
  payload_len: number;
}

export interface PacketL7HTTP {
  is_request?: boolean;
  is_response?: boolean;
  method?: string;
  path?: string;
  version?: string;
  status_code?: number;
  status_text?: string;
  headers: Record<string, string>;
  body_decoded: string;
  body_truncated?: boolean;
}

export interface PacketEvent {
  id: number;
  ts: string;
  ts_ns: number;
  iface: string;
  len: number;
  l2: PacketL2Frame;
  l3: PacketL3IPv4 | null;
  l4: PacketL4TCP | null;
  l7: PacketL7HTTP | null;
  summary: string;
  sections: Array<Record<string, unknown>>;
}

export interface PacketListResponse {
  events: PacketEvent[];
  since: number;
  limit: number;
}
