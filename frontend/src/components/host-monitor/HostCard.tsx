// Card for a single host — used on the Hosts page.

import type { Host } from '../../types';
import StatusLED from '../topology/StatusLED';

function formatTime(iso: string | null): string {
  if (!iso) return 'never';
  const d = new Date(iso);
  return d.toLocaleTimeString();
}

export default function HostCard({ host }: { host: Host }) {
  return (
    <div className="bg-panel border border-border rounded-xl p-5 hover:border-accent transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <StatusLED status={host.status} size="sm" />
          <div>
            <div className="text-lg font-semibold text-text">{host.hostname}</div>
            <div className="text-xs text-muted font-mono">{host.host_id}</div>
          </div>
        </div>
        <span
          className={`text-[10px] uppercase tracking-wider px-2 py-1 rounded ${
            host.status === 'online'
              ? 'bg-online/20 text-online'
              : host.status === 'offline'
              ? 'bg-offline/20 text-offline'
              : 'bg-unknown/20 text-unknown'
          }`}
        >
          {host.status}
        </span>
      </div>
      <div className="space-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-muted">IP address</span>
          <span className="text-text font-mono">{host.ip_address}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted">Last heartbeat</span>
          <span className="text-text font-mono">{formatTime(host.last_seen)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted">Registered</span>
          <span className="text-text font-mono">{formatTime(host.created_at)}</span>
        </div>
      </div>
    </div>
  );
}
