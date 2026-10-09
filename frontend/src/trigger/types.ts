// Types for the trigger & message console (M4 phase 05).

export type Protocol = 'HTTP' | 'TCP' | 'ICMP';

export interface Hop {
  node_id: string;
  node_name: string;
  node_kind: string;
  iface_name: string | null;
  iface_ip: string | null;
  link_id: string | null;
  link_subnet: string | null;
}

export interface RouteResponse {
  project_id: string;
  src_node_id: string;
  dst_ip: string;
  hops: Hop[];
  /** Set to 'routing_loop' when the topology contains a loop. The
   * 200 response then includes `visited`; otherwise the resolver
   * raised RouteError → 422 with `detail`. */
  error?: string;
  visited?: string[];
  /** Error detail for the 422 path (unreachable). */
  detail?: RouteError;
}

export interface RouteError {
  error: string;
  src: string;
  dst: string;
}

export interface SendResult {
  comm_id: string;
  status: 'delivered' | 'failed' | 'unreachable';
  delivered_at: string | null;
  hops_crossed: string[];
  error: string | null;
}

export interface MessageRow {
  id: string;
  project_id: string;
  src_node_id: string;
  dst_node_id: string | null;
  dst_ip: string;
  protocol: string;
  payload: string;
  status: string;
  hops_count: number;
  created_at: string | null;
  delivered_at: string | null;
}

export interface MessagesResponse {
  project_id: string;
  node_id: string | null;
  messages: MessageRow[];
}
