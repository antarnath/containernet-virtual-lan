// Canvas — the M4 React Flow surface. Owns:
//   • drop-from-Toolbox → addNode
//   • connect (handle-to-handle) → addLink
//   • drag-end (position) → updateNode (debounced 300ms)
//   • pan/zoom → setViewport (debounced 600ms)
//   • selection / deletion (delete / backspace on a node or edge)
//   • click-to-open — clicking a router node fires `onOpenNode` so
//     the parent can mount the RouterPanel (phase 03). Clicking a
//     wire fires `onOpenLink` so the parent can navigate to the
//     wire view (phase 04).
//
// All CRUD goes through the project store. The store is the single
// source of truth; React Flow's internal node state is derived from
// `current.nodes` / `current.links` on every render via memoized
// conversion functions.

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from 'react';
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlowProvider,
  addEdge,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type EdgeMouseHandler,
  type Node,
  type NodeChange,
  type NodeMouseHandler,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
  type ReactFlowInstance,
  type ReactFlowProps,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { useProjectStore } from '../store/projectStore';
import { useRealtimeStore } from '../store/realtimeStore';
import { toast } from '../components/ui';
import type {
  AttackMode,
  NodeKind,
  ProjectInterface,
  ProjectLink,
  ProjectNode,
} from '../types';
import { CanvasNode, type CanvasNodeData } from './CanvasNode';
import { CanvasEdge, type CanvasEdgeData } from './CanvasWire';
import { Toolbox, DRAG_MIME } from './Toolbox';

const NODE_TYPES = { canvasNode: CanvasNode };
const EDGE_TYPES = { canvasEdge: CanvasEdge };

export interface OpenNodePayload {
  nodeId: string;
  nodeName: string;
  nodeKind: NodeKind;
  containerStatus: string;
}

// ─── conversion helpers ─────────────────────────────────────────────────

function nodeToFlow(
  n: ProjectNode,
  hasAnomaly: boolean,
  hasActiveAttack: boolean,
): Node<CanvasNodeData> {
  return {
    id: n.id,
    type: 'canvasNode',
    position: { x: n.canvas_x, y: n.canvas_y },
    data: {
      kind: n.kind,
      name: n.name,
      container_status: n.container_status,
      attack_mode: n.attack_mode,
      interfaces: n.interfaces,
      has_anomaly: hasAnomaly,
      has_active_attack: hasActiveAttack,
    },
  };
}

function linkToFlow(
  l: ProjectLink,
  ifaceToNode: Map<string, string>,
): Edge<CanvasEdgeData> {
  // React Flow needs the *node id* in `source`/`target`, and the
  // *handle id* (our iface id + role + side suffix) in
  // `sourceHandle`/`targetHandle`. The link's `iface_a_id` /
  // `iface_b_id` are backend iface ids, so we resolve the parent
  // node id from a pre-built map. The handle id has to match one
  // of the four handles CanvasNode renders
  // (`::src_l` / `::tgt_l` / `::src_r` / `::tgt_r`) — we pick the
  // left-side source and right-side target by default, but React
  // Flow only uses these for the SVG handle lookup, so either
  // side works.
  const sourceNode = ifaceToNode.get(l.iface_a_id);
  const targetNode = ifaceToNode.get(l.iface_b_id);
  if (!sourceNode || !targetNode) {
    return null as unknown as Edge<CanvasEdgeData>;
  }
  return {
    id: l.id,
    source: sourceNode,
    target: targetNode,
    // Match one of the 4 handles CanvasNode renders for each iface
    // (bug #49). The actual handle used at draw time doesn't matter
    // as long as it exists on the node.
    sourceHandle: `${l.iface_a_id}::src_l`,
    targetHandle: `${l.iface_b_id}::tgt_r`,
    type: 'canvasEdge',
    data: {
      subnet_cidr: l.subnet_cidr,
      subnet_color_index: l.subnet_color_index,
    },
  };
}

// ─── default canvas position when a new node has no x/y from the user ───

function randomCanvasPosition(): { canvas_x: number; canvas_y: number } {
  // Sprinkle new nodes in a 200×200 box near the origin so a fresh
  // canvas doesn't drop everything on top of itself.
  return {
    canvas_x: 100 + Math.random() * 200,
    canvas_y: 100 + Math.random() * 200,
  };
}

// ─── Main component (inside provider) ───────────────────────────────────

function CanvasInner({
  projectId,
  onOpenNode,
  onOpenLink,
}: {
  projectId: string;
  onOpenNode?: (p: OpenNodePayload) => void;
  onOpenLink?: (linkId: string) => void;
}) {
  const current = useProjectStore((s) => s.current);
  const fetchProject = useProjectStore((s) => s.fetchProject);
  const addNode = useProjectStore((s) => s.addNode);
  const moveNode = useProjectStore((s) => s.moveNode);
  const addLink = useProjectStore((s) => s.addLink);
  const deleteNode = useProjectStore((s) => s.deleteNode);
  const deleteLink = useProjectStore((s) => s.deleteLink);
  const setViewport = useProjectStore((s) => s.setViewport);
  // Phase 03: the set of nodes with an open anomaly, so the canvas
  // can outline them. Subscribing to `anomalies` here is what
  // re-renders the affected nodes when the WS delivers a new event.
  const anomalies = useRealtimeStore((s) => s.anomalies);
  const dismissedIds = useRealtimeStore((s) => s.dismissedIds);
  const activeAttackers = useRealtimeStore((s) => s.activeAttackers);
  const anomalousNodeIds = useMemo(() => {
    const s = new Set<string>();
    for (const a of anomalies) {
      if (a.resolved_at) continue;
      if (dismissedIds.has(a.id)) continue;
      if (a.node_id) s.add(a.node_id);
    }
    return s;
  }, [anomalies, dismissedIds]);

  // Local mirror of the React Flow node/edge state. We seed it from
  // `current` whenever the server's view of the world changes
  // (e.g. after a refetch or after an external mutation).
  const [nodes, setNodes] = useState<Node<CanvasNodeData>[]>([]);
  const [edges, setEdges] = useState<Edge<CanvasEdgeData>[]>([]);

  // Hydrate from the project store on first mount + whenever the
  // server-side state changes. Also re-runs when the anomaly set
  // changes so the warn outline appears/disappears in real time,
  // and when the active-attacker set changes (phase 06 — red ring).
  useEffect(() => {
    if (!current) return;
    if (current.id !== projectId) return;
    setNodes(
      current.nodes.map((n) =>
        nodeToFlow(
          n,
          anomalousNodeIds.has(n.id),
          activeAttackers.has(n.id),
        ),
      ),
    );
    // Build the iface-id → node-id map so linkToFlow can resolve
    // React Flow's source/target (which must be node ids).
    const ifaceToNode = new Map<string, string>();
    for (const n of current.nodes) {
      for (const i of n.interfaces) {
        ifaceToNode.set(i.id, n.id);
      }
    }
    setEdges(
      current.links
        .map((l) => linkToFlow(l, ifaceToNode))
        .filter((e): e is Edge<CanvasEdgeData> => e !== null),
    );
    // Debug: expose to window so we can inspect edges in devtools.
    if (typeof window !== 'undefined') {
      (window as unknown as { __cnDebug: unknown }).__cnDebug = {
        nodes: current.nodes.map((n) => ({ id: n.id, name: n.name, x: n.canvas_x, y: n.canvas_y })),
        links: current.links.map((l) => ({ id: l.id, a: l.iface_a_id, b: l.iface_b_id, subnet: l.subnet_cidr })),
        ifaceMap: Array.from(ifaceToNode.entries()),
      };
      // eslint-disable-next-line no-console
      console.log('[Canvas] hydrated', {
        nodes: current.nodes.length,
        links: current.links.length,
        edges: (window as unknown as { __cnDebug: { edges?: unknown } }).__cnDebug,
      });
    }
  }, [current, projectId, anomalousNodeIds, activeAttackers]);

  // If the project is missing on first mount, fetch it.
  useEffect(() => {
    if (!current) {
      void fetchProject(projectId);
    }
  }, [current, fetchProject, projectId]);

  // M4 phase 08 — prune expired message trails every 500ms so the
  // canvas wires don't keep glowing after the data has stopped
  // flowing. The store's prune is a no-op if nothing is active.
  useEffect(() => {
    const t = window.setInterval(() => {
      useRealtimeStore.getState().pruneMessageTrails();
      useRealtimeStore.getState().pruneActiveAttackers();
    }, 500);
    return () => window.clearInterval(t);
  }, []);

  // ─── drop from toolbox ──────────────────────────────────────
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const rfInstance = useRef<ReactFlowInstance | null>(null);

  const onDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }, []);

  const onDrop = useCallback(
    async (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      const kind = e.dataTransfer.getData(DRAG_MIME) as NodeKind | '';
      if (!kind) return;
      const bounds = wrapperRef.current?.getBoundingClientRect();
      if (!bounds || !rfInstance.current) {
        // Fallback: drop at the origin.
        await addNode(projectId, { kind, ...randomCanvasPosition() });
        return;
      }
      const pos = rfInstance.current.screenToFlowPosition({
        x: e.clientX,
        y: e.clientY,
      });
      await addNode(projectId, {
        kind,
        canvas_x: pos.x,
        canvas_y: pos.y,
      });
    },
    [addNode, projectId],
  );

  const onAddAtCenter = useCallback(
    async (kind: NodeKind) => {
      if (rfInstance.current) {
        const center = rfInstance.current.screenToFlowPosition({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2,
        });
        await addNode(projectId, {
          kind,
          canvas_x: center.x,
          canvas_y: center.y,
        });
        return;
      }
      await addNode(projectId, { kind, ...randomCanvasPosition() });
    },
    [addNode, projectId],
  );

  // ─── node changes (drag, select, remove) ────────────────────
  // The latest position per node id — we update this on every
  // position change so we have the final coords ready when React
  // Flow fires the drag-end event (which arrives WITHOUT a
  // `position` field — see `updateNodePositions` in
  // @reactflow/core: the drag-stop call passes
  // `positionChanged=false`, so the change object is just
  // `{id, type: 'position', dragging: false}`). Without this
  // tracker we'd save undefined. (bug #46 follow-on.)
  const lastPositionRef = useRef<Map<string, { x: number; y: number }>>(
    new Map(),
  );

  const onNodesChange: OnNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setNodes((nds) => applyNodeChanges(changes, nds) as Node<CanvasNodeData>[]);

      for (const c of changes) {
        if (c.type === 'position') {
          // While dragging, remember the latest position. When the
          // drag ends, `c.position` is undefined — fall back to
          // the tracker.
          if (c.position) {
            lastPositionRef.current.set(c.id, c.position);
          }
          if (c.dragging === false) {
            const finalPos =
              c.position ?? lastPositionRef.current.get(c.id);
            if (finalPos) {
              lastPositionRef.current.delete(c.id);
              void moveNode(projectId, c.id, {
                canvas_x: finalPos.x,
                canvas_y: finalPos.y,
              });
            }
          }
        }
      }
    },
    [moveNode, projectId],
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      // We need to wrap setEdges because addEdge's typing is too
      // narrow for our generic data type. The implementation is
      // identical to React Flow's own setEdges for these change kinds.
      setEdges((eds) => {
        let next = eds;
        for (const c of changes) {
          if (c.type === 'remove') {
            next = next.filter((e) => e.id !== c.id);
          }
        }
        return next;
      });
      for (const c of changes) {
        if (c.type === 'remove') {
          // Edges are identified by link id; the source/target is
          // the iface id but we want to know which link was removed.
          const edge = edges.find((e) => e.id === c.id);
          if (edge) void deleteLink(projectId, edge.id);
        }
      }
    },
    [deleteLink, edges, projectId],
  );

  // ─── wire two interfaces together ───────────────────────────
  const onConnect: OnConnect = useCallback(
    async (params: Connection) => {
      if (!params.source || !params.target) return;
      // React Flow's `Connection` has `source` / `target` as NODE ids
      // and `sourceHandle` / `targetHandle` as HANDLE ids. Our
      // handle id is `${iface.id}::${src|tgt}_{l|r}` (bug #49 — 4
      // handles per iface so direction doesn't matter). Strip the
      // role+side suffix from the *handle* ids to recover the
      // backend iface id, which is what `addLink` expects.
      const stripRole = (handleId: string) =>
        handleId.replace(/::(src|tgt)_[lr]$/, '');
      const ifaceA = params.sourceHandle ? stripRole(params.sourceHandle) : '';
      const ifaceB = params.targetHandle ? stripRole(params.targetHandle) : '';
      if (!ifaceA || !ifaceB) {
        toast.warning('Invalid wire', 'Missing interface id.');
        return;
      }
      if (ifaceA === ifaceB) {
        toast.warning('Invalid wire', 'An interface cannot wire to itself.');
        return;
      }
      try {
        await addLink(projectId, {
          iface_a_id: ifaceA,
          iface_b_id: ifaceB,
        });
        toast.success('Wire added', 'Two interfaces connected.');
      } catch (e) {
        const msg = (e as Error & { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        toast.error('Could not wire', msg ?? (e as Error).message);
      }
    },
    [addLink, projectId],
  );

  // ─── click to open a node's panel (phase 03: routers; phase 05:
  //     host/server/attacker). Switches still no-op — they're
  //     transparent L2 devices with no agent. ───────────────────
  const onNodeClick: NodeMouseHandler = useCallback(
    (_e, node) => {
      if (!onOpenNode) return;
      const data = node.data as CanvasNodeData | undefined;
      if (!data) return;
      // Switches have no agent, so the panel would be empty.
      if (data.kind === 'switch') return;
      onOpenNode({
        nodeId: node.id,
        nodeName: data.name,
        nodeKind: data.kind,
        containerStatus: data.container_status,
      });
    },
    [onOpenNode],
  );

  // ─── click to open a wire's view (phase 04) ───────────────────
  const onEdgeClick: EdgeMouseHandler = useCallback(
    (_e, edge) => {
      if (!onOpenLink) return;
      onOpenLink(edge.id);
    },
    [onOpenLink],
  );

  // Debounced viewport save.
  const viewportTimer = useRef<number | null>(null);
  const onMoveEnd: NonNullable<ReactFlowProps['onMoveEnd']> = useCallback(
    (_e, viewport) => {
      if (viewportTimer.current) {
        clearTimeout(viewportTimer.current);
      }
      viewportTimer.current = window.setTimeout(() => {
        void setViewport(projectId, {
          viewport_x: viewport.x,
          viewport_y: viewport.y,
          viewport_zoom: viewport.zoom,
        });
      }, 600);
    },
    [projectId, setViewport],
  );

  // Keyboard delete — Backspace / Delete with a selected node or edge.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Delete' && e.key !== 'Backspace') return;
      // Don't intercept while the user is typing in a field.
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      // Find the first selected node / edge.
      const selectedNode = nodes.find((n) => n.selected);
      if (selectedNode) {
        e.preventDefault();
        void (async () => {
          try {
            await deleteNode(projectId, selectedNode.id);
          } catch (err) {
            const detail = (err as Error & {
              response?: { data?: { detail?: { message?: string } | string } };
            }).response?.data?.detail;
            const msg =
              typeof detail === 'object' && detail
                ? detail.message ?? JSON.stringify(detail)
                : (detail as string) ?? (err as Error).message;
            toast.error('Could not delete node', msg);
          }
        })();
        return;
      }
      const selectedEdge = edges.find((e2) => e2.selected);
      if (selectedEdge) {
        e.preventDefault();
        void deleteLink(projectId, selectedEdge.id);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [nodes, edges, deleteNode, deleteLink, projectId]);

  // ─── render ─────────────────────────────────────────────────
  const isEmpty = nodes.length === 0;

  return (
    <div className="flex h-full w-full">
      <Toolbox
        onDropKind={onAddAtCenter}
        onAddAtCenter={onAddAtCenter}
        disabled={!current}
      />
      <div
        ref={wrapperRef}
        className="relative flex-1 h-full"
        onDragOver={onDragOver}
        onDrop={onDrop}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onInit={(inst) => {
            rfInstance.current = inst;
          }}
          onMoveEnd={onMoveEnd}
          defaultViewport={{
            x: current?.viewport_x ?? 0,
            y: current?.viewport_y ?? 0,
            zoom: current?.viewport_zoom ?? 1,
          }}
          fitView={isEmpty}
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.2}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
          deleteKeyCode={null /* we handle delete via window listener */}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1.2}
          />
          {/* Bug #49 part 2 — bottom-right was covering node
              handles in the bottom-right canvas region, making
              drags silently fail. Top-right leaves the bottom for
              the MiniMap and the bottom-right handle area clear. */}
          <Controls position="top-right" showInteractive={false} />
          <MiniMap
            position="bottom-left"
            pannable
            zoomable
            maskColor="rgba(11, 18, 32, 0.7)"
            nodeColor={(n) => {
              const data = n.data as CanvasNodeData | undefined;
              switch (data?.kind) {
                case 'host':
                  return '#60a5fa';
                case 'switch':
                  return '#34d399';
                case 'router':
                  return '#22d3ee';
                case 'server':
                  return '#a78bfa';
                case 'attacker':
                  return '#f87171';
                default:
                  return '#5a6e91';
              }
            }}
            style={{
              backgroundColor: '#111a2e',
              border: '1px solid #1f2d4a',
            }}
          />
        </ReactFlow>

        {isEmpty && current && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="bg-bg-surface/80 border border-border rounded-lg px-4 py-3 text-center">
              <div className="text-sm font-semibold text-text-primary">
                Empty canvas
              </div>
              <div className="text-xs text-text-secondary mt-1">
                Drag a node from the toolbox to start.
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Public component (wraps the provider so RF hooks work) ─────────────

export function Canvas(props: {
  projectId: string;
  onOpenNode?: (p: OpenNodePayload) => void;
  onOpenLink?: (linkId: string) => void;
}) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}

export default Canvas;
