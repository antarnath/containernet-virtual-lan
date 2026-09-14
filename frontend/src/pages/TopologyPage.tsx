// Topology page — shows the topology of ONE project (taken from :projectId
// route param). Includes lifecycle controls (Start / Stop) and a header
// summarizing the project.

import { useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useProjectStore } from '../store/projectStore';
import { useToastStore } from '../store/toastStore';
import { TopologyIcon } from '../utils/topologyIcons';
import TopologyCanvas from '../components/topology/TopologyCanvas';
import type { ProjectStatus } from '../types';

const STATUS_BADGE: Record<ProjectStatus, string> = {
  draft: 'bg-muted/30 text-muted border-muted',
  running: 'bg-online/20 text-online border-online',
  partial: 'bg-unknown/20 text-unknown border-unknown',
  stopped: 'bg-border text-muted border-muted',
  error: 'bg-offline/20 text-offline border-offline',
};

export default function TopologyPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const project = useProjectStore((s) => s.current);
  const loading = useProjectStore((s) => s.currentLoading);
  const error = useProjectStore((s) => s.currentError);
  const fetchProject = useProjectStore((s) => s.fetchProject);
  const startProject = useProjectStore((s) => s.startProject);
  const stopProject = useProjectStore((s) => s.stopProject);
  const actionInFlight = useProjectStore((s) => s.actionInFlight);
  const clearCurrent = useProjectStore((s) => s.clearCurrent);
  const pushToast = useToastStore((s) => s.push);

  // Track whether the project ID changed — avoid stale state.
  const lastProjectIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    if (lastProjectIdRef.current !== projectId) {
      lastProjectIdRef.current = projectId;
      clearCurrent();
      fetchProject(projectId);
    }
  }, [projectId, clearCurrent, fetchProject]);

  // Light polling while the page is open — picks up container_id updates
  // after a Start, and status changes from the offline sweeper.
  useEffect(() => {
    if (!projectId) return;
    const id = setInterval(() => {
      fetchProject(projectId);
    }, 5000);
    return () => clearInterval(id);
  }, [projectId, fetchProject]);

  async function handleStart() {
    if (!projectId) return;
    try {
      await startProject(projectId);
      pushToast({
        kind: 'success',
        title: 'Project started',
        message: 'Containers are coming up.',
      });
    } catch (e) {
      pushToast({
        kind: 'error',
        title: 'Start failed',
        message: (e as Error).message,
      });
    }
  }

  async function handleStop() {
    if (!projectId) return;
    try {
      await stopProject(projectId);
      pushToast({
        kind: 'info',
        title: 'Project stopped',
        message: 'Containers have been gracefully stopped.',
      });
    } catch (e) {
      pushToast({
        kind: 'error',
        title: 'Stop failed',
        message: (e as Error).message,
      });
    }
  }

  if (!projectId) {
    return <div className="text-muted">Missing project ID.</div>;
  }

  if (loading && !project) {
    return (
      <div className="flex items-center justify-center h-[60vh] text-muted">
        Loading project…
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="space-y-3">
        <button
          onClick={() => navigate('/projects')}
          className="text-sm text-muted hover:text-text"
        >
          ← Back to projects
        </button>
        <div className="bg-offline/10 border border-offline text-offline rounded-md p-4 text-sm">
          {error ?? 'Project not found.'}
        </div>
      </div>
    );
  }

  const isRunning = project.status === 'running' || project.status === 'partial';
  const isStopped = project.status === 'stopped' || project.status === 'draft' || project.status === 'error';

  return (
    <div className="flex flex-col h-[calc(100vh-9rem)]">
      {/* Header */}
      <div className="flex items-start justify-between mb-4 gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-panel border border-border flex items-center justify-center text-accent">
            <TopologyIcon type={project.topology_type} className="w-7 h-7" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text">{project.name}</h1>
            <div className="text-sm text-muted mt-0.5 flex items-center gap-3">
              <span className="capitalize">{project.topology_type}</span>
              <span className="text-border">·</span>
              <span>
                {project.host_count} host{project.host_count === 1 ? '' : 's'}
              </span>
              <span className="text-border">·</span>
              <span className="font-mono">{project.subnet}</span>
              <span
                className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full border ${STATUS_BADGE[project.status]}`}
              >
                {project.status}
              </span>
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => navigate('/projects')}
            className="text-sm bg-panel border border-border text-text px-3 py-2 rounded-md hover:border-accent"
          >
            ← All projects
          </button>
          {isStopped && (
            <button
              onClick={handleStart}
              disabled={actionInFlight === 'start'}
              className="text-sm bg-accent text-white px-4 py-2 rounded-md hover:bg-accent/90 disabled:opacity-50"
            >
              {actionInFlight === 'start' ? 'Starting…' : '▶ Start'}
            </button>
          )}
          {isRunning && (
            <button
              onClick={handleStop}
              disabled={actionInFlight === 'stop'}
              className="text-sm bg-panel border border-border text-text px-4 py-2 rounded-md hover:border-accent disabled:opacity-50"
            >
              {actionInFlight === 'stop' ? 'Stopping…' : '■ Stop'}
            </button>
          )}
        </div>
      </div>

      {/* Canvas */}
      <div className="flex-1">
        <TopologyCanvas project={project} />
      </div>
    </div>
  );
}
