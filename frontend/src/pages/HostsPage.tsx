// Hosts page — responsive grid of host cards.

import { useHostStore } from '../store/hostStore';
import HostCard from '../components/host-monitor/HostCard';

export default function HostsPage() {
  const hosts = useHostStore((s) => s.hosts);

  if (!hosts) {
    return <div className="text-muted">Loading hosts…</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text">Hosts</h1>
        <p className="text-sm text-muted mt-1">
          Every container in the virtual LAN, with live status and last-heartbeat time.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {hosts.hosts.map((h) => (
          <HostCard key={h.id} host={h} />
        ))}
      </div>
    </div>
  );
}
