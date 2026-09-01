// Dashboard — three big stat cards (Total / Online / Offline) with a quick
// "live host list" panel.

import { useHostStore } from '../store/hostStore';
import StatusLED from '../components/topology/StatusLED';

interface StatProps {
  label: string;
  value: number;
  color: string;
  helper?: string;
}

function Stat({ label, value, color, helper }: StatProps) {
  return (
    <div className="bg-panel border border-border rounded-xl p-6 flex-1">
      <div className="text-xs uppercase tracking-wider text-muted">{label}</div>
      <div className={`text-5xl font-bold mt-3 ${color}`}>{value}</div>
      {helper && <div className="text-xs text-muted mt-2">{helper}</div>}
    </div>
  );
}

export default function Dashboard() {
  const hosts = useHostStore((s) => s.hosts);

  if (!hosts) {
    return <div className="text-muted">Loading…</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text">Dashboard</h1>
        <p className="text-sm text-muted mt-1">
          Live snapshot of the ContainerNet virtual LAN.
        </p>
      </div>

      <div className="flex gap-4">
        <Stat
          label="Total Hosts"
          value={hosts.total}
          color="text-text"
          helper="Discovered containers"
        />
        <Stat
          label="Online"
          value={hosts.online}
          color="text-online"
          helper="Heartbeats received within 15s"
        />
        <Stat
          label="Offline"
          value={hosts.offline}
          color="text-offline"
          helper="No heartbeat in 15s+"
        />
      </div>

      <div className="bg-panel border border-border rounded-xl p-6">
        <div className="text-sm font-semibold text-text mb-4">Live Host List</div>
        <div className="divide-y divide-border">
          {hosts.hosts.map((h) => (
            <div
              key={h.id}
              className="flex items-center justify-between py-3"
            >
              <div className="flex items-center gap-3">
                <StatusLED status={h.status} />
                <div>
                  <div className="text-text font-medium">{h.hostname}</div>
                  <div className="text-xs text-muted font-mono">
                    {h.ip_address}
                  </div>
                </div>
              </div>
              <div className="text-xs uppercase tracking-wider text-muted">
                {h.status}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
