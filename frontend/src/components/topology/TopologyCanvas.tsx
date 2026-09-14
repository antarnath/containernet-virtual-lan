// TopologyCanvas — wraps React Flow with project-aware node positioning
// and drag-stop persistence.
//
// Position handling:
//   * If a host has a non-zero persisted position from the server, use it.
//   * Otherwise, fall back to a Dagre auto-layout for nodes that haven't
//     been placed yet.
//   * On drag stop, PATCH /api/projects/{id}/nodes/{host_id} with the new
//     coordinates — handled by projectStore.setNodePosition.
//
// We keep the real-time in-flight edge highlighting from before via
// useRealtimeStore.inFlight — same as the global TopologyView.

import { useCallback, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeChange,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';

import { useRealtimeStore } from '../../store/realtimeStore';
import { useProjectStore } from '../../store/projectStore';
import { useToastStore } from '../../store/toastStore';
import type { ProjectDetail } from '../../types';
import HostNode from './HostNode';

const nodeTypes = { host: HostNode };

const NODE_WIDTH = 180;
const NODE_HEIGHT = 90;

function autoLayout(
  hosts: ProjectDetail['hosts'],
  edges: ProjectDetail['edges'],
): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 90 });

  hosts.forEach((h) => g.setNode(h.host_id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach((e) => g.setEdge(e.source_host_id, e.dest_host_id));
  dagre.layout(g);

  const out = new Map<string, { x: number; y: number }>();
  hosts.forEach((h) => {
    const p = g.node(h.host_id);
    if (p) {
      out.set(h.host_id, { x: p.x - NODE_WIDTH / 2, y: p.y - NODE_HEIGHT / 2 });
    }
  });
  return out;
}

export default function TopologyCanvas({ project }: { project: ProjectDetail }) {
  const setNodePosition = useProjectStore((s) => s.setNodePosition);
  const inFlight = useRealtimeStore((s) => s.inFlight);
  const pushToast = useToastStore((s) => s.push);

  // Build {nodes, edges} for React Flow. Positions come from the DB; only
  // hosts that have never been placed get a Dagre-assigned default.
  const { nodes, edges } = useMemo<{ nodes: Node[]; edges: Edge[] }>(() => {
    const havePositions = project.hosts.some(
      (h) => h.position_x !== 0 || h.position_y !== 0,
    );

    const auto = havePositions
      ? new Map<string, { x: number; y: number }>()
      : autoLayout(project.hosts, project.edges);

    const rfNodes: Node[] = project.hosts.map((h) => {
      const useStored = h.position_x !== 0 || h.position_y !== 0;
      const pos = useStored
        ? { x: h.position_x, y: h.position_y }
        : auto.get(h.host_id) ?? { x: 0, y: 0 };

      return {
        id: h.host_id,
        type: 'host',
        data: {
          label: h.hostname,
          ip: h.ip_address,
          status: h.status,
        },
        position: pos,
        draggable: true,
      };
    });

    const rfEdges: Edge[] = project.edges.map((e) => ({
      id: `${e.source_host_id}-${e.dest_host_id}`,
      source: e.source_host_id,
      target: e.dest_host_id,
      animated: false,
      type: 'smoothstep',
    }));

    return { nodes: rfNodes, edges: rfEdges };
  }, [project]);

  // Apply in-flight edge highlights (real-time animations during comms).
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
        style: { stroke: '#22c55e', strokeWidth: 4 },
        label: '◀ data flowing',
        labelStyle: { fill: '#22c55e', fontWeight: 700, fontSize: 11 },
        labelBgStyle: { fill: '#0b1120' },
        labelBgPadding: [4, 2],
        zIndex: 1000,
      };
    }
    return {
      ...e,
      animated: false,
      style: { stroke: '#3b82f6', strokeWidth: 1.5, opacity: 0.6 },
    };
  });

  // Persist position on drag stop. React Flow fires onNodeDragStop with
  // a NodeChange[] — we filter for position changes only.
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      for (const change of changes) {
        if (change.type === 'position' && change.dragging === false && change.position) {
          const hostId = change.id;
          // Fire-and-forget; the store does optimistic local update first.
          setNodePosition(project.id, hostId, {
            position_x: change.position.x,
            position_y: change.position.y,
          }).catch((err) => {
            pushToast({
              kind: 'error',
              title: 'Could not save position',
              message: (err as Error).message,
            });
          });
        }
      }
    },
    [project.id, setNodePosition, pushToast],
  );

  if (project.hosts.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted">
        This project has no hosts yet.
      </div>
    );
  }

  return (
    <div className="w-full h-full bg-bg rounded-lg border border-border overflow-hidden relative">
      <ReactFlow
        nodes={nodes}
        edges={styledEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        fitView
        proOptions={{ hideAttribution: true }}
        minZoom={0.2}
        maxZoom={2}
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
        <span className="text-muted">
          · drag hosts to rearrange
        </span>
      </div>
    </div>
  );
}
