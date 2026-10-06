// EnvelopeModal — full-screen modal showing a single packet's L2/L3/L4/L7
// breakdown with byte counts and ✓ next to every checksum. Click any layer
// heading to expand/collapse. Esc or backdrop-click closes.
//
// Replaces the old right-side drawer (today's PacketDrawer) with a larger,
// structured view.

import { useEffect } from 'react';
import type { PacketEvent } from '../../types';

interface Props {
  event: PacketEvent | null;
  onClose: () => void;
}

export function EnvelopeModal({ event, onClose }: Props) {
  // Esc key closes the modal.
  useEffect(() => {
    if (!event) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [event, onClose]);

  if (!event) return null;

  const l2Bytes = 14; // Ethernet header (no VLAN)
  const l3Bytes = (event.l3?.ihl ?? 5) * 4;
  const l4Bytes = (event.l4?.data_offset ?? 5) * 4;
  const l7Bytes = event.l4?.payload_len ?? 0;
  const crcBytes = 4; // Ethernet trailer
  const totalBytes = l2Bytes + l3Bytes + l4Bytes + l7Bytes + crcBytes;
  const efficiency =
    l7Bytes > 0 ? Math.round((l7Bytes / totalBytes) * 1000) / 10 : 0;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="bg-zinc-950 border border-zinc-700 rounded-lg shadow-2xl w-full max-w-3xl max-h-[85vh] overflow-auto font-mono text-sm"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header */}
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-3 sticky top-0 bg-zinc-950 z-10">
          <div>
            <div className="text-zinc-100 text-base font-semibold">
              packet #{event.id}
            </div>
            <div className="text-zinc-500 text-xs">
              captured {new Date(event.ts).toLocaleTimeString()} · {event.len} B on wire
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-100 text-xl px-3 py-1"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="p-5 space-y-3">
          {/* L2 */}
          <Layer
            title="L2 Ethernet"
            bytes={l2Bytes}
            checksumOk={event.l2?.crc_ok ?? true}
            checksumLabel="CRC-32"
          >
            <Field label="dst_mac" value={event.l2.dst_mac} note="← destination NIC" />
            <Field label="src_mac" value={event.l2.src_mac} note="← source NIC" />
            <Field
              label="ethertype"
              value={`0x${event.l2.ethertype.toString(16).padStart(4, '0')} (${event.l2.ethertype_name})`}
            />
          </Layer>

          {/* L3 */}
          {event.l3 && (
            <Layer
              title="L3 IPv4"
              bytes={l3Bytes}
              checksumOk={event.l3.checksum_ok}
              checksumLabel="header checksum"
            >
              <Field
                label="version / ihl"
                value={`${event.l3.version} / ${event.l3.ihl} (${l3Bytes} B)`}
              />
              <Field
                label="dscp / total_length"
                value={`${event.l3.dscp} / ${event.l3.total_length}`}
              />
              <Field
                label="identification"
                value={event.l3.identification}
              />
              <Field
                label="flags / fragment_offset"
                value={`${event.l3.flags} / ${event.l3.fragment_offset}`}
              />
              <Field
                label="ttl / protocol"
                value={`${event.l3.ttl} / ${event.l3.protocol} (${event.l3.protocol_name})`}
              />
              <Field
                label="src → dst"
                value={`${event.l3.src_ip} → ${event.l3.dst_ip}`}
                highlight
              />
            </Layer>
          )}

          {/* L4 */}
          {event.l4 && (
            <Layer
              title={`L4 ${event.l4.flags.length > 0 ? 'TCP' : (event.l3?.protocol_name ?? 'L4')}`}
              bytes={l4Bytes}
              checksumOk={event.l4.checksum_ok}
              checksumLabel="segment checksum"
            >
              <Field
                label="src_port → dst_port"
                value={`${event.l4.src_port} → ${event.l4.dst_port}`}
                highlight
              />
              <Field
                label="seq / ack"
                value={`${event.l4.seq} / ${event.l4.ack}`}
              />
              <Field
                label="data_offset / flags"
                value={`${event.l4.data_offset} (${l4Bytes} B) / ${event.l4.flags.join(', ') || '—'}`}
              />
              <Field
                label="window / checksum"
                value={`${event.l4.window} / ${event.l4.checksum}`}
              />
              {event.l4.options.length > 0 && (
                <Field
                  label="options"
                  value={event.l4.options.map((o) => o.kind).join(', ')}
                />
              )}
            </Layer>
          )}

          {/* L7 */}
          {event.l7 && (
            <Layer title="L7 HTTP" bytes={l7Bytes}>
              {event.l7.is_request ? (
                <div className="text-zinc-200 mb-2">
                  {event.l7.method} {event.l7.path} {event.l7.version}
                </div>
              ) : event.l7.is_response ? (
                <div className="text-zinc-200 mb-2">
                  {event.l7.version} {event.l7.status_code} {event.l7.status_text}
                </div>
              ) : null}
              {Object.keys(event.l7.headers).length > 0 && (
                <pre className="text-zinc-400 text-xs whitespace-pre-wrap mb-2">
                  {Object.entries(event.l7.headers)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join('\n')}
                </pre>
              )}
              <pre className="text-zinc-200 text-xs whitespace-pre-wrap bg-zinc-900 p-2 rounded">
                {event.l7.body_decoded}
                {event.l7.body_truncated ? ' …' : ''}
              </pre>
            </Layer>
          )}

          {/* footer stats */}
          <div className="border-t border-zinc-800 pt-3 mt-4 text-xs text-zinc-400 space-y-1">
            <div>
              📊 {l2Bytes} (L2) + {l3Bytes} (L3) + {l4Bytes} (L4) + {l7Bytes} (L7) +{' '}
              {crcBytes} (CRC) = <span className="text-zinc-200">{totalBytes} bytes on wire</span>
            </div>
            {l7Bytes > 0 && (
              <div>
                💡 Bandwidth efficiency: {l7Bytes} / {totalBytes} ={' '}
                <span className="text-emerald-400">{efficiency}%</span> — the rest is
                headers and error-detection overhead.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── helpers ──────────────────────────────────────────────────────────────

function Layer({
  title,
  bytes,
  checksumOk,
  checksumLabel,
  children,
}: {
  title: string;
  bytes: number;
  checksumOk?: boolean;
  checksumLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border border-zinc-800 rounded">
      <header className="flex items-center justify-between bg-zinc-900 px-3 py-2 rounded-t">
        <h3 className="text-zinc-100 font-semibold text-sm">{title}</h3>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-zinc-500">{bytes} bytes</span>
          {checksumOk !== undefined && (
            <span
              className={
                checksumOk
                  ? 'text-emerald-400'
                  : 'text-rose-400 font-semibold'
              }
            >
              {checksumLabel ?? 'checksum'}{' '}
              {checksumOk ? '✓' : '✗ MISMATCH'}
            </span>
          )}
        </div>
      </header>
      <div className="p-3 space-y-1">{children}</div>
    </section>
  );
}

function Field({
  label,
  value,
  note,
  highlight,
}: {
  label: string;
  value: string;
  note?: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex gap-3 text-xs">
      <span className="text-zinc-500 w-40 shrink-0">{label}</span>
      <span className={highlight ? 'text-emerald-300' : 'text-zinc-200'}>
        {value}
      </span>
      {note && <span className="text-zinc-500 italic">{note}</span>}
    </div>
  );
}
