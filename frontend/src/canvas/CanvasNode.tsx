// CanvasNode — a single node on the M4 canvas. Each one shows the
// kind icon (host / switch / router / server / attacker), the user-given
// name, the container status pill, and a small "interfaces" sub-row.
// Each interface is a React Flow handle so users can wire two
// interfaces together by dragging from one handle to another.
//
// The whole card picks its color from the node-kind palette
// (`text-node-host` etc.); selection, hover, and dragging add extra
// rings/shadows via the design-system tokens.
//
// Phase 03: a node with an open anomaly gets a 1.5px `warn` outline
// (per design-system §6.7). The Canvas owns a Set<nodeId> of "anomalous"
// nodes, computed from the realtime store, and stamps it into the
// node's data so this component is pure.

import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { NodeIcon } from '../components/icons';
import { StatusPill } from '../components/ui';
import type { ContainerStatus, NodeKind, ProjectInterface } from '../types';

export interface CanvasNodeData {
  kind: NodeKind;
  name: string;
  container_status: ContainerStatus;
  attack_mode: string | null;
  interfaces: ProjectInterface[];
  /** Phase 03: this node has an open anomaly. */
  has_anomaly?: boolean;
  /** Phase 06: this attacker has an active signal in the last 10s. */
  has_active_attack?: boolean;
}

// Map a kind to the design-system text class for the silhouette.
const KIND_TEXT: Record<NodeKind, string> = {
  host: 'text-node-host',
  switch: 'text-node-switch',
  router: 'text-node-router',
  server: 'text-node-server',
  attacker: 'text-node-attacker',
};

// Container status → StatusPill tone.
const STATUS_TONE: Record<ContainerStatus, 'idle' | 'starting' | 'running' | 'error' | 'stopped'> = {
  idle: 'idle',
  starting: 'starting',
  running: 'running',
  stopped: 'stopped',
  error: 'error',
};

function CanvasNodeImpl({ data, selected }: NodeProps<CanvasNodeData>) {
  const { kind, name, container_status, attack_mode, interfaces, has_anomaly, has_active_attack } = data;
  const anomaly = !!has_anomaly;
  const attacking = !!has_active_attack;

  // Border + outline priority: selected > attack > anomaly > hover.
  // The attack state is sticky and survives selection/anomaly.
  const borderClass = selected
    ? 'border-accent shadow-glow-accent'
    : attacking
    ? 'border-danger shadow-glow-danger animate-pulse'
    : anomaly
    ? 'border-warn'
    : 'border-border hover:border-border-strong shadow-md';

  return (
    <div
      className={[
        'min-w-[180px] rounded-lg overflow-visible',
        'bg-bg-surface border-2 transition-shadow duration-fast',
        // Bug #49 part 2 — the React Flow Controls panel (z=5)
        // and the MiniMap (z=5) sit on top of node handles that
        // happen to render in the bottom-right region of the canvas
        // and steal their pointer events. Lifting the node to z=20
        // (above the panel) makes the handle click-reachable. We
        // also flip `overflow-hidden` to `overflow-visible` so the
        // handles can extend past the node's bounding box.
        'relative z-20',
        borderClass,
      ].join(' ')}
    >
      {/* Top: icon + name + status pill */}
      <div className="flex items-center gap-2.5 px-3 py-2.5 border-b border-border">
        <div className={['flex-shrink-0', KIND_TEXT[kind]].join(' ')}>
          <NodeIcon kind={kind} size={28} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-text-primary truncate">
            {name}
          </div>
          <div className="text-2xs uppercase tracking-wider text-text-muted">
            {kind}
            {kind === 'attacker' && attack_mode ? ` · ${attack_mode}` : ''}
          </div>
        </div>
        <div className="flex-shrink-0">
          <StatusPill tone={STATUS_TONE[container_status]} pulse={container_status === 'running'}>
            {container_status}
          </StatusPill>
        </div>
      </div>

      {/* Bottom: interface list with handles */}
      <div className="px-2 py-1.5">
        {interfaces.length === 0 ? (
          <div className="text-2xs text-text-muted text-center py-1">
            no interfaces
          </div>
        ) : (
          interfaces.map((iface, idx) => (
            <div
              key={iface.id}
              className="relative flex items-center justify-between gap-2 h-7"
            >
              {/* Each interface gets FOUR handles — a source and a
                  target on BOTH the left and right side. This is the
                  "wires always connect" fix (bug #49): with only one
                  source on the left and one target on the right,
                  dragging router(right-target)→host(left-target) is
                  target→source which React Flow silently rejects.
                  Giving every side both source + target roles means
                  a drag from any side to any other side always
                  produces a valid source→target pair. The source
                  and target on the same side are stacked vertically
                  (top: 40% / top: 60%) so both are hover-reachable
                  — placing them at the exact same point would let
                  only one win the pointer event. The link's
                  sourceHandle/targetHandle stores the full handle
                  id; the onConnect handler in Canvas.tsx strips
                  the `::src_l` / `::src_r` / `::tgt_l` / `::tgt_r`
                  suffix to recover the backend iface id. */}
              {/* Render order matters: the LAST handle in DOM at a
                  given position wins pointer events. We want the
                  SOURCE to be on top so the user can click-and-drag
                  it (the target is the drop receiver — it doesn't
                  need to be clickable). So render target first,
                  then source. Pair them: left-target, left-source,
                  right-target, right-source. */}
              <Handle
                id={`${iface.id}::tgt_l`}
                type="target"
                position={Position.Left}
                className="!w-2.5 !h-2.5 !bg-transparent !border-2 !border-accent"
                style={{ top: '60%', left: -5 }}
              />
              <Handle
                id={`${iface.id}::src_l`}
                type="source"
                position={Position.Left}
                className="!w-2.5 !h-2.5 !bg-accent !border-2 !border-bg-surface"
                style={{ top: '40%', left: -5 }}
              />
              <Handle
                id={`${iface.id}::tgt_r`}
                type="target"
                position={Position.Right}
                className="!w-2.5 !h-2.5 !bg-transparent !border-2 !border-accent"
                style={{ top: '60%', right: -5 }}
              />
              <Handle
                id={`${iface.id}::src_r`}
                type="source"
                position={Position.Right}
                className="!w-2.5 !h-2.5 !bg-accent !border-2 !border-bg-surface"
                style={{ top: '40%', right: -5 }}
              />
              <div className="text-xs text-text-secondary truncate pl-1">
                {iface.name}
              </div>
              <div className="text-2xs font-mono text-text-muted truncate pr-1">
                {iface.ip_address ?? (
                  <span className="italic text-text-muted/60">no ip</span>
                )}
              </div>
              {/* The index hint for handle positioning when many interfaces
                  are stacked; React Flow auto-distributes but we keep this
                  for visual symmetry. */}
              <span className="hidden">{idx}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export const CanvasNode = memo(CanvasNodeImpl);
export default CanvasNode;
