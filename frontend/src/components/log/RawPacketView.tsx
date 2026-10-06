// RawPacketView — today's packet log view, kept verbatim. Shows every
// packet (including background noise) with filter chips and a small
// side drawer.

import { useMemo, useState } from 'react';
import type { PacketEvent } from '../../types';

interface Props {
  events: PacketEvent[];
}

const FLAG_COLOR: Record<string, string> = {
  SYN: 'text-blue-400',
  ACK: 'text-zinc-400',
  PSH: 'text-emerald-400',
  FIN: 'text-amber-400',
  RST: 'text-rose-400',
};

function flagsClass(flags: string[] | undefined): string {
  if (!flags || flags.length === 0) return 'text-zinc-300';
  return flags.map((f) => FLAG_COLOR[f] ?? 'text-zinc-300').join(' ');
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number, w = 2) => n.toString().padStart(w, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds() * 1000, 6)}`;
}

function matchesFilter(e: PacketEvent, filter: string): boolean {
  if (filter === 'all') return true;
  if (filter === 'ARP') return e.l2?.ethertype_name === 'ARP';
  const flags = e.l4?.flags ?? [];
  if (filter === 'SYN,ACK')
    return flags.includes('SYN') && flags.includes('ACK');
  if (filter === 'data')
    return flags.includes('PSH') || (e.l4?.payload_len ?? 0) > 0;
  if (filter === 'FIN') return flags.includes('FIN');
  if (filter === 'RST') return flags.includes('RST');
  return true;
}

export function RawPacketView({ events }: Props) {
  const [filter, setFilter] = useState('all');
  const filtered = useMemo(
    () => events.filter((e) => matchesFilter(e, filter)),
    [events, filter],
  );

  return (
    <div className="flex-1 overflow-auto bg-zinc-950 text-zinc-200">
      <div className="sticky top-0 bg-zinc-900/95 backdrop-blur border-b border-zinc-800 px-4 py-2 z-10 flex items-center gap-2 flex-wrap text-xs">
        <span className="text-zinc-500 mr-2">Filter:</span>
        {['all', 'SYN,ACK', 'data', 'FIN', 'RST', 'ARP'].map((chip) => (
          <button
            key={chip}
            onClick={() => setFilter(chip)}
            className={`px-2 py-0.5 rounded border ${
              filter === chip
                ? 'border-emerald-400 text-emerald-300 bg-emerald-400/10'
                : 'border-zinc-700 text-zinc-400 hover:text-zinc-100'
            }`}
          >
            {chip}
          </button>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="p-6 text-zinc-500 text-sm">
          no packets match the filter
        </div>
      )}

      <div className="font-mono text-xs">
        {filtered.map((e) => {
          const flags = e.l4?.flags ?? [];
          const isArp = e.l2?.ethertype_name === 'ARP';
          const proto = isArp ? 'ARP' : e.l4 ? 'TCP' : '?';
          return (
            <div
              key={e.id}
              className="px-4 py-1 hover:bg-zinc-900/60 border-b border-zinc-900/50"
            >
              <div className="flex gap-3 items-baseline">
                <span className="text-zinc-500 tabular-nums">
                  {fmtTime(e.ts)}
                </span>
                <span className="text-zinc-400 w-12">{proto}</span>
                {isArp ? (
                  <span className="text-zinc-200">{e.summary}</span>
                ) : (
                  <span className="text-zinc-200">
                    <span className="text-zinc-300">{e.l4?.src_port}</span>
                    <span className="text-zinc-500 mx-1">→</span>
                    <span className="text-zinc-300">{e.l4?.dst_port}</span>
                    <span className={`ml-3 ${flagsClass(flags)}`}>
                      [{flags.join(', ') || '—'}]
                    </span>
                    <span className="ml-3 text-zinc-400">
                      seq={e.l4?.seq} ack={e.l4?.ack}
                    </span>
                    {(e.l4?.payload_len ?? 0) > 0 && (
                      <span className="ml-3 text-emerald-300">
                        payload={e.l4?.payload_len} B
                      </span>
                    )}
                  </span>
                )}
              </div>
              {e.l7?.method && (
                <div className="ml-32 text-zinc-400">
                  {e.l7.method} {e.l7.path} {e.l7.version}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
