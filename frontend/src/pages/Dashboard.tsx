// Dashboard — minimal M4 overview. Shows the total project count and
// a few quick stats. Pulls from the same /api/projects endpoint that
// the Projects page uses (cheap to refetch).
//
// Future phases will add a live activity feed (communications, captures)
// here, but phase 01 keeps it lean — the editor is the headline.

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { useProjectStore } from '../store/projectStore';
import { Card, StatusPill } from '../components/ui';
import type { ProjectStatus } from '../types';

interface Counters {
  total: number;
  running: number;
  stopped: number;
  totalNodes: number;
  totalLinks: number;
}

const STATUS_TONE: Record<ProjectStatus, 'idle' | 'draft' | 'starting' | 'running' | 'partial' | 'stopped' | 'error'> = {
  draft: 'draft',
  starting: 'starting',
  running: 'running',
  partial: 'partial',
  stopped: 'stopped',
  error: 'error',
};

export default function Dashboard() {
  const projects = useProjectStore((s) => s.projects);
  const fetchProjects = useProjectStore((s) => s.fetchProjects);
  const [counters, setCounters] = useState<Counters>({
    total: 0,
    running: 0,
    stopped: 0,
    totalNodes: 0,
    totalLinks: 0,
  });

  useEffect(() => {
    void fetchProjects();
  }, [fetchProjects]);

  useEffect(() => {
    setCounters({
      total: projects.length,
      running: projects.filter((p) => p.status === 'running').length,
      stopped: projects.filter((p) => p.status === 'stopped' || p.status === 'draft').length,
      totalNodes: projects.reduce((acc, p) => acc + p.node_count, 0),
      totalLinks: projects.reduce((acc, p) => acc + p.link_count, 0),
    });
  }, [projects]);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">ContainerNet</h1>
          <p className="text-sm text-text-secondary mt-1">
            Build a virtual network from scratch. Drop hosts, switches, routers, and wires on a canvas — no templates, no magic.
          </p>
        </div>
        <Link
          to="/projects"
          className="inline-flex items-center justify-center h-9 px-3.5 rounded-md text-sm font-medium bg-accent text-text-inverse hover:bg-accent/90 transition-colors"
        >
          Go to projects →
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <div className="text-2xs uppercase tracking-wider text-text-muted">
            Projects
          </div>
          <div className="text-2xl font-bold text-text-primary mt-1">
            {counters.total}
          </div>
        </Card>
        <Card>
          <div className="text-2xs uppercase tracking-wider text-text-muted">
            Running
          </div>
          <div className="text-2xl font-bold text-success mt-1">
            {counters.running}
          </div>
        </Card>
        <Card>
          <div className="text-2xs uppercase tracking-wider text-text-muted">
            Total nodes
          </div>
          <div className="text-2xl font-bold text-text-primary mt-1">
            {counters.totalNodes}
          </div>
        </Card>
        <Card>
          <div className="text-2xs uppercase tracking-wider text-text-muted">
            Total wires
          </div>
          <div className="text-2xl font-bold text-text-primary mt-1">
            {counters.totalLinks}
          </div>
        </Card>
      </div>

      <Card>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-text-primary">Recent projects</h2>
          <Link
            to="/projects"
            className="text-2xs uppercase tracking-wider text-accent hover:underline"
          >
            All projects →
          </Link>
        </div>
        {projects.length === 0 ? (
          <div className="text-sm text-text-secondary py-6 text-center">
            No projects yet. Open the projects page to create one.
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {projects.slice(0, 5).map((p) => (
              <li key={p.id}>
                <Link
                  to={`/projects/${p.id}/canvas`}
                  className="flex items-center justify-between py-2.5 hover:bg-bg-surface-2 -mx-2 px-2 rounded transition-colors"
                >
                  <span className="text-sm text-text-primary truncate">
                    {p.name}
                  </span>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-2xs font-mono text-text-muted">
                      {p.node_count} · {p.link_count}
                    </span>
                    <StatusPill tone={STATUS_TONE[p.status]}>
                      {p.status}
                    </StatusPill>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
