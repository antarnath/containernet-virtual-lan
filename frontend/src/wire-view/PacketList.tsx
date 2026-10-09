// PacketList — auto-scrolling list of PacketRow entries, newest
// at the top.
//
// The list auto-scrolls to the top on every new packet UNLESS the
// user has paused the stream. The header is a thin column legend
// (time / proto / endpoint / length / wire). Empty state shows a
// centered "Waiting for traffic…" hint.
//
// M4 phase 08: clicking a row toggles the per-packet
// ``PacketDetail`` expand which renders the full L2/L3/L4/L7
// decode of the captured frame. Only one row is expanded at a
// time; the user re-clicks the same row to collapse it.

import { useEffect, useRef, useState } from 'react';
import type { PacketEvent, PacketFilter } from './types';
import { PacketRow } from './PacketRow';
import { PacketDetail } from './PacketDetail';

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
  // ID of the row currently expanded to show the TCP/IP decode.
  // Only one row at a time.
  const [expandedId, setExpandedId] = useState<number | null>(null);

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
          <div className="text-2xs text-text-muted/70 mt-2">
            Tip: send a message from the canvas (click a host → “Send”)
            to generate traffic.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      {/* Column legend */}
      <div className="h-7 px-3 flex items-center gap-3 font-mono text-2xs uppercase tracking-wider text-text-muted bg-bg-surface-2 border-b border-border flex-shrink-0">
        <span className="w-6" />
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
        {ordered.map((p) => {
          const isExpanded = expandedId === p.id;
          return (
            <div key={p.id}>
              <PacketRow
                packet={p}
                wireLabel={wireLabel}
                isExpanded={isExpanded}
                onToggle={() =>
                  setExpandedId((cur) => (cur === p.id ? null : p.id))
                }
              />
              {isExpanded && <PacketDetail packet={p} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default PacketList;
