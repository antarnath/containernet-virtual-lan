// EventFilter — the chip row at the top of the LogsView. Each chip
// toggles one event kind in the active filter set. "All" clears the
// set (matches every kind). Multiple chips compose (an event shows if
// its kind is in the active set, OR the set is empty = "All").
//
// Tone per chip is per design-system §6.7 — attacks are danger, errors
// are danger, anomalies are warn, lifecycle is primary-soft, etc.

import { type ProjectEventKind } from '../api/client';

export type EventKindFilter = ProjectEventKind | 'all';

interface ChipDef {
  key: EventKindFilter;
  label: string;
  tone: 'neutral' | 'primary' | 'warn' | 'danger' | 'info';
}

const CHIPS: ChipDef[] = [
  { key: 'all', label: 'All', tone: 'neutral' },
  { key: 'lifecycle', label: 'Lifecycle', tone: 'primary' },
  { key: 'node_started', label: 'Nodes', tone: 'info' },
  { key: 'node_stopped', label: 'Stops', tone: 'info' },
  { key: 'link_created', label: 'Wires', tone: 'info' },
  { key: 'bridge_created', label: 'Bridges', tone: 'info' },
  { key: 'message_sent', label: 'Messages', tone: 'info' },
  { key: 'anomaly', label: 'Anomalies', tone: 'warn' },
  { key: 'attack_signal', label: 'Attacks', tone: 'danger' },
  { key: 'error', label: 'Errors', tone: 'danger' },
];

const TONE_ACTIVE: Record<ChipDef['tone'], string> = {
  neutral: 'border-border-strong bg-bg-elevated text-text-primary',
  primary: 'border-primary bg-primary-soft text-text-primary',
  warn: 'border-warn bg-warn-soft text-warn',
  danger: 'border-danger bg-danger-soft text-danger',
  info: 'border-accent bg-accent-soft text-accent',
};

const TONE_INACTIVE: Record<ChipDef['tone'], string> = {
  neutral: 'border-border bg-bg-surface text-text-muted hover:text-text-primary',
  primary: 'border-border bg-bg-surface text-text-muted hover:text-text-primary',
  warn: 'border-border bg-bg-surface text-text-muted hover:text-warn',
  danger: 'border-border bg-bg-surface text-text-muted hover:text-danger',
  info: 'border-border bg-bg-surface text-text-muted hover:text-accent',
};

export interface EventFilterProps {
  active: Set<EventKindFilter>;
  onToggle: (key: EventKindFilter) => void;
  counts?: Partial<Record<EventKindFilter, number>>;
}

export function EventFilter({ active, onToggle, counts }: EventFilterProps) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {CHIPS.map((c) => {
        const isActive = active.has(c.key);
        const cls = isActive ? TONE_ACTIVE[c.tone] : TONE_INACTIVE[c.tone];
        const count = counts?.[c.key];
        return (
          <button
            key={c.key}
            type="button"
            onClick={() => onToggle(c.key)}
            className={[
              'inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-2xs',
              'border font-mono uppercase tracking-wider transition-colors',
              cls,
            ].join(' ')}
          >
            <span>{c.label}</span>
            {typeof count === 'number' && (
              <span className="text-text-muted font-mono">
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
