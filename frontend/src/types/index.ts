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
