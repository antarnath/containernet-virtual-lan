// WireViewHeader — the top bar of the wire view (breadcrumb,
// status pill, pause / resume / clear / back buttons).
//
// Per design-system §7.2:
//   Breadcrumb: `ContainerNet / Lab A / Wire: 10.30.10.0/24`
//   Status pill + lifecycle action buttons (Start / Stop / Restart)
//   (we don't expose Start/Stop from the wire view — the user goes
//   back to the canvas for that — but we mirror the same height
//   and right-aligned action cluster shape).

import { useNavigate } from 'react-router-dom';
import { Button, StatusPill, type StatusTone } from '../components/ui';
import type { ProjectStatus } from '../types';

interface WireViewHeaderProps {
  projectId: string;
  projectName: string;
  projectStatus: ProjectStatus;
  /** Display label for this wire (e.g. "10.0.0.0/24"). */
  wireLabel: string;
  paused: boolean;
  onTogglePause: () => void;
  onClear: () => void;
  /** Optional link count so the user can see "N packets" in the bar. */
  packetCount: number;
}

const STATUS_TONE: Record<ProjectStatus, StatusTone> = {
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

export function WireViewHeader({
  projectId,
  projectName,
  projectStatus,
  wireLabel,
  paused,
  onTogglePause,
  onClear,
  packetCount,
}: WireViewHeaderProps) {
  const navigate = useNavigate();
  return (
    <div className="h-12 flex-shrink-0 bg-bg-surface border-b border-border flex items-center px-4 gap-3">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate(`/projects/${projectId}/canvas`)}
        aria-label="Back to canvas"
      >
        ←
      </Button>
      <div className="min-w-0 flex-1 text-sm">
        <span className="text-text-muted">ContainerNet</span>
        <span className="text-text-muted mx-1.5">/</span>
        <span className="text-text-secondary">{projectName}</span>
        <span className="text-text-muted mx-1.5">/</span>
        <span className="text-text-primary font-semibold">
          Wire: {wireLabel || '(no subnet)'}
        </span>
      </div>
      <div className="text-2xs font-mono text-text-muted tabular-nums">
        {packetCount} packet{packetCount === 1 ? '' : 's'}
      </div>
      <StatusPill tone={STATUS_TONE[projectStatus]} pulse={STATUS_PULSE[projectStatus]}>
        {projectStatus}
      </StatusPill>
      <Button
        variant="secondary"
        size="sm"
        onClick={onTogglePause}
        aria-label={paused ? 'Resume auto-scroll' : 'Pause auto-scroll'}
      >
        {paused ? '▶ Resume' : '⏸ Pause'}
      </Button>
      <Button variant="ghost" size="sm" onClick={onClear} aria-label="Clear buffer">
        Reset
      </Button>
    </div>
  );
}

export default WireViewHeader;
