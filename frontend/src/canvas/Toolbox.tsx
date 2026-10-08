// Toolbox — the left rail of the canvas. Each row is a "drop a node"
// button for one of the 5 node kinds. The visual style matches the
// NodeIcon: Cisco silhouette in the kind's color, name + one-liner.
//
// Phase 01 only — drag from the rail to the canvas and a new node
// is created via the API. The "add at center" fallback handles the
// common case (one click drops a node at the current viewport center).

import { type DragEvent } from 'react';
import type { NodeKind } from '../types';
import { NodeIcon } from '../components/icons';

interface ToolboxProps {
  /** Called when the user drops a node over the canvas. */
  onDropKind: (kind: NodeKind, canvasX: number, canvasY: number) => void;
  /** Add a node at the center of the current viewport (the click fallback). */
  onAddAtCenter: (kind: NodeKind) => void;
  disabled?: boolean;
}

interface KindMeta {
  kind: NodeKind;
  label: string;
  blurb: string;
  textClass: string;
}

const KIND_META: KindMeta[] = [
  {
    kind: 'host',
    label: 'Host',
    blurb: 'PC / endpoint',
    textClass: 'text-node-host',
  },
  {
    kind: 'switch',
    label: 'Switch',
    blurb: 'L2 bridge',
    textClass: 'text-node-switch',
  },
  {
    kind: 'router',
    label: 'Router',
    blurb: 'L3 gateway',
    textClass: 'text-node-router',
  },
  {
    kind: 'server',
    label: 'Server',
    blurb: 'service host',
    textClass: 'text-node-server',
  },
  {
    kind: 'attacker',
    label: 'Attacker',
    blurb: 'threat actor',
    textClass: 'text-node-attacker',
  },
];

const DRAG_MIME = 'application/x-containernet-node-kind';

function ToolboxRow({
  meta,
  disabled,
  onAddAtCenter,
}: {
  meta: KindMeta;
  disabled?: boolean;
  onAddAtCenter: (kind: NodeKind) => void;
}) {
  const onDragStart = (e: DragEvent<HTMLButtonElement>) => {
    e.dataTransfer.setData(DRAG_MIME, meta.kind);
    e.dataTransfer.effectAllowed = 'copy';
  };

  return (
    <button
      type="button"
      draggable={!disabled}
      onDragStart={onDragStart}
      onClick={() => onAddAtCenter(meta.kind)}
      disabled={disabled}
      className={[
        'group w-full flex items-center gap-2.5 px-2 py-2 rounded-md',
        'bg-bg-surface-2 border border-border',
        'hover:border-border-strong hover:bg-bg-surface',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        'transition-colors duration-fast cursor-grab active:cursor-grabbing',
        'text-left',
      ].join(' ')}
      title={`Drag onto the canvas, or click to add at the center`}
    >
      <div className={['flex-shrink-0', meta.textClass].join(' ')}>
        <NodeIcon kind={meta.kind} size={22} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold text-text-primary truncate">
          {meta.label}
        </div>
        <div className="text-2xs text-text-muted truncate">{meta.blurb}</div>
      </div>
    </button>
  );
}

export function Toolbox({ onDropKind, onAddAtCenter, disabled }: ToolboxProps) {
  return (
    <aside className="w-44 flex-shrink-0 bg-bg-surface border-r border-border flex flex-col">
      <div className="px-3 py-2.5 border-b border-border">
        <div className="text-2xs uppercase tracking-wider text-text-muted">
          Toolbox
        </div>
        <div className="text-xs text-text-secondary mt-0.5">
          Drag onto the canvas
        </div>
      </div>
      <div className="flex-1 p-2 space-y-1.5 overflow-y-auto">
        {KIND_META.map((m) => (
          <ToolboxRow
            key={m.kind}
            meta={m}
            disabled={disabled}
            onAddAtCenter={onAddAtCenter}
          />
        ))}
      </div>
      <div className="px-3 py-2 border-t border-border text-2xs text-text-muted">
        <span className="block">Click = drop at center</span>
        <span className="block">Drag = drop where released</span>
      </div>
      {/* Expose the MIME so the canvas can read it from dataTransfer. */}
      <span className="hidden" aria-hidden>{DRAG_MIME}</span>
    </aside>
  );
}

export { DRAG_MIME };
