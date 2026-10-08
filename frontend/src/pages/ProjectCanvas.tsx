// ProjectCanvas — the M4 canvas page. The full viewport is the
// React Flow surface; a thin top bar shows the project name, status,
// counts, and the lifecycle buttons (Start / Stop / Restart).
//
// Phase 02 wires those buttons to the real backend. Start/stop/restart
// all return the updated ProjectDetail, so we replace the store's
// `current` with the response — no need for a follow-up fetch.

import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { useProjectStore } from '../store/projectStore';
import { Button, Card, LoadingSkeleton, StatusPill, toast } from '../components/ui';
import { Canvas } from '../canvas';
import { ProjectsAPI } from '../api/client';
import type { ProjectDetail, ProjectStatus } from '../types';

const STATUS_TONE: Record<ProjectStatus, 'idle' | 'draft' | 'starting' | 'running' | 'partial' | 'stopped' | 'error'> = {
  draft: 'draft',
  starting: 'starting',
  running: 'running',
  partial: 'partial',
  stopped: 'stopped',
  error: 'error',
};

const STATUS_PULSE: Partial<Record<ProjectStatus, boolean>> = {
  running: true,
  partial: true,
  starting: true,
};

type LifecycleOp = 'start' | 'stop' | 'restart';

export default function ProjectCanvas() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const current = useProjectStore((s) => s.current);
  const loading = useProjectStore((s) => s.currentLoading);
  const error = useProjectStore((s) => s.currentError);
  const actionInFlight = useProjectStore((s) => s.actionInFlight);
  const fetchProject = useProjectStore((s) => s.fetchProject);
  const clearCurrent = useProjectStore((s) => s.clearCurrent);

  useEffect(() => {
    if (!projectId) return;
    void fetchProject(projectId);
    return () => {
      // When the user navigates away, drop the cached detail so the
      // next page doesn't accidentally show stale data.
      clearCurrent();
    };
  }, [projectId, fetchProject, clearCurrent]);

  async function handleLifecycle(op: LifecycleOp) {
    if (!projectId) return;
    useProjectStore.setState({ actionInFlight: op });
    try {
      let detail: ProjectDetail;
      if (op === 'start') detail = await ProjectsAPI.start(projectId);
      else if (op === 'stop') detail = await ProjectsAPI.stop(projectId);
      else detail = await ProjectsAPI.restart(projectId);
      // The start/stop/restart endpoints return the full ProjectDetail
      // — replace the cached one so the canvas shows the new state
      // without a follow-up fetch.
      useProjectStore.setState({ current: detail });
      const label = op === 'start' ? 'started' : op === 'stop' ? 'stopped' : 'restarted';
      const errCount = (detail.nodes || []).filter(
        (n) => n.container_status === 'error',
      ).length;
      if (errCount > 0 && op !== 'stop') {
        toast.error(
          `${label} with ${errCount} error${errCount === 1 ? '' : 's'}`,
          'See the Logs view (phase 07) for details.',
        );
      } else {
        toast.success(`Project ${label}`, `${detail.nodes.length} container(s) up.`);
      }
    } catch (e) {
      // The backend returns 500 with a detail object on partial
      // failure. Surface the message to the user.
      const msg = (e as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail;
      const text = typeof msg === 'string' ? msg : (e as Error).message;
      toast.error(`Could not ${op} project`, text);
    } finally {
      useProjectStore.setState({ actionInFlight: null });
    }
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center p-6">
        <Card className="max-w-md w-full">
          <div className="text-sm font-semibold text-text-primary mb-1">
            Could not load project
          </div>
          <div className="text-xs text-text-secondary mb-4">{error}</div>
          <Button variant="secondary" onClick={() => navigate('/projects')}>
            Back to projects
          </Button>
        </Card>
      </div>
    );
  }

  if (loading || !current || current.id !== projectId) {
    return (
      <div className="h-full flex flex-col">
        <div className="h-12 border-b border-border flex items-center px-4 gap-3 bg-bg-surface">
          <LoadingSkeleton width="160px" height="14px" />
          <LoadingSkeleton width="80px" height="20px" />
        </div>
        <div className="flex-1 flex items-center justify-center">
          <LoadingSkeleton width="220px" height="14px" />
        </div>
      </div>
    );
  }

  const isRunning = current.status === 'running' || current.status === 'partial';
  const isStarting = current.status === 'starting';

  return (
    <div className="h-full flex flex-col -m-6">
      {/* Top bar */}
      <div className="h-12 flex-shrink-0 bg-bg-surface border-b border-border flex items-center px-4 gap-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/projects')}
          aria-label="Back to projects"
        >
          ←
        </Button>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-text-primary truncate">
            {current.name}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-2xs font-mono text-text-muted">
            {current.node_count} node{current.node_count === 1 ? '' : 's'} ·{' '}
            {current.link_count} wire{current.link_count === 1 ? '' : 's'}
          </div>
          <StatusPill tone={STATUS_TONE[current.status]} pulse={STATUS_PULSE[current.status]}>
            {current.status}
          </StatusPill>
          {!isRunning && !isStarting && (
            <Button
              variant="accent"
              size="sm"
              onClick={() => handleLifecycle('start')}
              loading={actionInFlight === 'start'}
              disabled={isStarting}
            >
              Start
            </Button>
          )}
          {isRunning && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleLifecycle('stop')}
              loading={actionInFlight === 'stop'}
            >
              Stop
            </Button>
          )}
          {isRunning && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleLifecycle('restart')}
              loading={actionInFlight === 'restart'}
            >
              Restart
            </Button>
          )}
        </div>
      </div>

      {/* Canvas surface */}
      <div className="flex-1 min-h-0">
        <Canvas projectId={current.id} />
      </div>
    </div>
  );
}
