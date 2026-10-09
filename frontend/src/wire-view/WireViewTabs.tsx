// WireViewTabs — the three tabs across the top of the wire view
// content area: Raw / Conversations / Attackers.
//
// Conversations is a placeholder for phase 04 (per the design
// system, it's a "grouped by 5-tuple" view); we render a friendly
// "coming in a later phase" message there so the tab strip is
// usable. Attackers filters the same list down to packets whose
// src_node_kind === 'attacker'.

import type { WireViewTab } from './types';

interface WireViewTabsProps {
  active: WireViewTab;
  onChange: (tab: WireViewTab) => void;
  counts: { raw: number; attackers: number };
}

const TABS: { key: WireViewTab; label: string }[] = [
  { key: 'raw', label: 'Raw' },
  { key: 'conversations', label: 'Conversations' },
  { key: 'attackers', label: 'Attackers' },
];

export function WireViewTabs({ active, onChange, counts }: WireViewTabsProps) {
  return (
    <div className="h-9 bg-bg-surface border-b border-border flex items-center px-2 gap-1">
      {TABS.map((t) => {
        const isActive = t.key === active;
        const count = t.key === 'raw' ? counts.raw : t.key === 'attackers' ? counts.attackers : null;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={[
              'h-7 px-3 text-xs font-medium rounded-md transition-colors duration-fast',
              isActive
                ? 'bg-bg-surface-2 text-text-primary'
                : 'text-text-secondary hover:text-text-primary hover:bg-bg-surface-2/50',
            ].join(' ')}
            aria-pressed={isActive}
          >
            {t.label}
            {count !== null && count > 0 && (
              <span
                className={[
                  'ml-1.5 inline-flex items-center justify-center min-w-4 h-4 px-1 rounded text-2xs font-mono',
                  isActive ? 'bg-accent-soft text-accent' : 'bg-bg-surface text-text-muted',
                ].join(' ')}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export default WireViewTabs;
