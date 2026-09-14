// Hosts page — Phase 05.
//
// Two modes:
//   1. /projects/:projectId/hosts   → per-project view (new). Reads the
//      project's hosts via `useHostStore.byProject[projectId]`, polls every
//      10s, drops a metric card into each HostCard.
//   2. /hosts                       → legacy global fallback. Polls
//      `useHostStore.hosts` like the original static-page version.

import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import HostCard from '../components/host-monitor/HostCard';
import { useHostStore } from '../store/hostStore';

const POLL_MS = 10_000;

export default function HostsPage() {
  const { projectId } = useParams<{ projectId?: string }>();

  if (projectId) {
    return <ProjectHostsPage projectId={projectId} />;
  }
  return <LegacyGlobalHostsPage />;
}

// ─── per-project view (Phase 05) ───────────────────────────────────────────

function ProjectHostsPage({ projectId }: { projectId: string }) {
  const list = useHostStore((s) => s.byProject[projectId] ?? null);
  const fetchProjectHosts = useHostStore((s) => s.fetchProjectHosts);

  useEffect(() => {
    fetchProjectHosts(projectId);
    const id = setInterval(() => fetchProjectHosts(projectId), POLL_MS);
    return () => clearInterval(id);
  }, [projectId, fetchProjectHosts]);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text">Hosts</h1>
          <p className="text-sm text-muted mt-1">
            Live status, last-heartbeat, and resource usage for every host in
            this project.
          </p>
        </div>
        <Link
          to={`/projects/${projectId}/topology`}
          className="text-sm bg-panel border border-border text-text px-3 py-2 rounded-md hover:border-accent"
        >
          ← Back to topology
        </Link>
      </div>

      {list ? (
        <>
          <SummaryStats list={list} />
          {list.hosts.length === 0 ? (
            <div className="bg-panel border border-border rounded-xl p-10 text-center text-muted">
              No hosts in this project yet. Start the project to spawn
              containers.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {list.hosts.map((h) => (
                <HostCard key={h.id} host={h} projectId={projectId} />
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="text-muted">Loading hosts…</div>
      )}
    </div>
  );
}

function SummaryStats({
  list,
}: {
  list: { total: number; online: number; offline: number };
}) {
  const unknown = list.total - list.online - list.offline;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <StatCard label="Total" value={list.total} color="text-text" />
      <StatCard label="Online" value={list.online} color="text-online" />
      <StatCard label="Offline" value={list.offline} color="text-offline" />
      <StatCard label="Unknown" value={unknown} color="text-unknown" />
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="bg-panel border border-border rounded-xl p-4">
      <div className="text-[10px] uppercase tracking-wider text-muted">
        {label}
      </div>
      <div className={`text-3xl font-bold mt-1 ${color}`}>{value}</div>
    </div>
  );
}

// ─── legacy global hosts page (transition fallback) ────────────────────────

function LegacyGlobalHostsPage() {
  const hosts = useHostStore((s) => s.hosts);
  const fetchHosts = useHostStore((s) => s.fetchHosts);

  useEffect(() => {
    fetchHosts();
    const id = setInterval(fetchHosts, POLL_MS);
    return () => clearInterval(id);
  }, [fetchHosts]);

  if (!hosts) {
    return <div className="text-muted">Loading hosts…</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text">Hosts (legacy)</h1>
        <p className="text-sm text-muted mt-1">
          Flat list across every project. Prefer{' '}
          <Link className="text-accent underline" to="/projects">
            Projects
          </Link>{' '}
          → per-project view.
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