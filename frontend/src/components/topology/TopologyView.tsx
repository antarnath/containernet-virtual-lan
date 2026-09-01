// The main interactive topology graph (React Flow + Dagre layout).

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
import { buildLayout } from '../../utils/layout';
import HostNode from './HostNode';

const nodeTypes = { host: HostNode };

export default function TopologyView() {
  const topology = useHostStore((s) => s.topology);

  const { nodes, edges } = useMemo<
    { nodes: Node[]; edges: Edge[] }
  >(() => {
    if (!topology || topology.nodes.length === 0) {
      return { nodes: [], edges: [] };
    }
    return buildLayout(topology);
  }, [topology]);

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
        edges={edges}
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
    </div>
  );
}
