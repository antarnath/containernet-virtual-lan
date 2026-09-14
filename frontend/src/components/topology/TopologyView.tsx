// The main interactive topology graph (React Flow + Dagre layout).
// Active in-flight communications light up their corresponding edges
// in bright green so the data flow is visible in real time.

import { useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { useHostStore } from '../../store/hostStore';
import { useInFlight } from '../../store/realtimeStore';
import { buildLayout } from '../../utils/layout';
import HostNode from './HostNode';

const nodeTypes = { host: HostNode };

export default function TopologyView() {
  const topology = useHostStore((s) => s.topology);
  // Phase 07 — legacy global view. No project context, so we read the
  // union of every project's in-flight comms via the helper hook. New
  // project-aware TopologyCanvas uses the per-project slice instead.
  const inFlight = useInFlight();

  const { nodes, edges } = useMemo<
    { nodes: Node[]; edges: Edge[] }
  >(() => {
    if (!topology || topology.nodes.length === 0) {
      return { nodes: [], edges: [] };
    }
    return buildLayout(topology);
  }, [topology]);

  // Style edges: brighten any edge that corresponds to an in-flight comm.
  // We compare in both directions because edges are unordered in our graph.
  const styledEdges: Edge[] = edges.map((e) => {
    const active = inFlight.some(
      (c) =>
        (c.source === e.source && c.target === e.target) ||
        (c.source === e.target && c.target === e.source),
    );
    if (active) {
      return {
        ...e,
        animated: true,
        style: {
          stroke: '#22c55e',
          strokeWidth: 4,
        },
        label: '◀ data flowing',
        labelStyle: { fill: '#22c55e', fontWeight: 700, fontSize: 11 },
        labelBgStyle: { fill: '#0b1120' },
        labelBgPadding: [4, 2],
        zIndex: 1000,
      };
    }
    // Idle edges: dim, no animation (the default React Flow dashes are
    // distracting when no comm is happening — clear visual hierarchy).
    return {
      ...e,
      animated: false,
      style: { stroke: '#3b82f6', strokeWidth: 1.5, opacity: 0.6 },
    };
  });

  if (!topology) {
    return (
      <div className="flex items-center justify-center h-full text-muted">
        Loading topology…
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted">
        No hosts discovered yet. Waiting for heartbeats…
      </div>
    );
  }

  return (
    <div className="w-full h-full bg-bg rounded-lg border border-border overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={styledEdges}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1f2937" gap={20} />
        <Controls />
        <MiniMap
          nodeColor={(n) => {
            const s = (n.data as { status?: string })?.status;
            return s === 'online'
              ? '#22c55e'
              : s === 'offline'
              ? '#ef4444'
              : '#eab308';
          }}
          maskColor="rgba(11,17,32,0.7)"
        />
      </ReactFlow>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-panel/90 border border-border rounded px-3 py-2 text-xs text-muted flex gap-4">
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-0.5 bg-blue-500"></span>
          idle
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-0.5 bg-online"></span>
          data flowing ({inFlight.length})
        </span>
      </div>
    </div>
  );
}