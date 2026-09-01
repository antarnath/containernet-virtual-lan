// Topology page — wraps the interactive React Flow view full-bleed.

import TopologyView from '../components/topology/TopologyView';

export default function TopologyPage() {
  return (
    <div className="flex flex-col h-[calc(100vh-9rem)]">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-text">Network Topology</h1>
        <p className="text-sm text-muted mt-1">
          Each node is a container on the <code className="text-accent">containernet_lan</code> bridge.
          Drag, zoom, and pan. Status LEDs update every 5 seconds.
        </p>
      </div>
      <div className="flex-1">
        <TopologyView />
      </div>
    </div>
  );
}
