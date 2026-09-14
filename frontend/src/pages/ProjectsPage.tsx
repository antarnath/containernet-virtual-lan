// Projects home — grid of project cards. Each card shows status and lets
// the user open / start / stop / delete.

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProjectStore } from '../store/projectStore';
import { useToastStore } from '../store/toastStore';
import { TopologyIcon } from '../utils/topologyIcons';
import type { Project, ProjectStatus } from '../types';

const STATUS_COLOR: Record<ProjectStatus, string> = {
  draft: 'bg-muted/30 text-muted border-muted',
  running: 'bg-online/20 text-online border-online',
  partial: 'bg-unknown/20 text-unknown border-unknown',
  stopped: 'bg-border text-muted border-muted',
  error: 'bg-offline/20 text-offline border-offline',
};

const STATUS_DOT: Record<ProjectStatus, string> = {
  draft: 'bg-muted',
  running: 'bg-online',
  partial: 'bg-unknown',
  stopped: 'bg-muted',
  error: 'bg-offline',
};

function ProjectCard({ project }: { project: Project }) {
  const navigate = useNavigate();
  const startProject = useProjectStore((s) => s.startProject);
  const stopProject = useProjectStore((s) => s.stopProject);
  const deleteProject = useProjectStore((s) => s.deleteProject);
  const actionInFlight = useProjectStore((s) => s.actionInFlight);
  const pushToast = useToastStore((s) => s.push);

  const isBusy = (kind: string) => actionInFlight === kind;

  async function handleStart(e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await startProject(project.id);
      pushToast({
        kind: 'success',
        title: 'Project started',
        message: `Containers are coming up for ${project.name}.`,
      });
    } catch (err) {
      pushToast({
        kind: 'error',
        title: 'Start failed',
        message: (err as Error).message,
      });
    }
  }

  async function handleStop(e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await stopProject(project.id);
      pushToast({
        kind: 'info',
        title: 'Project stopped',
        message: `${project.name} containers stopped.`,
      });
    } catch (err) {
      pushToast({
        kind: 'error',
        title: 'Stop failed',
        message: (err as Error).message,
      });
    }
  }

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm(`Delete "${project.name}"? This stops all its containers and removes the bridge.`)) {
      return;
    }
    try {
      await deleteProject(project.id);
      pushToast({
        kind: 'info',
        title: 'Project deleted',
        message: project.name,
      });
    } catch (err) {
      pushToast({
        kind: 'error',
        title: 'Delete failed',
        message: (err as Error).message,
      });
    }
  }

  const isRunning = project.status === 'running' || project.status === 'partial';
  const isStopped = project.status === 'stopped' || project.status === 'draft' || project.status === 'error';

  return (
    <div
      onClick={() => navigate(`/projects/${project.id}/topology`)}
      className="bg-panel border border-border rounded-xl p-5 hover:border-accent transition-colors cursor-pointer group"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-bg border border-border flex items-center justify-center text-accent">
            <TopologyIcon type={project.topology_type} className="w-7 h-7" />
          </div>
          <div>
            <div className="font-semibold text-text truncate max-w-[180px]" title={project.name}>
              {project.name}
            </div>
            <div className="text-xs text-muted capitalize">
              {project.topology_type} · {project.host_count} host{project.host_count === 1 ? '' : 's'}
            </div>
          </div>
        </div>
        <span
          className={`text-[10px] uppercase tracking-wider px-2 py-1 rounded-full border ${STATUS_COLOR[project.status]}`}
        >
          <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle ${STATUS_DOT[project.status]}`}></span>
          {project.status}
        </span>
      </div>

      <div className="text-xs text-muted font-mono mb-4">
        {project.subnet} <span className="text-border">/</span> gw {project.gateway}
      </div>

      <div className="flex gap-2">
        {isStopped && (
          <button
            onClick={handleStart}
            disabled={isBusy('start')}
            className="flex-1 text-xs bg-accent text-white px-3 py-1.5 rounded-md hover:bg-accent/90 disabled:opacity-50"
          >
            {isBusy('start') ? 'Starting…' : 'Start'}
          </button>
        )}
        {isRunning && (
          <button
            onClick={handleStop}
            disabled={isBusy('stop')}
            className="flex-1 text-xs bg-bg border border-border text-text px-3 py-1.5 rounded-md hover:border-accent disabled:opacity-50"
          >
            {isBusy('stop') ? 'Stopping…' : 'Stop'}
          </button>
        )}
        <button
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/projects/${project.id}/topology`);
          }}
          className="flex-1 text-xs bg-bg border border-border text-text px-3 py-1.5 rounded-md hover:border-accent"
        >
          Open
        </button>
        <button
          onClick={handleDelete}
          disabled={isBusy('delete')}
          className="text-xs bg-bg border border-border text-offline px-3 py-1.5 rounded-md hover:border-offline disabled:opacity-50"
        >
          ×
        </button>
      </div>
    </div>
  );
}

export default function ProjectsPage() {
  const projects = useProjectStore((s) => s.projects);
  const loading = useProjectStore((s) => s.projectsLoading);
  const error = useProjectStore((s) => s.projectsError);
  const fetchProjects = useProjectStore((s) => s.fetchProjects);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text">Projects</h1>
          <p className="text-sm text-muted mt-1">
            Each project is its own isolated Docker bridge with its own hosts.
          </p>
        </div>
        <button
          onClick={() => (window.location.href = '/builder')}
          className="bg-accent text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-accent/90"
        >
          + New Project
        </button>
      </div>

      {loading && projects.length === 0 && (
        <div className="text-muted text-sm">Loading projects…</div>
      )}

      {error && (
        <div className="bg-offline/10 border border-offline text-offline rounded-md p-4 text-sm">
          Failed to load projects: {error}
        </div>
      )}

      {!loading && projects.length === 0 && !error && (
        <div className="bg-panel border border-border rounded-xl p-10 text-center">
          <div className="text-muted mb-3">No projects yet.</div>
          <a
            href="/builder"
            className="inline-block bg-accent text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-accent/90"
          >
            Create your first LAN
          </a>
        </div>
      )}

      {projects.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      )}
    </div>
  );
}
