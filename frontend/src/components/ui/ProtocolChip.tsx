// ProtocolChip — a compact 16px-tall pill that color-codes a packet's
// protocol (TCP / UDP / ICMP / ARP / HTTP / attack). Reuses the
// design-system `StatusPill` palette via the `protocol-*` tones, but
// is shorter so it fits inside a 32px-tall PacketRow without
// crowding the data.
//
// Per design-system §6.6: each row carries a protocol chip in the
// protocol's color. When the packet came from an attacker node, the
// chip's tone becomes `attack` (the "watch this" cue).

import { StatusPill, type StatusTone } from './StatusPill';
import type { PacketProtocol } from '../../wire-view/types';

const PROTO_LABEL: Record<PacketProtocol, string> = {
  tcp: 'TCP',
  udp: 'UDP',
  icmp: 'ICMP',
  arp: 'ARP',
  http: 'HTTP',
  other: 'other',
};

interface ProtocolChipProps {
  protocol: PacketProtocol;
  /** When true, override the chip to the "attack" tone (e.g. attacker-sourced). */
  isAttack?: boolean;
  className?: string;
}

export function ProtocolChip({ protocol, isAttack, className }: ProtocolChipProps) {
  // "other" isn't a StatusTone — collapse it onto the muted idle chip
  // so unknown protocols still render instead of crashing the row.
  const tone: StatusTone = isAttack
    ? 'attack'
    : protocol === 'other'
      ? 'idle'
      : protocol;
  const label = isAttack ? 'ATTACK' : PROTO_LABEL[protocol];
  return (
    <StatusPill tone={tone} className={['h-4 px-1.5 text-2xs', className ?? ''].join(' ')}>
      {label}
    </StatusPill>
  );
}

export default ProtocolChip;
