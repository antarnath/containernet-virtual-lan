// Dagre auto-layout — computes (x, y) positions for each node so we don't
// have to place them by hand. The returned nodes have `position` populated
// for React Flow.

import dagre from 'dagre';
import type { Edge, Node } from 'reactflow';
import type { TopologyResponse } from '../types';

const NODE_WIDTH = 180;
const NODE_HEIGHT = 90;

export function buildLayout(topology: TopologyResponse): {
  nodes: Node[];
  edges: Edge[];
} {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 90 });

  const nodes: Node[] = topology.nodes.map((n) => ({
    id: n.id,
    type: 'host',
    data: { label: n.label, ip: n.ip, status: n.status },
    position: { x: 0, y: 0 },
  }));

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  topology.edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  const positioned = nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    };
  });

  const edges: Edge[] = topology.edges.map((e) => ({
    id: `${e.source}-${e.target}`,
    source: e.source,
    target: e.target,
    animated: true,
    type: 'smoothstep',
  }));

  return { nodes: positioned, edges };
}
