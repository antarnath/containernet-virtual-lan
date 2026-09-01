// Custom React Flow node renderer — looks like a styled card with a status LED.

import { Handle, Position } from 'reactflow';
import type { HostStatus } from '../../types';
import StatusLED from './StatusLED';

interface HostNodeData {
  label: string;
  ip: string;
  status: HostStatus;
}

export default function HostNode({ data }: { data: HostNodeData }) {
  const statusColor =
    data.status === 'online'
      ? 'border-online'
      : data.status === 'offline'
      ? 'border-offline'
      : 'border-unknown';

  return (
    <div
      className={`bg-panel border-2 ${statusColor} rounded-lg px-4 py-3 shadow-lg min-w-[160px]`}
    >
      {/* Source handle on top, target on bottom */}
      <Handle type="target" position={Position.Top} className="!bg-accent" />
      <Handle type="source" position={Position.Bottom} className="!bg-accent" />

      <div className="flex items-center gap-2 mb-1">
        <StatusLED status={data.status} size="sm" />
        <span className="font-semibold text-text">{data.label}</span>
      </div>
      <div className="text-xs text-muted font-mono">{data.ip}</div>
      <div className="text-[10px] uppercase tracking-wider text-muted mt-1">
        {data.status}
      </div>
    </div>
  );
}