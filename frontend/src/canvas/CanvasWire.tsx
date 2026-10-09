// CanvasWire — a custom React Flow edge that colors itself with the
// link's subnet color (auto-cycled 1..6 by the backend at creation).
// Selected wires thicken + glow. The wire label shows the derived
// subnet_cidr when known.
//
// Per design-system §6.8, when a packet crosses the wire, a small
// 4×4 filled circle in the packet's `protocol-*` color animates
// along the bezier from source to dest over 400ms. We listen on the
// realtime store's `packetsByLink` map; on every new packet whose
// link_id matches this edge, we enqueue a 400ms dot animation.
// Up to 5 dots can stack visually.

import { memo, useEffect, useRef, useState } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from 'reactflow';
import { useRealtimeStore, type RealtimePacketEvent } from '../store/realtimeStore';

// React Flow 11 doesn't export a `getPointOnBezier` helper, so we
// replicate the same control-point math (see BezierEdge.js in
// @reactflow/core) and evaluate the cubic bezier at parameter `t`.
// Default curvature matches `getBezierPath` (0.25).
function getPointOnBezier(args: {
  sourceX: number;
  sourceY: number;
  sourcePosition: EdgeProps['sourcePosition'];
  targetX: number;
  targetY: number;
  targetPosition: EdgeProps['targetPosition'];
  t: number;
  curvature?: number;
}): [number, number] {
  const {
    sourceX,
    sourceY,
    sourcePosition = 'bottom',
    targetX,
    targetY,
    targetPosition = 'top',
    t,
    curvature = 0.25,
  } = args;
  const c = curvature;
  const offsetFor = (delta: number) =>
    delta >= 0 ? 0.5 * delta : c * 25 * Math.sqrt(-delta);
  const ctrl = (pos: string, x1: number, y1: number, x2: number, y2: number) => {
    switch (pos) {
      case 'left':
        return [x1 - offsetFor(x1 - x2), y1];
      case 'right':
        return [x1 + offsetFor(x2 - x1), y1];
      case 'top':
        return [x1, y1 - offsetFor(y1 - y2)];
      case 'bottom':
      default:
        return [x1, y1 + offsetFor(y2 - y1)];
    }
  };
  const [c1x, c1y] = ctrl(sourcePosition, sourceX, sourceY, targetX, targetY);
  const [c2x, c2y] = ctrl(targetPosition, targetX, targetY, sourceX, sourceY);
  // Cubic bezier: P(t) = (1-t)³P0 + 3(1-t)²t P1 + 3(1-t)t² P2 + t³ P3
  const mt = 1 - t;
  const x =
    mt * mt * mt * sourceX +
    3 * mt * mt * t * c1x +
    3 * mt * t * t * c2x +
    t * t * t * targetX;
  const y =
    mt * mt * mt * sourceY +
    3 * mt * mt * t * c1y +
    3 * mt * t * t * c2y +
    t * t * t * targetY;
  return [x, y];
}

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

const PROTO_COLOR: Record<string, string> = {
  tcp: '#22d3ee',
  udp: '#a78bfa',
  icmp: '#34d399',
  arp: '#fbbf24',
  http: '#60a5fa',
  other: '#8aa0c4',
  attack: '#f87171',
};

interface Dot {
  start: number; // performance.now() when this dot started
  protocol: string;
  isAttack: boolean;
}

const DOT_DURATION_MS = 400;
const MAX_STACK = 5;

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
  const [edgePath, labelX, labelY, edgeCenterX, edgeCenterY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const colorIdx = data?.subnet_color_index ?? 1;
  const color = SUBNET_STROKE[colorIdx] ?? SUBNET_STROKE[1];

  // ─── live packet dot animation (phase 04) ───────────────────
  // We listen to the realtime store's per-link packet ring. Each
  // time a new packet for this edge's link arrives, we enqueue a
  // dot animation. The animation reads its current position from
  // the bezier every frame.
  const [dots, setDots] = useState<Dot[]>([]);
  const dotsRef = useRef<Dot[]>([]);
  dotsRef.current = dots;
  const lastSeenTsRef = useRef<number>(0);

  useEffect(() => {
    const unsub = useRealtimeStore.subscribe((state, prev) => {
      const ring = state.packetsByLink.get(id);
      if (!ring || ring.length === 0) return;
      const prevRing = prev.packetsByLink.get(id) ?? [];
      // Anything in `ring` past `prevRing.length` is new.
      for (let i = prevRing.length; i < ring.length; i++) {
        const p = ring[i];
        if ((p.ts_ns ?? 0) <= lastSeenTsRef.current) continue;
        lastSeenTsRef.current = p.ts_ns ?? 0;
        const newDot: Dot = {
          start: performance.now(),
          protocol: p.protocol,
          isAttack: p.src_node_kind === 'attacker',
        };
        const next = dotsRef.current.concat(newDot).slice(-MAX_STACK);
        dotsRef.current = next;
        setDots(next);
      }
    });
    return unsub;
  }, [id]);

  // Animation frame loop — drop dots whose 400ms is up.
  useEffect(() => {
    if (dots.length === 0) return;
    let raf = 0;
    const tick = () => {
      const now = performance.now();
      const alive = dotsRef.current.filter((d) => now - d.start < DOT_DURATION_MS);
      if (alive.length !== dotsRef.current.length) {
        dotsRef.current = alive;
        setDots(alive);
      }
      if (alive.length > 0) {
        // Force a re-render to advance positions.
        setDots((prev) => prev.slice());
        raf = requestAnimationFrame(tick);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [dots.length]);

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
      {/* Live packet dots — each one a 4×4 circle positioned along
          the bezier by `getPointOnBezier`. */}
      {dots.map((d, i) => {
        const t = Math.min(1, (performance.now() - d.start) / DOT_DURATION_MS);
        const [px, py] = getPointOnBezier({
          sourceX,
          sourceY,
          sourcePosition,
          targetX,
          targetY,
          targetPosition,
          // Begin with a small offset between stacked dots so they
          // don't perfectly overlap.
          t,
        });
        const c = d.isAttack ? PROTO_COLOR.attack : (PROTO_COLOR[d.protocol] ?? PROTO_COLOR.other);
        return (
          <circle
            key={`${d.start}-${i}`}
            cx={px}
            cy={py}
            r={2}
            fill={c}
            style={{ filter: `drop-shadow(0 0 4px ${c})` }}
          />
        );
      })}
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
