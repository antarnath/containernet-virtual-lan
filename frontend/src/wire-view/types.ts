// Wire-view types — the M4 phase 04 wire view.
//
// The wire view streams one PacketEvent per frame over Server-Sent
// Events. The same shape is also written to the project's
// WebSocket channel so the canvas can animate a dot along the
// wire each time a packet crosses (canvas feature, not the wire
// view itself — the wire view just renders the live list).

import type { NodeKind } from '../types';

export type PacketProtocol = 'tcp' | 'udp' | 'icmp' | 'arp' | 'http' | 'other';

/** The kind of the node that originated the packet. Empty when
 *  the source MAC isn't one of the project's nodes (e.g. external
 *  mDNS from the docker bridge). */
export type PacketSrcKind = NodeKind | '';

export interface PacketEvent {
  id: number;
  ts: string;
  ts_ns: number;
  link_id: string;
  protocol: PacketProtocol;
  src_node_kind: PacketSrcKind;
  src_mac: string;
  dst_mac: string;
  src_ip: string;
  dst_ip: string;
  src_port: number | null;
  dst_port: number | null;
  length: number;
  summary: string;
}

export type WireViewTab = 'raw' | 'conversations' | 'attackers';

export interface PacketFilter {
  /** Set of protocols the user wants to see. Empty = all. */
  protocols: Set<PacketProtocol>;
  /** When true, only show packets from attacker-sourced nodes. */
  attackOnly: boolean;
}
