// StepCard — one card per step in a TCP/IP conversation.
// Shows the packets as compact rows and a "envelope" button per
// packet that opens EnvelopeModal.

import type { PacketEvent } from '../../types';
import type { Step } from '../../utils/tcpClassifier';

interface Props {
  step: Step;
  onSelectPacket: (e: PacketEvent) => void;
}

const FLAG_COLOR: Record<string, string> = {
  SYN: 'text-blue-400',
  ACK: 'text-zinc-400',
  PSH: 'text-emerald-400',
  FIN: 'text-amber-400',
  RST: 'text-rose-400',
};

function flagsClass(flags: string[]): string {
  if (!flags || flags.length === 0) return 'text-zinc-300';
  return flags.map((f) => FLAG_COLOR[f] ?? 'text-zinc-300').join(' ');
}

function stepBadge(idx: number): string {
  // ① ② ③ ④ ⑤ …
  const circled = 0x2460 + idx - 1;
  return String.fromCharCode(circled);
}

export function StepCard({ step, onSelectPacket }: Props) {
  const first = step.packets[0];
  const last = step.packets[step.packets.length - 1];
  const durationMs = step.duration_us / 1000;

  return (
    <section className="border border-zinc-800 rounded-lg overflow-hidden bg-zinc-950">
      {/* header */}
      <header className="flex items-center justify-between bg-zinc-900 px-4 py-2 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <span className="text-zinc-400 text-lg">{stepBadge(step.index)}</span>
          <h3 className="text-zinc-100 font-semibold">{step.title}</h3>
        </div>
        <div className="text-xs text-zinc-500">
          {step.packets.length} packet{step.packets.length !== 1 ? 's' : ''} ·{' '}
          {durationMs.toFixed(2)} ms
          {first && last && first.id !== last.id && (
            <span className="ml-2 text-zinc-600">
              (#{first.id} → #{last.id})
            </span>
          )}
        </div>
      </header>

      {/* packet rows */}
      <div className="divide-y divide-zinc-900">
        {step.packets.map((p) => (
          <PacketRow key={p.id} packet={p} onShow={() => onSelectPacket(p)} />
        ))}
      </div>

    </section>
  );
}

function PacketRow({
  packet,
  onShow,
}: {
  packet: PacketEvent;
  onShow: () => void;
}) {
  const flags = packet.l4?.flags ?? [];
  const isArp = packet.l2.ethertype_name === 'ARP';
  const l7Body = packet.l7?.body_decoded ?? '';
  const protoLabel = isArp ? 'ARP' : packet.l4 ? 'TCP' : '?';

  return (
    <div className="px-4 py-2 hover:bg-zinc-900/60 transition-colors">
      <div className="flex items-center gap-3 font-mono text-xs">
        <span className="text-zinc-500 tabular-nums">
          {fmtTime(packet.ts)}
        </span>
        <span className="text-zinc-400 w-10">{protoLabel}</span>

        {isArp ? (
          <span className="text-zinc-200 flex-1">{packet.summary}</span>
        ) : (
          <span className="flex-1 flex items-center gap-2 flex-wrap">
            <span className="text-zinc-300">
              {packet.l4?.src_port} → {packet.l4?.dst_port}
            </span>
            <span className={flagsClass(flags)}>
              [{flags.join(', ') || '—'}]
            </span>
            <span className="text-zinc-400">
              seq={packet.l4?.seq} ack={packet.l4?.ack}
            </span>
            <span className="text-zinc-500">win={packet.l4?.window}</span>
            {(packet.l4?.payload_len ?? 0) > 0 && (
              <span className="text-emerald-300">
                payload={packet.l4?.payload_len} B
              </span>
            )}
          </span>
        )}

        <button
          onClick={onShow}
          className="text-xs px-2 py-0.5 rounded border border-zinc-700 text-zinc-400 hover:text-emerald-300 hover:border-emerald-400"
        >
          envelope
        </button>
      </div>

      {/* HTTP body preview, when present */}
      {packet.l7?.method && (
        <div className="ml-32 mt-1 text-xs text-zinc-400">
          {packet.l7.method} {packet.l7.path} {packet.l7.version}
        </div>
      )}
      {packet.l7?.status_code && (
        <div className="ml-32 mt-1 text-xs text-zinc-400">
          {packet.l7.version} {packet.l7.status_code} {packet.l7.status_text}
        </div>
      )}
      {l7Body && (
        <div className="ml-32 mt-0.5 text-xs text-zinc-500 font-mono truncate">
          {l7Body.length > 100 ? l7Body.slice(0, 100) + '…' : l7Body}
        </div>
      )}
    </div>
  );
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number, w = 2) => n.toString().padStart(w, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds() * 1000, 6)}`;
}
