// Top header bar — shows the online count + a "Live"/"Reconnecting" badge.

import { useHostStore } from '../../store/hostStore';
import { useRealtimeStore } from '../../store/realtimeStore';

export default function Topbar() {
  const hosts = useHostStore((s) => s.hosts);
  const wsStatus = useRealtimeStore((s) => s.wsStatus);
  const online = hosts?.online ?? 0;
  const total = hosts?.total ?? 0;

  const dot =
    wsStatus === 'open'
      ? 'bg-online'
      : wsStatus === 'connecting'
      ? 'bg-unknown'
      : 'bg-offline';
  const label =
    wsStatus === 'open' ? 'Live' : wsStatus === 'connecting' ? 'Connecting' : 'Offline';

  return (
    <header className="h-14 bg-panel border-b border-border flex items-center justify-between px-6">
      <div className="text-sm text-muted">
        Container-based Virtual LAN — live status
      </div>

      <div className="flex items-center gap-6 text-sm">
        {/* WS status */}
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            {wsStatus === 'open' && (
              <span className="animate-pulse-dot absolute inline-flex h-full w-full rounded-full bg-online opacity-75"></span>
            )}
            <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${dot}`}></span>
          </span>
          <span className="text-xs uppercase tracking-wider text-muted">
            {label}
          </span>
        </div>

        {/* Host count */}
        <div className="flex items-center gap-2">
          <span className="relative flex h-3 w-3">
            <span className="animate-pulse-dot absolute inline-flex h-full w-full rounded-full bg-online opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-online"></span>
          </span>
          <span className="text-text font-medium">
            {online} / {total} hosts online
          </span>
        </div>
      </div>
    </header>
  );
}