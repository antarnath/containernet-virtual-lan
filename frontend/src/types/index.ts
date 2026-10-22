// TypeScript types mirroring the FastAPI backend's Pydantic schemas.
// Keeping these in sync with the backend prevents silent type drift.
//
// M4 — the 5-primitive model:
//   Project, ProjectNode (5 kinds), ProjectInterface, ProjectLink, ProjectCapture

// ─── 5 node kinds + the 5 attack modes ──────────────────────────────────
export type NodeKind = 'host' | 'switch' | 'router' | 'server' | 'attacker';

export type AttackMode =
  | 'unknown_host'
  | 'duplicate_ip'
  | 'arp_spoof'
  | 'tcp_flood'
  | 'http_flood';

export type ProjectStatus =
  | 'draft'
  | 'starting'
  | 'running'
  | 'partial'
  | 'stopped'
  | 'error';

export type ContainerStatus = 'idle' | 'starting' | 'running' | 'stopped' | 'error';

// ─── Project ────────────────────────────────────────────────────────────
export interface ProjectInterface {
  id: string;
  node_id: string;
  name: string;
  ip_address: string | null;
  subnet_mask: string | null;
  mac_address: string | null;
  // M5-01 / 1.2 — DHCP server config (router interfaces only).
  dhcp_enabled: boolean;
  dhcp_pool_start: string | null;
  dhcp_pool_end: string | null;
  dhcp_lease_time: number;
  dhcp_dns: string | null;
  // M5-01 / 1.3 — DHCP relay config. Mutually exclusive with
  // dhcp_enabled: an interface is either a server or a relay.
  dhcp_relay_enabled: boolean;
  dhcp_relay_server: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectNode {
  id: string;
  project_id: string;
  name: string;
  kind: NodeKind;
  canvas_x: number;
  canvas_y: number;
  attack_mode: AttackMode | null;
  container_id: string | null;
  container_status: ContainerStatus;
  created_at: string;
  updated_at: string;
  interfaces: ProjectInterface[];
}

export interface ProjectCapture {
  id: string;
  link_id: string;
  container_id: string | null;
  status: ContainerStatus;
  last_packet_at: string | null;
  packet_count: number;
}

export interface ProjectLink {
  id: string;
  project_id: string;
  iface_a_id: string;
  iface_b_id: string;
  subnet_cidr: string | null;
  subnet_color_index: number;
  docker_bridge_name: string | null;
  created_at: string;
  capture: ProjectCapture | null;
}

export interface Project {
  id: string;
  name: string;
  status: ProjectStatus;
  viewport_x: number;
  viewport_y: number;
  viewport_zoom: number;
  node_count: number;
  link_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends Project {
  nodes: ProjectNode[];
  links: ProjectLink[];
}

export interface ProjectListResponse {
  projects: Project[];
  total: number;
}

export interface ProjectCreate {
  name: string;
}

export interface ProjectUpdate {
  name?: string;
  viewport_x?: number;
  viewport_y?: number;
  viewport_zoom?: number;
}

// ─── Node CRUD payloads ─────────────────────────────────────────────────
export interface ProjectNodeCreate {
  kind: NodeKind;
  canvas_x?: number;
  canvas_y?: number;
  name?: string;
  attack_mode?: AttackMode | null;
}

export interface ProjectNodeUpdate {
  name?: string;
  canvas_x?: number;
  canvas_y?: number;
  attack_mode?: AttackMode | null;
}

// ─── Interface CRUD payloads ────────────────────────────────────────────
export interface ProjectInterfaceCreate {
  name: string;
  ip_address?: string | null;
  subnet_mask?: string | null;
}

export interface ProjectInterfaceUpdate {
  name?: string;
  ip_address?: string | null;
  subnet_mask?: string | null;
}

// ─── Link CRUD payloads ─────────────────────────────────────────────────
export interface ProjectLinkCreate {
  iface_a_id: string;
  iface_b_id: string;
}

// ─── DHCP (M5-01 / 1.2 + 1.3 + 1.4) ─────────────────────────────────────

/** Body for PUT /api/projects/<pid>/nodes/<nid>/interfaces/<iid>/dhcp */
export interface InterfaceDHCPConfig {
  enabled: boolean;
  pool_start?: string | null;
  pool_end?: string | null;
  lease_time?: number;
  dns?: string | null;
}

/** Body for PUT .../dhcp/relay */
export interface InterfaceDHCPRelayConfig {
  enabled: boolean;
  server_ip?: string | null;
}

/** One row from the router agent's /var/lib/misc/dnsmasq.leases. */
export interface DHCPLease {
  mac: string;
  ip: string;
  hostname: string;
  /** Unix epoch seconds. 0 or a past value means expired. */
  expires_at: number;
}

/** Response of GET /api/projects/<pid>/nodes/<nid>/dhcp/leases */
export interface DHCPLeasesResponse {
  node_id: string;
  /** Never null — an empty array means no leases yet. */
  leases: DHCPLease[];
  /** Iface names (eth0, eth1…) currently running a DHCP server. */
  server_ifaces: string[];
  /** Iface names currently relaying to an upstream server. */
  relay_ifaces: string[];
  /** Non-null when the leases couldn't be fetched. */
  error: string | null;
}

/** A MAC → fixed-IP binding (M5-01 / 1.4). */
export interface DHCPReservation {
  id: string;
  iface_id: string;
  mac_address: string;
  ip_address: string;
  hostname: string | null;
  created_at: string;
  updated_at: string;
}

/** One entry in a PUT .../dhcp/reservations body. */
export interface DHCPReservationInput {
  mac_address: string;
  ip_address: string;
  hostname?: string | null;
}

export interface DHCPReservationsResponse {
  reservations: DHCPReservation[];
}

/** One duplicate-IP conflict. `interface_ids` / `node_names` are
 *  parallel arrays — index i of each belongs to the same interface. */
export interface DuplicateIPConflict {
  ip: string;
  interface_ids: string[];
  node_names: string[];
}
