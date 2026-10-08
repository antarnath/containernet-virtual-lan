// Table — the data-table primitive used by the router panel (phase 03),
// logs view (phase 07), and anywhere else we need to render a small
// list of rows with named columns.
//
// Design system contract (§6.4):
//   * Header row: bg-bg-surface-2, text-text-muted, uppercase 2xs
//     tracking, 10px font.
//   * Body cells: text-text-secondary default, text-text-primary for
//     the "data" column. Mono for IP / MAC / port content.
//   * Row hover: bg-bg-surface-2.
//   * No zebra striping (the design system explicitly bans it).
//   * Optional "outline" prop: 1.5px danger outline around a row
//     (used by the ARP table to mark an anomalous entry).
//
// All colors come from the tailwind tokens, not raw hex.

import { type ReactNode, type CSSProperties } from 'react';

export interface TableColumn<T> {
  key: string;
  label: string;
  /** Optional fixed width (e.g. "120px", "20%"). */
  width?: string;
  /** When true, render the cell in the mono font. */
  mono?: boolean;
  /** Optional formatter — receives the value + the full row. */
  render?: (value: unknown, row: T) => ReactNode;
  /** Tailwind class to apply to the cell (e.g. text colour). */
  className?: string;
}

export interface TableProps<T> {
  columns: TableColumn<T>[];
  rows: T[];
  /** ID field on each row (defaults to "id"). */
  rowKey?: keyof T;
  /** Predicate to mark a row as "outlined" (e.g. anomaly). */
  isOutlined?: (row: T) => boolean;
  /** Empty-state message. */
  emptyMessage?: string;
  /** Optional class for the wrapper. */
  className?: string;
  /** Optional fixed height for vertical scroll. */
  maxHeight?: string;
}

export function Table<T extends Record<string, unknown>>({
  columns,
  rows,
  rowKey = 'id' as keyof T,
  isOutlined,
  emptyMessage = 'no rows',
  className = '',
  maxHeight,
}: TableProps<T>) {
  if (rows.length === 0) {
    return (
      <div className={`text-xs text-text-muted italic ${className}`}>
        {emptyMessage}
      </div>
    );
  }

  const gridTemplate = columns
    .map((c) => c.width || 'minmax(0, 1fr)')
    .join(' ');

  return (
    <div
      className={`rounded-md border border-border overflow-hidden ${className}`}
      style={maxHeight ? { maxHeight, overflowY: 'auto' } : undefined}
    >
      {/* Header */}
      <div
        className="grid bg-bg-surface-2 text-2xs uppercase tracking-wider text-text-muted py-2 px-3 font-semibold"
        style={{ gridTemplateColumns: gridTemplate } as CSSProperties}
      >
        {columns.map((c) => (
          <div key={c.key} className="truncate">
            {c.label}
          </div>
        ))}
      </div>

      {/* Body */}
      <div>
        {rows.map((row, idx) => {
          const key = String(row[rowKey] ?? idx);
          const outlined = isOutlined?.(row);
          return (
            <div
              key={key}
              className={[
                'grid py-1.5 px-3 text-xs hover:bg-bg-surface-2 transition-colors duration-fast',
                outlined ? 'border-l-[1.5px] border-l-danger' : '',
                idx < rows.length - 1 ? 'border-b border-border-muted' : '',
              ].join(' ')}
              style={{ gridTemplateColumns: gridTemplate } as CSSProperties}
            >
              {columns.map((c) => {
                const v = row[c.key];
                const cell = c.render ? c.render(v, row) : (v as ReactNode);
                const mono = c.mono
                  ? 'font-mono'
                  : typeof v === 'string' && /\d+\.\d+\.\d+\.\d+/.test(v)
                  ? 'font-mono'
                  : '';
                return (
                  <div
                    key={c.key}
                    className={[
                      'truncate',
                      c.mono ? 'font-mono' : mono,
                      c.className || '',
                    ].join(' ')}
                    title={typeof cell === 'string' ? cell : undefined}
                  >
                    {cell ?? '—'}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
