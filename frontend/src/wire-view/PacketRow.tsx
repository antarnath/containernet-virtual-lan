// PacketRow — one row in the wire view's packet list.
//
// Per design-system §6.6:
//   * 32px tall, 12px padding
//   * Mono data, protocol chip in the protocol's color
//   * When src_node_kind === 'attacker' → 2px `danger` left border
//     and the chip's tone becomes `attack` (the "watch this" cue)
//
// M4 phase 08: a small chevron on the left lets the user click
// the row to expand the full TCP/IP decode (rendered by
// PacketDetail in the parent). The row is keyboard-clickable too
// (Enter / Space toggles the expand) for accessibility.
//
// The row is purely presentational; the parent (PacketList) supplies
// the layout and decides which rows are visible.

import { memo } from 'react';
import type { PacketEvent } from './types';
import { ProtocolChip } from '../components/ui/ProtocolChip';

interface PacketRowProps {
  packet: PacketEvent;
  /** Cached label for the wire (e.g. "10.0.0.0/24"). Optional. */
  wireLabel?: string;
  /** True when this row's expand panel is currently shown. */
  isExpanded?: boolean;
  /** Toggle the expand panel. */
  onToggle?: () => void;
}

function formatTime(ts: string): string {
  // ts is "YYYY-MM-DDTHH:MM:SS.uuuuuuZ" — take the HH:MM:SS.uuu part.
  if (!ts) return '--:--:--';
  const tIdx = ts.indexOf('T');
  if (tIdx === -1) return ts.slice(11, 23) || ts;
  // up to 8 chars of the time + 4 chars of micros for a "HH:MM:SS.uuu"
  // (the .123 is enough to disambiguate adjacent packets).
  const time = ts.slice(tIdx + 1);
  return time.length >= 12 ? `${time.slice(0, 8)}.${time.slice(9, 12)}` : time;
}

function endpointStr(p: PacketEvent): string {
  if (p.src_ip && p.dst_ip) {
    const sp = p.src_port ? `:${p.src_port}` : '';
    const dp = p.dst_port ? `:${p.dst_port}` : '';
    return `${p.src_ip}${sp}  →  ${p.dst_ip}${dp}`;
  }
  // ARP / L2-only packets don't have IP / port info.
  if (p.src_mac && p.dst_mac) {
    return `${p.src_mac}  →  ${p.dst_mac}`;
  }
  return p.summary || '(unknown)';
}

function PacketRowImpl({ packet, wireLabel, isExpanded, onToggle }: PacketRowProps) {
  const isAttack = packet.src_node_kind === 'attacker';
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onToggle}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onToggle?.();
        }
      }}
      aria-expanded={!!isExpanded}
      className={[
        'h-8 px-3 flex items-center gap-3 font-mono text-xs cursor-pointer',
        'border-b border-border/40',
        'hover:bg-bg-surface-2 transition-colors duration-fast',
        isExpanded ? 'bg-accent-soft/20' : '',
        isAttack
          ? 'border-l-2 border-l-danger bg-danger-soft/20'
          : 'border-l-2 border-l-transparent',
      ].join(' ')}
      data-pkt-id={packet.id}
    >
      <span
        className="w-6 text-text-muted select-none"
        title={isExpanded ? 'Hide TCP/IP decode' : 'Show full TCP/IP decode'}
      >
        {isExpanded ? '▾' : '▸'}
      </span>
      <span className="w-24 text-text-muted tabular-nums">
        {formatTime(packet.ts)}
      </span>
      <ProtocolChip protocol={packet.protocol} isAttack={isAttack} />
      <span className="flex-1 min-w-0 truncate text-text-primary">
        {endpointStr(packet)}
      </span>
      <span className="w-14 text-right text-text-muted tabular-nums">
        {packet.length ? `${packet.length}B` : ''}
      </span>
      {wireLabel && (
        <span className="w-28 text-right text-text-secondary truncate">
          {wireLabel}
        </span>
      )}
    </div>
  );
}

export const PacketRow = memo(PacketRowImpl);
export default PacketRow;
