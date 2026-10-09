// PacketFilter — the chip row at the top of the wire view that
// lets the user toggle which protocols (and attack packets) are
// visible.
//
// Each chip is a small button styled like a StatusPill: when
// inactive it's a subtle ghost button; when active it lights up
// in the protocol's color. The "All" chip clears every filter;
// the "Attack" chip flips the attackOnly flag.

import { Button } from '../components/ui/Button';
import type { PacketFilter as PacketFilterState, PacketProtocol } from './types';

interface PacketFilterProps {
  filter: PacketFilterState;
  onChange: (next: PacketFilterState) => void;
}

type ChipKey = 'all' | 'attack' | PacketProtocol;

interface ChipDef {
  key: ChipKey;
  label: string;
  /** Tailwind classes for the *active* state. Empty for the "All" chip. */
  active: string;
}

const CHIPS: ChipDef[] = [
  { key: 'all', label: 'All', active: 'bg-accent-soft text-accent border-accent/40' },
  { key: 'tcp', label: 'TCP', active: 'bg-protocol-tcp/10 text-protocol-tcp border-protocol-tcp/40' },
  { key: 'udp', label: 'UDP', active: 'bg-protocol-udp/10 text-protocol-udp border-protocol-udp/40' },
  { key: 'icmp', label: 'ICMP', active: 'bg-protocol-icmp/10 text-protocol-icmp border-protocol-icmp/40' },
  { key: 'arp', label: 'ARP', active: 'bg-protocol-arp/10 text-protocol-arp border-protocol-arp/40' },
  { key: 'http', label: 'HTTP', active: 'bg-protocol-http/10 text-protocol-http border-protocol-http/40' },
  { key: 'attack', label: 'Attack', active: 'bg-protocol-attack/10 text-protocol-attack border-protocol-attack/40' },
];

function isActive(chip: ChipDef, filter: PacketFilterState): boolean {
  if (chip.key === 'all') {
    return filter.protocols.size === 0 && !filter.attackOnly;
  }
  if (chip.key === 'attack') {
    return filter.attackOnly;
  }
  return filter.protocols.has(chip.key);
}

function nextFilter(chip: ChipDef, filter: PacketFilterState): PacketFilterState {
  if (chip.key === 'all') {
    return { protocols: new Set(), attackOnly: false };
  }
  if (chip.key === 'attack') {
    return { ...filter, attackOnly: !filter.attackOnly };
  }
  const next = new Set(filter.protocols);
  if (next.has(chip.key)) {
    next.delete(chip.key);
  } else {
    next.add(chip.key);
  }
  return { ...filter, protocols: next };
}

export function PacketFilter({ filter, onChange }: PacketFilterProps) {
  return (
    <div className="flex items-center gap-1.5 px-3 py-2 bg-bg-surface border-b border-border">
      {CHIPS.map((c) => {
        const active = isActive(c, filter);
        return (
          <Button
            key={c.key}
            variant="ghost"
            size="sm"
            onClick={() => onChange(nextFilter(c, filter))}
            className={[
              'h-6 px-2 text-2xs font-mono uppercase tracking-wider border',
              active ? c.active : 'border-transparent text-text-secondary',
            ].join(' ')}
            aria-pressed={active}
          >
            {c.label}
          </Button>
        );
      })}
    </div>
  );
}

export default PacketFilter;
