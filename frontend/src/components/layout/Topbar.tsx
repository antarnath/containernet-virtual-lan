// Top header bar showing the online count with a pulsing dot.

import { useHostStore } from '../../store/hostStore';

export default function Topbar() {
  const hosts = useHostStore((s) => s.hosts);
  const online = hosts?.online ?? 0;
  const total = hosts?.total ?? 0;

  return (
    <header className="h-14 bg-panel border-b border-border flex items-center justify-between px-6">
      <div className="text-sm text-muted">
        Container-based Virtual LAN — live status
      </div>
      <div className="flex items-center gap-2 text-sm">
        <span className="relative flex h-3 w-3">
          <span className="animate-pulse-dot absolute inline-flex h-full w-full rounded-full bg-online opacity-75"></span>
          <span className="relative inline-flex rounded-full h-3 w-3 bg-online"></span>
        </span>
        <span className="text-text font-medium">
          {online} / {total} hosts online
        </span>
      </div>
    </header>
  );
}
