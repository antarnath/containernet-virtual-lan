// Inline SVG icons for each topology type. Drawn small (24x24 viewport)
// so they fit inside topology-type selector cards on the LAN Builder page.

import type { TopologyType } from '../types';

interface IconProps {
  className?: string;
}

export function MeshIcon({ className }: IconProps) {
  // 5-node fully connected mesh
  const r = 8;
  const nodes = [
    [12, 4],
    [22, 10],
    [19, 21],
    [5, 21],
    [2, 10],
  ];
  const edges: [number, number][] = [
    [0, 1], [0, 2], [0, 3], [0, 4],
    [1, 2], [1, 4],
    [2, 3],
    [3, 4],
  ];
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.2">
      {edges.map(([a, b], i) => (
        <line key={i} x1={nodes[a][0]} y1={nodes[a][1]} x2={nodes[b][0]} y2={nodes[b][1]} />
      ))}
      {nodes.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={r / 2} fill="currentColor" />
      ))}
    </svg>
  );
}

export function StarIcon({ className }: IconProps) {
  // Center + 4 spokes
  const cx = 12;
  const cy = 12;
  const leaves = [[12, 3], [21, 12], [12, 21], [3, 12]];
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.2">
      {leaves.map(([x, y], i) => (
        <line key={i} x1={cx} y1={cy} x2={x} y2={y} />
      ))}
      {leaves.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={2} fill="currentColor" />
      ))}
      <circle cx={cx} cy={cy} r={2.5} fill="currentColor" />
    </svg>
  );
}

export function RingIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.2">
      <circle cx="12" cy="12" r="8" />
      {[
        [12, 4],
        [20, 12],
        [12, 20],
        [4, 12],
      ].map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={2} fill="currentColor" />
      ))}
    </svg>
  );
}

export function BusIcon({ className }: IconProps) {
  // Linear chain: backbone + 4 stubs
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.2">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="6" x2="3" y2="12" />
      <line x1="9" y1="6" x2="9" y2="12" />
      <line x1="15" y1="6" x2="15" y2="12" />
      <line x1="21" y1="6" x2="21" y2="12" />
      {[3, 9, 15, 21].map((x, i) => (
        <circle key={i} cx={x} cy={14} r={2} fill="currentColor" />
      ))}
    </svg>
  );
}

export function TreeIcon({ className }: IconProps) {
  // Simple binary-ish tree
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.2">
      <line x1="12" y1="4" x2="6" y2="11" />
      <line x1="12" y1="4" x2="18" y2="11" />
      <line x1="6" y1="11" x2="3" y2="18" />
      <line x1="6" y1="11" x2="9" y2="18" />
      <line x1="18" y1="11" x2="15" y2="18" />
      <line x1="18" y1="11" x2="21" y2="18" />
      <circle cx="12" cy="4" r="2" fill="currentColor" />
      {[
        [6, 11],
        [18, 11],
        [3, 18],
        [9, 18],
        [15, 18],
        [21, 18],
      ].map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={1.5} fill="currentColor" />
      ))}
    </svg>
  );
}

export function TopologyIcon({
  type,
  className,
}: { type: TopologyType } & IconProps) {
  switch (type) {
    case 'mesh':
      return <MeshIcon className={className} />;
    case 'star':
      return <StarIcon className={className} />;
    case 'ring':
      return <RingIcon className={className} />;
    case 'bus':
      return <BusIcon className={className} />;
    case 'tree':
      return <TreeIcon className={className} />;
  }
}

export const TOPOLOGY_TYPES: TopologyType[] = [
  'mesh',
  'star',
  'ring',
  'bus',
  'tree',
];

export const TOPOLOGY_DESCRIPTIONS: Record<TopologyType, string> = {
  mesh: 'Every host connects to every other host. Maximum redundancy.',
  star: 'All hosts connect through one central hub. Easiest to wire.',
  ring: 'Each host connects to its two neighbours forming a loop.',
  bus: 'Hosts daisy-chain off a shared backbone line.',
  tree: 'Hierarchical structure with a root and branching leaves.',
};
