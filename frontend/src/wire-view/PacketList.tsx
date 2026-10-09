// PacketList — auto-scrolling list of PacketRow entries, newest
// at the top.
//
// The list auto-scrolls to the top on every new packet UNLESS the
// user has paused the stream. The header is a thin column legend
// (time / proto / endpoint / length / wire). Empty state shows a
// centered "Waiting for traffic…" hint.

import { useEffect, useRef } from 'react';
import type { PacketEvent, PacketFilter } from './types';
import { PacketRow } from './PacketRow';

interface PacketListProps {
  packets: PacketEvent[];
  filter: PacketFilter;
  paused: boolean;
  wireLabel?: string;
}

function applyFilter(pkts: PacketEvent[], filter: PacketFilter): PacketEvent[] {
  return pkts.filter((p) => {
    if (filter.attackOnly && p.src_node_kind !== 'attacker') return false;
    if (filter.protocols.size === 0) return true;
    return filter.protocols.has(p.protocol);
  });
}

export function PacketList({ packets, filter, paused, wireLabel }: PacketListProps) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  const visible = applyFilter(packets, filter);
  // Newest first — packets arrive oldest-last so we reverse.
  const ordered = visible.slice().reverse();

  // Auto-scroll to top on new packets unless paused.
  useEffect(() => {
    if (paused) return;
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = 0;
  }, [ordered.length, paused]);

  if (ordered.length === 0) {
    return (
      <div className="flex-1 min-h-0 flex items-center justify-center text-text-muted text-sm">
        <div className="text-center">
          <div className="text-2xs uppercase tracking-wider mb-1">no packets</div>
          <div>Waiting for traffic on this wire…</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {/* Column legend */}
      <div className="h-7 px-3 flex items-center gap-3 font-mono text-2xs uppercase tracking-wider text-text-muted bg-bg-surface-2 border-b border-border flex-shrink-0">
        <span className="w-24">Time</span>
        <span className="w-12">Proto</span>
        <span className="flex-1">Endpoint</span>
        <span className="w-14 text-right">Length</span>
        {wireLabel && <span className="w-28 text-right">Wire</span>}
      </div>
      {/* Scroll container */}
      <div
        ref={scrollerRef}
        className="flex-1 min-h-0 overflow-y-auto"
      >
        {ordered.map((p) => (
          <PacketRow key={p.id} packet={p} wireLabel={wireLabel} />
        ))}
      </div>
    </div>
  );
}

export default PacketList;
