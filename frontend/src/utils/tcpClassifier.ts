// tcpClassifier — pure functions that turn a flat PacketEvent[] into
// structured TCP/IP conversations + steps for the M2-07 dashboard.
//
// The pipeline:
//   events  →  filter to "app traffic" (port 8080 / involved ARP)
//          →  group into conversations by 4-tuple
//          →  classify each packet as a Step
//          →  fold pure ACKs into their parent step (no orphan rows)
//
// All functions are pure; no React, no useState. Easy to unit-test.

import type { PacketEvent } from '../types';

/** The port the host-agent's aiohttp server binds to. */
export const APP_PORT = 8080;

/** A TCP/IP step kind — what role this packet plays in the conversation. */
export type StepKind =
  | 'address_resolution' // ARP for one of the conversation's endpoints
  | 'handshake' // SYN + SYN,ACK + ACK (the 3-way handshake)
  | 'http_request' // PSH,ACK from client→server carrying the request
  | 'http_response' // PSH,ACK from server→client carrying the response
  | 'data_ack' // pure ACK inside data transfer (collapsed into prior step)
  | 'close'; // FIN,ACK handshake to tear down

/** Metadata describing one step in a conversation. */
export interface Step {
  kind: StepKind;
  /** The step number within its conversation (1-indexed, displayed as ①). */
  index: number;
  /** Short label for the step header. */
  title: string;
  /** Packets that belong to this step, oldest first. */
  packets: PacketEvent[];
  /** Number of microseconds from first to last packet (or single packet RTT). */
  duration_us: number;
}

/** One detected TCP/IP conversation between two hosts. */
export interface Conversation {
  /** Stable id for React keying. */
  id: string;
  /** Canonical 4-tuple (smaller ip first; for the same ip, smaller port first). */
  loIp: string;
  loPort: number;
  hiIp: string;
  hiPort: number;
  /** "Client" = the side that opened the connection (sent first SYN). */
  clientIp: string;
  clientPort: number;
  serverIp: string;
  serverPort: number;
  /** When the conversation started (first packet ts). */
  startedAt: string;
  /** ms from first packet to last packet (or 0 for single-packet). */
  duration_ms: number;
  /** Ordered list of steps. */
  steps: Step[];
  /** Aggregate stats — used by the conversation footer. */
  stats: ConversationStats;
}

export interface ConversationStats {
  totalPackets: number;
  appBytesSent: number;
  appBytesReceived: number;
  ipChecksumOk: number;
  ipChecksumTotal: number;
  tcpChecksumOk: number;
  tcpChecksumTotal: number;
}

// ─── 1. Filtering ─────────────────────────────────────────────────────────

/**
 * Is this packet part of the project's application traffic?
 * True for: TCP/UDP packets involving port 8080, and ARP packets whose
 * question/answer involves an IP we'll see in the conversation.
 *
 * Note: we don't pre-filter ARPs here — the caller will decide which ARPs
 * to attach per-conversation using attachArp().
 */
export function isAppTraffic(e: PacketEvent): boolean {
  if (!e.l4) return false;
  const sp = e.l4.src_port;
  const dp = e.l4.dst_port;
  return sp === APP_PORT || dp === APP_PORT;
}

/** Is this an ARP packet? */
function isArp(e: PacketEvent): boolean {
  return e.l2.ethertype_name === 'ARP';
}

// ─── 2. Grouping into conversations ───────────────────────────────────────

/**
 * Group app-traffic packets into conversations by 4-tuple. Returns one
 * Conversation per unique 4-tuple, each containing ALL its packets (no
 * step classification yet — call classifyConversation() next).
 */
export function groupConversations(events: PacketEvent[]): Conversation[] {
  const byTuple = new Map<string, PacketEvent[]>();
  for (const e of events) {
    if (!isAppTraffic(e) && !isArp(e)) continue;
    if (!e.l3 && !isArp(e)) continue;
    const key = conversationKey(e);
    if (!key) continue;
    const list = byTuple.get(key) ?? [];
    list.push(e);
    byTuple.set(key, list);
  }

  const out: Conversation[] = [];
  for (const [, packets] of byTuple) {
    if (packets.length === 0) continue;
    // Only emit a conversation if it actually has app traffic
    // (ARP-only groups are noise — skip them).
    const hasApp = packets.some(isAppTraffic);
    if (!hasApp) continue;

    // Sort packets by id ascending (oldest first). The shim emits
    // monotonically increasing ids within a capture, so this is also
    // chronological.
    packets.sort((a, b) => a.id - b.id);

    out.push(buildConversation(packets));
  }
  // Newest conversation first.
  out.sort((a, b) => (a.startedAt < b.startedAt ? 1 : -1));
  return out;
}

/** Stable string key for the canonical 4-tuple of a packet. */
function conversationKey(e: PacketEvent): string | null {
  // ARP: tag by the two IPs it mentions (request + target).
  if (isArp(e)) {
    const ips = arpIps(e);
    if (!ips) return null;
    const [a, b] = ips.sort();
    return `arp:${a}__${b}`;
  }
  if (!e.l3 || !e.l4) return null;
  const a = `${e.l3.src_ip}:${e.l4.src_port}`;
  const b = `${e.l3.dst_ip}:${e.l4.dst_port}`;
  const [lo, hi] = a < b ? [a, b] : [b, a];
  return `tcp:${lo}__${hi}`;
}

/** Pull the two IPs from an ARP packet's summary text. The shim writes
 * summaries like:
 *   "ARP 10.30.0.4 → *  \"who has 10.30.0.5? tell aa:..04\""
 *   "ARP * → 10.30.0.4 \"10.30.0.5 is at aa:..05\""
 * We extract the IPs by regex from the summary. */
function arpIps(e: PacketEvent): [string, string] | null {
  const s = e.summary;
  const ips = Array.from(s.matchAll(/\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/g)).map(
    (m) => m[1],
  );
  if (ips.length === 0) return null;
  // For "who has X? tell Y", X is target, Y is sender → both ips matter.
  // For "X is at MAC", X is sender → we still need a peer from context.
  // In our capture the shim always includes both sender and target in
  // the text, so de-duping and taking the first two is sufficient.
  const seen = new Set<string>();
  const out: string[] = [];
  for (const ip of ips) {
    if (!seen.has(ip)) {
      seen.add(ip);
      out.push(ip);
    }
    if (out.length === 2) break;
  }
  if (out.length < 2) return null;
  return [out[0], out[1]];
}

// ─── 3. Classify one conversation's packets into steps ───────────────────

function buildConversation(packets: PacketEvent[]): Conversation {
  // Determine client/server. The client is the IP that sent the first SYN
  // (or, if no SYN, the IP that sent the first packet with payload > 0).
  const firstSyn = packets.find((p) => p.l4?.flags.includes('SYN'));
  let clientIp: string;
  let serverIp: string;
  if (firstSyn && firstSyn.l3) {
    clientIp = firstSyn.l3.src_ip;
    serverIp = firstSyn.l3.dst_ip;
  } else {
    // Fallback: use 4-tuple endian ordering to guess server side.
    const first = packets.find((p) => p.l4)?.l4!;
    const firstL3 = packets.find((p) => p.l3)?.l3!;
    if (first.dst_port === APP_PORT) {
      clientIp = firstL3.src_ip;
      serverIp = firstL3.dst_ip;
    } else if (first.src_port === APP_PORT) {
      clientIp = firstL3.dst_ip;
      serverIp = firstL3.src_ip;
    } else {
      clientIp = firstL3.src_ip;
      serverIp = firstL3.dst_ip;
    }
  }

  // Pull canonical lo/hi ordering for the 4-tuple (purely for display).
  const first4 = packets.find((p) => p.l4 && p.l3);
  let loIp = clientIp;
  let loPort = 0;
  let hiIp = serverIp;
  let hiPort = APP_PORT;
  if (first4 && first4.l4 && first4.l3) {
    const sp = first4.l4.src_port;
    const dp = first4.l4.dst_port;
    const sip = first4.l3.src_ip;
    const dip = first4.l3.dst_ip;
    if (sip < dip || (sip === dip && sp < dp)) {
      loIp = sip; loPort = sp; hiIp = dip; hiPort = dp;
    } else {
      loIp = dip; loPort = dp; hiIp = sip; hiPort = sp;
    }
  }

  const clientPort =
    packets.find((p) => p.l3?.src_ip === clientIp && p.l4)?.l4?.src_port ?? 0;

  const steps = classifySteps(packets, clientIp, serverIp);
  const stats = computeStats(packets);

  const first = packets[0];
  const last = packets[packets.length - 1];
  const duration_ms =
    first && last && first.ts_ns && last.ts_ns
      ? Math.max(0, (last.ts_ns - first.ts_ns) / 1_000_000)
      : 0;

  return {
    id: `${loIp}:${loPort}__${hiIp}:${hiPort}__${first?.id ?? 0}`,
    loIp,
    loPort,
    hiIp,
    hiPort,
    clientIp,
    clientPort,
    serverIp,
    serverPort: APP_PORT,
    startedAt: first?.ts ?? '',
    duration_ms,
    steps,
    stats,
  };
}

/**
 * Walk packets in order, labeling each as one of:
 *   address_resolution | handshake | http_request | http_response |
 *   data_ack | close | rst
 * Pure ACKs inside data transfer are merged into the prior PSH step.
 */
function classifySteps(
  packets: PacketEvent[],
  clientIp: string,
  serverIp: string,
): Step[] {
  const out: Step[] = [];
  let stepIdx = 0;

  // Phase 1: ARP discovery (only ARP that mentions either endpoint IP).
  const arpPackets = packets.filter((p) => {
    if (!isArp(p)) return false;
    const ips = arpIps(p);
    if (!ips) return false;
    return ips.includes(clientIp) && ips.includes(serverIp);
  });
  if (arpPackets.length > 0) {
    stepIdx++;
    out.push({
      kind: 'address_resolution',
      index: stepIdx,
      title: 'Address resolution',
      packets: arpPackets,
      duration_us: spanUs(arpPackets),
    });
  }

  // Phase 2: 3-way handshake (SYN, SYN+ACK, ACK — until first PSH or first FIN).
  const handshake: PacketEvent[] = [];
  let i = 0;
  for (; i < packets.length; i++) {
    const p = packets[i];
    if (isArp(p)) continue;
    const flags = p.l4?.flags ?? [];
    if (flags.includes('SYN') || (flags.includes('ACK') && handshake.length > 0 && !flags.includes('PSH') && !flags.includes('FIN'))) {
      handshake.push(p);
    }
    if (flags.includes('PSH') || flags.includes('FIN')) break;
    if (handshake.length >= 3) break;
  }
  if (handshake.length > 0) {
    stepIdx++;
    out.push({
      kind: 'handshake',
      index: stepIdx,
      title: 'TCP handshake',
      packets: handshake,
      duration_us: spanUs(handshake),
    });
  }

  // Phase 3: HTTP request + ACK pair
  const httpReqPackets: PacketEvent[] = [];
  for (; i < packets.length; i++) {
    const p = packets[i];
    if (isArp(p)) continue;
    const flags = p.l4?.flags ?? [];
    if (flags.includes('FIN') || flags.includes('RST')) break;
    if (
      flags.includes('PSH') &&
      p.l4?.src_port !== APP_PORT &&
      (p.l4?.payload_len ?? 0) > 0
    ) {
      httpReqPackets.push(p);
      i++;
      // Greedily absorb any pure ACKs until the next PSH or FIN.
      for (; i < packets.length; i++) {
        const next = packets[i];
        if (isArp(next)) continue;
        const nf = next.l4?.flags ?? [];
        if (nf.includes('FIN') || nf.includes('RST')) break;
        if (nf.includes('PSH') || (nf.includes('SYN') && !nf.includes('ACK'))) break;
        httpReqPackets.push(next);
      }
      break;
    }
  }
  if (httpReqPackets.length > 0) {
    stepIdx++;
    const isReq = httpReqPackets.some((p) => p.l7?.is_request);
    out.push({
      kind: isReq ? 'http_request' : 'http_response',
      index: stepIdx,
      title: isReq
        ? 'HTTP request'
        : 'HTTP response',
      packets: httpReqPackets,
      duration_us: spanUs(httpReqPackets),
    });
  }

  // Phase 4: response (if we just classified a request, find the next PSH
  //         going the other way, plus surrounding ACKs).
  if (out[out.length - 1]?.kind === 'http_request') {
    const httpResp: PacketEvent[] = [];
    for (; i < packets.length; i++) {
      const p = packets[i];
      if (isArp(p)) continue;
      const flags = p.l4?.flags ?? [];
      if (flags.includes('FIN') || flags.includes('RST')) break;
      if (
        flags.includes('PSH') &&
        p.l4?.src_port === APP_PORT &&
        (p.l4?.payload_len ?? 0) > 0
      ) {
        httpResp.push(p);
        i++;
        for (; i < packets.length; i++) {
          const next = packets[i];
          if (isArp(next)) continue;
          const nf = next.l4?.flags ?? [];
          if (nf.includes('FIN') || nf.includes('RST')) break;
          if (nf.includes('PSH')) break;
          httpResp.push(next);
        }
        break;
      }
    }
    if (httpResp.length > 0) {
      stepIdx++;
      out.push({
        kind: 'http_response',
        index: stepIdx,
        title: 'HTTP response',
        packets: httpResp,
        duration_us: spanUs(httpResp),
      });
    }
  }

  // Phase 5: Teardown — collect every remaining FIN,ACK and its ACKs.
  const close: PacketEvent[] = [];
  for (; i < packets.length; i++) {
    const p = packets[i];
    if (isArp(p)) continue;
    const flags = p.l4?.flags ?? [];
    if (flags.includes('FIN')) {
      close.push(p);
    }
  }
  if (close.length > 0) {
    stepIdx++;
    out.push({
      kind: 'close',
      index: stepIdx,
      title: 'TCP close',
      packets: close,
      duration_us: spanUs(close),
    });
  }

  return out;
}

// ─── 4. Stats ─────────────────────────────────────────────────────────────

function computeStats(packets: PacketEvent[]): ConversationStats {
  const s: ConversationStats = {
    totalPackets: packets.length,
    appBytesSent: 0,
    appBytesReceived: 0,
    ipChecksumOk: 0,
    ipChecksumTotal: 0,
    tcpChecksumOk: 0,
    tcpChecksumTotal: 0,
  };
  for (const p of packets) {
    if (p.l3) {
      s.ipChecksumTotal++;
      if (p.l3.checksum_ok) s.ipChecksumOk++;
    }
    if (p.l4) {
      s.tcpChecksumTotal++;
      if (p.l4.checksum_ok) s.tcpChecksumOk++;
      if (p.l4.dst_port === APP_PORT) {
        // Packet going FROM client TO server.
        s.appBytesReceived += p.l4.payload_len ?? 0;
      } else if (p.l4.src_port === APP_PORT) {
        s.appBytesSent += p.l4.payload_len ?? 0;
      }
    }
  }
  return s;
}

function spanUs(packets: PacketEvent[]): number {
  if (packets.length < 1) return 0;
  const first = packets[0];
  const last = packets[packets.length - 1];
  if (!first || !last) return 0;
  return Math.max(0, Math.round((last.ts_ns - first.ts_ns) / 1000));
}

// ─── 5. Teaching tips (one per step kind) ─────────────────────────────────

export const TEACHING_TIPS: Record<StepKind, string> = {
  address_resolution:
    'Ethernet frames need a MAC address, not an IP. Before TCP can send anything, host-1 must ARP for host-2\'s MAC. Two packets: a broadcast question and a unicast reply. Without these, TCP cannot even start.',
  handshake:
    'TCP opens a connection in 3 packets. Each side picks a random starting sequence number (seq). The ack number says "I expect byte X next." After these 3 packets, both sides consider the connection ESTABLISHED.',
  http_request:
    'The HTTP request itself. PSH means "give this to the application now, don\'t wait for more data." The JSON body sits inside the TCP segment, which sits inside the IP packet, which sits inside the Ethernet frame — that is the encapsulation chain.',
  http_response:
    'The aiohttp server\'s reply. The server often piggybacks its ACK onto the data packet (one fewer round trip). status 200 means "received and stored."',
  data_ack:
    'Pure acknowledgement — no payload, just "I got your bytes up to N." Folded into the parent step because ACKs alone are not interesting.',
  close:
    'TCP closes cleanly with two FINs — one per direction — plus final ACKs. Each side then waits in TIME_WAIT before reusing the port, so a fresh connection from the same client gets a new ephemeral port.',
};

// ─── 6. Re-exports ────────────────────────────────────────────────────────

export { isArp };
