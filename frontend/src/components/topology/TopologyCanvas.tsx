// TopologyCanvas — wraps React Flow with project-aware node positioning
// and drag-stop persistence.
//
// Why we use `useNodesState` (NOT raw `useState`):
//   React Flow operates in "controlled" mode whenever you pass `nodes` as
//   a prop. In that mode EVERY position/dimension/select change has to be
//   round-tripped through `onNodesChange` or the visual position never
//   updates. The hand-rolled `useState + ignoring drag-moves` setup we had
//   before silently dropped the in-progress move updates, so dragging a
//   host did nothing on screen. `useNodesState` (from React Flow) wires
//   `onNodesChange` -> `applyNodeChanges` internally, which keeps the
//   local node positions in sync with React Flow's internal state for us.
//
// Position handling:
//   * If a host has a non-zero persisted position from the server, use it.
//   * Otherwise, fall back to a Dagre auto-layout for nodes that haven't
//     been placed yet.
//   * On drag stop, PATCH /api/projects/{id}/nodes/{host_id} with the new
//     coordinates — handled by projectStore.setNodePosition. During the
//     drag we just write the new position into local React Flow state so
//     the node follows the cursor; the PATCH fires only when the user
//     releases the mouse.
//
// We keep the real-time in-flight edge highlighting from before via
// useRealtimeStore.inFlightByProject[project.id] — scoped to this project
// so comms from a different project can't light up edges here. The legacy
// global TopologyView still uses the union across all projects.

import { useCallback, useEffect, useMemo, useRef } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
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

// Stable empty array so `useRealtimeStore` returns the same reference when
// no comms are in flight for this project — avoids spurious re-renders.
const EMPTY: never[] = [];

const NODE_WIDTH = 180;
const NODE_HEIGHT = 90;

// Dagre auto-layout: positions hosts that have never been placed. Takes
// only the hosts list (with their persisted positions) plus the edges
// list — nodes that already have a non-zero persisted position are pinned
// by giving them fixed coordinates we don't want dagre to move.
function autoLayout(
  hosts: ProjectDetail['hosts'],
  edges: ProjectDetail['edges'],
): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 90 });

  hosts.forEach((h) =>
    g.setNode(h.host_id, { width: NODE_WIDTH, height: NODE_HEIGHT }),
  );
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

// Build the initial RF nodes from the project's persisted state. Used as
// the initial value of `useNodesState` (first mount) and to re-sync the
// local state when the user navigates to a different project (the
// `lastProjectIdRef` effect above gates the call).
function buildInitialNodes(
  hosts: ProjectDetail['hosts'],
  edges: ProjectDetail['edges'],
): Node[] {
  const havePositions = hosts.some(
    (h) => h.position_x !== 0 || h.position_y !== 0,
  );
  const auto = havePositions
    ? new Map<string, { x: number; y: number }>()
    : autoLayout(hosts, edges);

  return hosts.map((h) => {
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
}

function buildInitialEdges(edges: ProjectDetail['edges']): Edge[] {
  return edges.map((e) => ({
    id: `${e.source_host_id}-${e.dest_host_id}`,
    source: e.source_host_id,
    target: e.dest_host_id,
    animated: false,
    type: 'smoothstep',
  }));
}

export default function TopologyCanvas({ project }: { project: ProjectDetail }) {
  const setNodePosition = useProjectStore((s) => s.setNodePosition);
  // Phase 07 — only light up edges for comms inside THIS project. The
  // realtime store buckets in-flight comms by project_id, so we read the
  // slice that belongs to the project we're rendering (the helper also
  // subscribes us to the map so the selector re-fires on changes).
  const inFlight = useRealtimeStore((s) =>
    s.inFlightByProject[project.id] ?? EMPTY,
  );
  const pushToast = useToastStore((s) => s.push);

  // React Flow's first-class controlled-state hook. Handles every
  // NodeChange variant (position, dimensions, select, remove) through
  // applyNodeChanges — including the in-progress position updates that
  // make the drag visibly follow the cursor.
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(
    buildInitialNodes(project.hosts, project.edges),
  );
  const [edges, , onEdgesChange] = useEdgesState<Edge>(
    buildInitialEdges(project.edges),
  );

  // Re-sync local state ONLY when the project ID changes (user navigated
  // from one project to another, or first mount). We intentionally don't
  // re-sync on every poll tick: doing so would clobber any in-progress
  // drag the moment the user lets go (the PATCH hasn't been ACKed yet),
  // and would also fight React Flow's internal drag state machine on
  // every poll. Status changes from the offline sweeper reach us via
  // WebSocket and apply directly to the hostStore, so the LED still
  // updates without re-positioning nodes.
  const lastProjectIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (lastProjectIdRef.current !== project.id) {
      lastProjectIdRef.current = project.id;
      setNodes(buildInitialNodes(project.hosts, project.edges));
    }
  }, [project.id, project.hosts, project.edges, setNodes]);

  // Apply in-flight edge highlights (real-time animations during comms).
  const styledEdges: Edge[] = useMemo(() => {
    return edges.map((e) => {
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
  }, [edges, inFlight]);

  // Persist position on drag stop. React Flow's useNodesState already
  // mirrors every position change into local state for us; here we just
  // catch the drag-end (a position change with `dragging: false`) and
  // PATCH the final coordinates to the server.
  //
  // We still let onNodesChange run for every change (including
  // `dragging: true` mid-move) so React Flow's internal node positions
  // stay in sync with the cursor.
  //
  // The drag-end frame often carries the `position` field inline, but
  // sometimes only the marker `{"type":"position","dragging":false}` is
  // emitted (the trailing settle frame from d3-drag). In that case we
  // fall back to the node's current position in our local `nodes` state.
  const wrappedOnNodesChange = useCallback(
    (changes: NodeChange[]) => {
      let dragDone: { id: string; x: number; y: number } | null = null;
      for (const c of changes) {
        if (c.type !== 'position') continue;
        if (c.dragging) continue; // mid-drag, not the final commit
        // Final commit. Prefer the position in the change if present,
        // otherwise look up the node's current position in local state
        // (useNodesState already applied the in-progress moves there).
        if (c.position) {
          dragDone = { id: c.id, x: c.position.x, y: c.position.y };
        } else {
          const cur = nodes.find((n) => n.id === c.id);
          if (cur && cur.position) {
            dragDone = { id: c.id, x: cur.position.x, y: cur.position.y };
          }
        }
      }
      // Let React Flow apply the changes to local state first.
      onNodesChange(changes);
      // Then, when the user releases the mouse, fire the persistence PATCH.
      if (dragDone) {
        const hostId = dragDone.id;
        setNodePosition(project.id, hostId, {
          position_x: dragDone.x,
          position_y: dragDone.y,
        }).catch((err) => {
          pushToast({
            kind: 'error',
            title: 'Could not save position',
            message: (err as Error).message,
          });
        });
      }
    },
    [nodes, onNodesChange, project.id, setNodePosition, pushToast],
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
        onNodesChange={wrappedOnNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        proOptions={{ hideAttribution: true }}
        minZoom={0.2}
        maxZoom={2}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
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
