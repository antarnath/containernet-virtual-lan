// CanvasWire — a custom React Flow edge that colors itself with the
// link's subnet color (auto-cycled 1..6 by the backend at creation).
// Selected wires thicken + glow. The wire label shows the derived
// subnet_cidr when known.

import { memo } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from 'reactflow';

export interface CanvasEdgeData {
  subnet_cidr: string | null;
  subnet_color_index: number; // 1..6
}

// Six subnet colors, mapped to the Tailwind tokens defined in the
// design system. The numeric index is what the backend stores; the
// color below is what we draw.
const SUBNET_STROKE: Record<number, string> = {
  1: '#22d3ee', // cyan
  2: '#a78bfa', // violet
  3: '#34d399', // emerald
  4: '#fbbf24', // amber
  5: '#f472b6', // pink
  6: '#60a5fa', // sky
};

function CanvasEdgeImpl({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps<CanvasEdgeData>) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const colorIdx = data?.subnet_color_index ?? 1;
  const color = SUBNET_STROKE[colorIdx] ?? SUBNET_STROKE[1];

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: color,
          strokeWidth: selected ? 3 : 2,
          filter: selected
            ? `drop-shadow(0 0 6px ${color}80)`
            : `drop-shadow(0 0 2px ${color}40)`,
        }}
      />
      {data?.subnet_cidr && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'all',
              borderColor: color,
            }}
            className={[
              'px-1.5 py-0.5 rounded text-2xs font-mono',
              'bg-bg-surface border',
              'shadow-sm',
            ].join(' ')}
          >
            <span style={{ color }}>{data.subnet_cidr}</span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const CanvasEdge = memo(CanvasEdgeImpl);
export default CanvasEdge;
