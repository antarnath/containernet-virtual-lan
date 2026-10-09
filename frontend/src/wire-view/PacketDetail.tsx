// PacketDetail — the expand panel that shows the full TCP/IP
// protocol decode for a single packet. M4 phase 08.
//
// The capture shim (host-agent/capture_shim.py) parses every
// frame into the canonical L2 / L3 / L4 / L7 shape. We render
// it as a stack of cards, one per layer, with the most useful
// fields highlighted and the rest available in a `▾ raw` expander.
//
// Why this matters: this is the view that lets the user "see how
// TCP/IP protocol works". When a message is sent we stream a burst
// of SYN / SYN-ACK / ACK / PSH+ACK / FIN packets, and clicking
// any of them shows the exact headers on the wire.

import { memo, useState } from 'react';
import type { PacketEvent } from './types';

interface PacketDetailProps {
  packet: PacketEvent;
}

interface Field {
  label: string;
  value: string;
  /** When true, render in a monospace accent color (numbers, hex). */
  mono?: boolean;
  /** When true, render with a stronger color (checksums, flags). */
  emphasis?: boolean;
  /** Tooltip text shown next to the field. */
  hint?: string;
}

function FieldRow({ field }: { field: Field }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-2 py-0.5 text-2xs font-mono">
      <span className="text-text-muted">{field.label}</span>
      <span
        className={[
          'break-all',
          field.mono ? 'text-text-primary' : 'text-text-secondary',
          field.emphasis ? 'text-accent' : '',
        ].join(' ')}
        title={field.hint}
      >
        {field.value || <span className="italic text-text-muted">—</span>}
      </span>
    </div>
  );
}

function LayerCard({
  title,
  badge,
  children,
  defaultOpen = true,
}: {
  title: string;
  badge?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-border/60 rounded-md bg-bg-base/40">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 text-left hover:bg-bg-surface-2/40"
      >
        <div className="flex items-center gap-2">
          <span className="text-2xs font-semibold uppercase tracking-wider text-text-primary">
            {title}
          </span>
          {badge && (
            <span className="text-2xs font-mono text-text-muted">{badge}</span>
          )}
        </div>
        <span className="text-2xs text-text-muted">{open ? '▾' : '▸'}</span>
      </button>
      {open && <div className="px-2.5 pb-2">{children}</div>}
    </div>
  );
}

function L2Fields({
  l2,
  length,
}: {
  l2: Record<string, unknown> | null | undefined;
  length: number;
}) {
  if (!l2) {
    return (
      <div className="text-2xs text-text-muted italic py-1">
        No L2 header (e.g. loopback or pre-decoded frame)
      </div>
    );
  }
  const ethertype = l2.ethertype_name as string | undefined;
  const fields: Field[] = [
    {
      label: 'Source MAC',
      value: String(l2.src_mac ?? ''),
      mono: true,
      hint: 'The hardware address that transmitted the frame',
    },
    {
      label: 'Destination MAC',
      value: String(l2.dst_mac ?? ''),
      mono: true,
      hint: 'The hardware address the frame is addressed to',
    },
    {
      label: 'Ethertype',
      value: ethertype
        ? `${ethertype}${l2.ethertype ? ` (0x${Number(l2.ethertype).toString(16).padStart(4, '0')})` : ''}`
        : 'unknown',
      mono: true,
      hint: 'Identifies the L3 protocol (0x0800 = IPv4, 0x0806 = ARP)',
    },
    {
      label: 'Frame length',
      value: `${length} B`,
      mono: true,
    },
    {
      label: 'Linktype',
      value: String(l2.linktype ?? ''),
      hint: 'pcap linktype (1 = Ethernet, 276 = Linux SLL2)',
    },
    {
      label: 'Broadcast',
      value: l2.is_broadcast ? 'yes (ff:ff:ff:ff:ff:ff)' : 'no',
    },
  ];
  return (
    <div>
      {fields.map((f) => (
        <FieldRow key={f.label} field={f} />
      ))}
    </div>
  );
}

function L3Fields({ l3 }: { l3: Record<string, unknown> | null | undefined }) {
  if (!l3) {
    return (
      <div className="text-2xs text-text-muted italic py-1">
        No L3 header (ARP or non-IP frame)
      </div>
    );
  }
  const flags = (l3.flags as string) ?? '';
  const fields: Field[] = [
    { label: 'Version', value: String(l3.version ?? ''), mono: true },
    { label: 'IHL', value: `${l3.ihl ?? '?'} × 32-bit words`, mono: true },
    {
      label: 'Total length',
      value: l3.total_length != null ? `${l3.total_length} B` : '',
      mono: true,
    },
    {
      label: 'Identification',
      value: String(l3.identification ?? ''),
      mono: true,
      hint: 'Used by the destination to reassemble fragments',
    },
    {
      label: 'Flags',
      value: flags || 'none',
      mono: true,
      hint: 'DF = Don\'t Fragment, MF = More Fragments',
    },
    {
      label: 'Fragment offset',
      value: l3.fragment_offset != null ? String(l3.fragment_offset) : '0',
      mono: true,
    },
    {
      label: 'TTL',
      value: l3.ttl != null ? `${l3.ttl} hops` : '',
      mono: true,
      hint: 'Decremented by each router; packet dropped at 0',
    },
    {
      label: 'Protocol',
      value: String(l3.protocol_name ?? l3.protocol ?? ''),
      mono: true,
      hint: 'L4 protocol (6 = TCP, 17 = UDP, 1 = ICMP)',
    },
    {
      label: 'Header checksum',
      value: String(l3.checksum ?? ''),
      mono: true,
      emphasis: l3.checksum_ok === true,
      hint: l3.checksum_ok
        ? 'Recomputed and matches — header intact'
        : 'Recomputed value does NOT match — header corrupted',
    },
    {
      label: 'Source IP',
      value: String(l3.src_ip ?? ''),
      mono: true,
      emphasis: true,
    },
    {
      label: 'Destination IP',
      value: String(l3.dst_ip ?? ''),
      mono: true,
      emphasis: true,
    },
  ];
  return (
    <div>
      {fields.map((f) => (
        <FieldRow key={f.label} field={f} />
      ))}
    </div>
  );
}

function L4Fields({ l4 }: { l4: Record<string, unknown> | null | undefined }) {
  if (!l4) {
    return (
      <div className="text-2xs text-text-muted italic py-1">
        No L4 header (ICMP or L3-only)
      </div>
    );
  }
  const flags = l4.flags as string[] | undefined;
  const flagsStr = flags && flags.length > 0 ? flags.join(', ') : '—';
  const isTcp = flags != null || l4.seq != null;
  const fields: Field[] = [
    { label: 'Source port', value: String(l4.src_port ?? ''), mono: true },
    { label: 'Destination port', value: String(l4.dst_port ?? ''), mono: true },
  ];
  if (isTcp) {
    fields.push(
      { label: 'Sequence', value: String(l4.seq ?? 0), mono: true, emphasis: true, hint: 'Byte offset of the first byte in this segment' },
      { label: 'Acknowledgement', value: String(l4.ack ?? 0), mono: true, emphasis: true, hint: 'Next byte expected from the peer' },
      {
        label: 'Flags',
        value: flagsStr,
        mono: true,
        emphasis: true,
        hint: 'SYN opens, FIN closes, ACK acks, PSH pushes, RST resets',
      },
      { label: 'Window', value: l4.window != null ? `${l4.window} B` : '', mono: true, hint: 'Receive window — flow control' },
      {
        label: 'Checksum',
        value: String(l4.checksum ?? ''),
        mono: true,
        emphasis: l4.checksum_ok === true,
        hint: l4.checksum_offloaded
          ? 'TX offload — NIC finishes the checksum (captured before hardware update)'
          : l4.checksum_ok
          ? 'Recomputed and matches — segment intact'
          : 'Recomputed value does NOT match',
      },
      { label: 'Urgent pointer', value: l4.urgent != null ? String(l4.urgent) : '0', mono: true },
      { label: 'Data offset', value: l4.data_offset != null ? `${l4.data_offset} × 32-bit words` : '', mono: true },
    );
  } else {
    // UDP
    fields.push(
      { label: 'Length', value: l4.length != null ? `${l4.length} B` : '', mono: true },
    );
  }
  fields.push({
    label: 'Payload',
    value: l4.payload_len != null ? `${l4.payload_len} B` : '0 B',
    mono: true,
    emphasis: (l4.payload_len as number) > 0,
  });
  return (
    <div>
      {fields.map((f) => (
        <FieldRow key={f.label} field={f} />
      ))}
    </div>
  );
}

function L7Fields({ l7 }: { l7: Record<string, unknown> | null | undefined }) {
  if (!l7) {
    return (
      <div className="text-2xs text-text-muted italic py-1">
        No L7 (application layer) decoded — port is not HTTP/S
      </div>
    );
  }
  const isReq = !!l7.is_request;
  const isResp = !!l7.is_response;
  const fields: Field[] = [];
  if (isReq) {
    fields.push(
      { label: 'Method', value: String(l7.method ?? ''), mono: true, emphasis: true },
      { label: 'Path', value: String(l7.path ?? ''), mono: true },
      { label: 'Version', value: String(l7.version ?? ''), mono: true },
    );
  } else if (isResp) {
    fields.push(
      { label: 'Status', value: `${l7.status_code ?? '?'} ${l7.status_text ?? ''}`, mono: true, emphasis: true },
      { label: 'Version', value: String(l7.version ?? ''), mono: true },
    );
  }
  const headers = (l7.headers as Record<string, string>) ?? {};
  for (const [k, v] of Object.entries(headers).slice(0, 12)) {
    fields.push({
      label: k,
      value: v,
      mono: true,
    });
  }
  if (l7.body_decoded) {
    fields.push({
      label: 'Body',
      value: String(l7.body_decoded).slice(0, 240),
      hint: l7.body_truncated
        ? 'Body truncated to 1 KB'
        : 'Full body',
    });
  }
  return (
    <div>
      {fields.map((f) => (
        <FieldRow key={f.label} field={f} />
      ))}
    </div>
  );
}

function ArpFields({ arp }: { arp: Record<string, unknown> | null | undefined }) {
  if (!arp) {
    return null;
  }
  const fields: Field[] = [
    { label: 'Opcode', value: String(arp.opcode_name ?? arp.opcode ?? ''), mono: true, emphasis: true },
    { label: 'Sender MAC', value: String(arp.sender_mac ?? ''), mono: true },
    { label: 'Sender IP', value: String(arp.sender_ip ?? ''), mono: true },
    { label: 'Target MAC', value: String(arp.target_mac ?? ''), mono: true },
    { label: 'Target IP', value: String(arp.target_ip ?? ''), mono: true, emphasis: true },
  ];
  return (
    <div>
      {fields.map((f) => (
        <FieldRow key={f.label} field={f} />
      ))}
    </div>
  );
}

function RawJson({ data }: { data: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-border/40 pt-1.5 mt-1.5">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-2xs text-text-muted hover:text-text-secondary flex items-center gap-1"
      >
        {open ? '▾' : '▸'} raw JSON
      </button>
      {open && (
        <pre className="mt-1 text-2xs font-mono text-text-muted whitespace-pre-wrap break-all">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

function PacketDetailImpl({ packet }: PacketDetailProps) {
  const raw = packet.raw;
  if (!raw) {
    return (
      <div className="px-3 py-2 text-2xs text-text-muted italic border-t border-border/40">
        Full TCP/IP decode unavailable for this packet (no `raw` payload
        from the backend). Open the wire from the canvas to stream the
        per-link SSE channel — it includes the full decode.
      </div>
    );
  }
  const l2 = raw.l2;
  const l3 = raw.l3 ?? null;
  const l4 = raw.l4 ?? null;
  const l7 = raw.l7 ?? null;
  const arp = (raw as Record<string, unknown>).arp as
    | Record<string, unknown>
    | null
    | undefined;
  const l3proto = (l3?.protocol_name as string) || '';
  return (
    <div className="px-3 py-2 border-t border-border/40 space-y-1.5 bg-bg-base/30">
      {/* Frame summary line at the top so the user always sees the
          high-level shape before they dive into the layers. */}
      <div className="flex items-center gap-3 text-2xs font-mono pb-1">
        <span className="text-text-muted">Frame:</span>
        <span className="text-text-secondary">
          {packet.length} B
        </span>
        <span className="text-text-muted">·</span>
        <span className="text-text-secondary">
          {l2?.ethertype_name as string ?? '—'}
        </span>
        {l3proto && (
          <>
            <span className="text-text-muted">·</span>
            <span className="text-text-secondary">{l3proto}</span>
          </>
        )}
        {packet.src_ip && (
          <>
            <span className="text-text-muted">·</span>
            <span className="text-text-primary">
              {packet.src_ip}
              {packet.src_port ? `:${packet.src_port}` : ''}
            </span>
            <span className="text-text-muted">→</span>
            <span className="text-text-primary">
              {packet.dst_ip}
              {packet.dst_port ? `:${packet.dst_port}` : ''}
            </span>
          </>
        )}
      </div>

      <LayerCard title="L2 · Ethernet" badge="frame header">
        <L2Fields l2={l2} length={packet.length} />
      </LayerCard>

      {arp ? (
        <LayerCard title="L3 · ARP" badge="address resolution">
          <ArpFields arp={arp} />
        </LayerCard>
      ) : (
        <LayerCard title="L3 · IPv4" badge="network layer">
          <L3Fields l3={l3} />
        </LayerCard>
      )}

      <LayerCard title="L4 · Transport" badge={l4 ? String(l4.src_port ?? '?') + ' → ' + String(l4.dst_port ?? '?') : '—'}>
        <L4Fields l4={l4} />
      </LayerCard>

      <LayerCard title="L7 · Application" badge="payload" defaultOpen={!!l7}>
        <L7Fields l7={l7} />
      </LayerCard>

      <RawJson data={raw} />
    </div>
  );
}

export const PacketDetail = memo(PacketDetailImpl);
export default PacketDetail;
