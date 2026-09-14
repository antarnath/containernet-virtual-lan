// Dashboard — Phase 09 multi-project overview.
//
// Replaces the legacy "total/online/offline" host dashboard with a
// platform-wide rollup + recent activity feed. Polls /api/stats/summary
// every 5s so the numbers stay fresh without the WS layer needing a new
// event type.

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { StatsAPI } from '../api/client';
import type { StatsSummary } from '../types';

const POLL_MS = 5000;

interface StatProps {
  label: string;
  value: number | string;
  color?: string;
  sub?: string;
}

function Stat({ label, value, color = 'text-text', sub }: StatProps) {
  return (
    <div className="bg-panel border border-border rounded-xl p-5">
      <div className="text-[10px] uppercase tracking-wider text-muted">
        {label}
      </div>
      <div className={`text-4xl font-bold mt-2 ${color}`}>{value}</div>
      {sub && <div className="text-xs text-muted mt-1">{sub}</div>}
    </div>
  );
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

function shortId(id: string | null): string {
  if (!id) return '?';
  return id.replace(/-/g, '').slice(0, 8);
}

export default function Dashboard() {
  const [summary, setSummary] = useState<StatsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const data = await StatsAPI.summary();
        if (!cancelled) {
          setSummary(data);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };
    void tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (!summary) {
    return (
      <div className="text-muted">
        {error ? `Failed to load stats: ${error}` : 'Loading overview…'}
      </div>
    );
  }

  const { projects, hosts, recent_communications } = summary;
  const onlinePct = hosts.total
    ? Math.round((hosts.online / hosts.total) * 100)
    : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text">ContainerNet Overview</h1>
          <p className="text-sm text-muted mt-1">
            Live rollup across every project. Refreshes every {POLL_MS / 1000}s.
          </p>
        </div>
        <Link
          to="/builder"
          className="bg-accent text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-accent/90"
        >
          + Create a New Project
        </Link>
      </div>

      {error && (
        <div className="bg-offline/10 border border-offline text-offline rounded-md p-3 text-xs">
          Last refresh failed: {error}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat
          label="Projects"
          value={projects.total}
          sub={`${projects.running} running · ${projects.stopped} stopped`}
          color="text-accent"
        />
        <Stat
          label="Hosts"
          value={hosts.total}
          sub={`${hosts.online} online (${onlinePct}%)`}
          color="text-online"
        />
        <Stat
          label="Messages (recent)"
          value={recent_communications.length}
          sub="latest activity"
          color="text-text"
        />
        <Stat
          label="Topology templates"
          value={5}
          sub="mesh · star · ring · bus · tree"
          color="text-text"
        />
      </div>

      <div className="bg-panel border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-text">Recent Activity</h2>
          <span className="text-xs text-muted">
            last {recent_communications.length} communications
          </span>
        </div>

        {recent_communications.length === 0 ? (
          <div className="text-muted text-sm py-8 text-center">
            No communications yet. Start a project and send a message.
          </div>
        ) : (
          <div className="divide-y divide-border">
            {recent_communications.map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between py-2 text-sm"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="font-mono text-xs text-muted whitespace-nowrap">
                    {fmtTime(c.timestamp)}
                  </span>
                  <span className="font-mono text-text whitespace-nowrap">
                    {c.source_host_id} → {c.dest_host_id}
                  </span>
                  {c.project_id && (
                    <Link
                      to={`/projects/${c.project_id}/topology`}
                      className="text-[10px] font-mono text-accent hover:underline whitespace-nowrap"
                      title={c.project_id}
                    >
                      [{shortId(c.project_id)}]
                    </Link>
                  )}
                </div>
                <div className="flex items-center gap-3 whitespace-nowrap">
                  <span className="text-xs text-muted font-mono truncate max-w-[240px]">
                    {c.payload}
                  </span>
                  <span
                    className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded ${
                      c.status === 'delivered'
                        ? 'bg-online/20 text-online'
                        : c.status === 'failed'
                          ? 'bg-offline/20 text-offline'
                          : 'bg-unknown/20 text-unknown'
                    }`}
                  >
                    {c.status}
                  </span>
                  {c.latency_ms != null && (
                    <span className="text-[10px] font-mono text-muted w-16 text-right">
                      {c.latency_ms.toFixed(1)} ms
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}