// Projects home — dark grid of project cards on the M4 design system.
//
// Each card shows:
//   • the project name (the only user-given field)
//   • a status pill (draft / running / partial / stopped / error)
//   • node count + link count
//   • "updated 2m ago" timestamp
//   • Open / Delete actions
//
// The "+ New project" button opens a modal that takes a name and
// creates an empty project (no template — the user is the engineer).
// New projects land directly in /canvas so the user can start
// dropping nodes.
//
// First-time UX: when the user lands on this page with no projects
// and no `visited` flag in localStorage, a one-time cyan toast
// suggests the killer demo. Clicking the button creates the demo
// project and opens its canvas.

import { useEffect, useState, useRef, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { useProjectStore } from '../store/projectStore';
import { ProjectsAPI } from '../api/client';
import { toast } from '../components/ui';
import {
  Button,
  Card,
  CardHeader,
  EmptyState,
  LoadingSkeleton,
  StatusPill,
} from '../components/ui';
import { NodeIcon } from '../components/icons';
import type { Project, ProjectStatus } from '../types';

const DEMO_TOAST_KEY = 'containernet.killer_demo_toast_shown';

// ─── helpers ────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const diffSec = Math.round((Date.now() - then) / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.round(diffSec / 3600)}h ago`;
  return `${Math.round(diffSec / 86400)}d ago`;
}

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
};

// ─── New-project modal ──────────────────────────────────────────────────

function NewProjectModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const createProject = useProjectStore((s) => s.createProject);
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      const project = await createProject({ name: name.trim() });
      if (project) {
        toast.success('Project created', project.name);
        onCreated(project.id);
      } else {
        onClose();
      }
    } catch (err) {
      toast.error('Could not create project', (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg-base/70 backdrop-blur-sm animate-slide-in-up"
      onClick={onClose}
    >
      <Card
        elevation="raised"
        className="w-[420px] max-w-[90vw]"
        onClick={(e) => e.stopPropagation()}
      >
        <form onSubmit={handleSubmit}>
          <CardHeader
            title="New project"
            subtitle="Start with a blank canvas. You'll add hosts, routers, and switches yourself."
          />
          <label
            htmlFor="project-name"
            className="block text-2xs uppercase tracking-wider text-text-muted mb-1.5"
          >
            Name
          </label>
          <input
            id="project-name"
            ref={inputRef}
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. My first network"
            maxLength={120}
            className={[
              'w-full h-9 px-3 rounded-md text-sm',
              'bg-bg-base text-text-primary placeholder:text-text-muted',
              'border border-border focus:border-accent focus:outline-none',
              'transition-colors duration-fast',
            ].join(' ')}
            autoComplete="off"
          />
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button
              variant="primary"
              type="submit"
              disabled={!name.trim()}
              loading={submitting}
            >
              Create
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

// ─── Delete confirmation modal ──────────────────────────────────────────

function DeleteConfirmModal({
  project,
  onClose,
  onDeleted,
}: {
  project: Project;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const deleteProject = useProjectStore((s) => s.deleteProject);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function handleDelete() {
    setSubmitting(true);
    try {
      const ok = await deleteProject(project.id);
      if (ok) {
        toast.info('Project deleted', project.name);
        onDeleted();
      }
    } catch (err) {
      toast.error('Could not delete project', (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg-base/70 backdrop-blur-sm animate-slide-in-up"
      onClick={onClose}
    >
      <Card
        elevation="raised"
        className="w-[420px] max-w-[90vw]"
        onClick={(e) => e.stopPropagation()}
      >
        <CardHeader
          title={`Delete "${project.name}"?`}
          subtitle="This will remove the project and every node, interface, and wire inside it."
        />
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={handleDelete}
            loading={submitting}
          >
            Delete project
          </Button>
        </div>
      </Card>
    </div>
  );
}

// ─── Project card ───────────────────────────────────────────────────────

function ProjectCard({
  project,
  onRequestDelete,
}: {
  project: Project;
  onRequestDelete: (p: Project) => void;
}) {
  const navigate = useNavigate();

  return (
    <Card
      elevation="flat"
      className="hover:border-border-strong transition-colors duration-fast"
    >
      <button
        type="button"
        onClick={() => navigate(`/projects/${project.id}/canvas`)}
        className="w-full text-left"
      >
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-text-primary truncate" title={project.name}>
              {project.name}
            </div>
            <div className="text-2xs text-text-muted mt-0.5 font-mono">
              {project.node_count} node{project.node_count === 1 ? '' : 's'} ·{' '}
              {project.link_count} wire{project.link_count === 1 ? '' : 's'}
            </div>
          </div>
          <StatusPill tone={STATUS_TONE[project.status]} pulse={STATUS_PULSE[project.status]}>
            {project.status}
          </StatusPill>
        </div>

        <div className="text-2xs text-text-muted mb-3">
          updated {relativeTime(project.updated_at)}
        </div>
      </button>

      <div className="flex gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => navigate(`/projects/${project.id}/canvas`)}
          className="flex-1"
          icon={<NodeIcon kind="router" size={14} />}
        >
          Open canvas
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onRequestDelete(project)}
          aria-label="Delete project"
          title="Delete project"
        >
          ✕
        </Button>
      </div>
    </Card>
  );
}

// ─── Page ───────────────────────────────────────────────────────────────

export default function ProjectsPage() {
  const projects = useProjectStore((s) => s.projects);
  const loading = useProjectStore((s) => s.projectsLoading);
  const error = useProjectStore((s) => s.projectsError);
  const fetchProjects = useProjectStore((s) => s.fetchProjects);
  const navigate = useNavigate();

  const [showNew, setShowNew] = useState(false);
  const [toDelete, setToDelete] = useState<Project | null>(null);

  useEffect(() => {
    void fetchProjects();
  }, [fetchProjects]);

  // First-time UX: if the user has never visited AND there are no
  // projects yet, show the cyan "Try the killer demo" toast once.
  useEffect(() => {
    if (loading) return;
    if (projects.length > 0) return;
    if (typeof window === 'undefined') return;
    let alreadyShown = false;
    try {
      alreadyShown = window.localStorage.getItem(DEMO_TOAST_KEY) === '1';
    } catch {
      // ignore — private mode etc.
    }
    if (alreadyShown) return;
    try {
      window.localStorage.setItem(DEMO_TOAST_KEY, '1');
    } catch {
      // ignore
    }
    const id = toast.info(
      'New here? Try the killer demo',
      '60s ARP-spoof MITM, no setup required.',
      {
        action: {
          label: 'Try it →',
          onClick: () => void handleCreateDemo(),
        },
        durationMs: 12000,
      },
    );
    return () => {
      toast.dismiss(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, projects.length]);

  async function handleCreateDemo() {
    try {
      const project = await ProjectsAPI.create(
        { name: 'ARP Spoof Demo' },
        'killer_demo',
      );
      toast.success('Demo ready', 'Opening canvas…');
      // Refetch so the new project appears in the grid (the user may
      // close the canvas and come back).
      void fetchProjects();
      navigate(`/projects/${project.id}/canvas`);
    } catch (err) {
      toast.error('Demo failed', (err as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Projects</h1>
          <p className="text-sm text-text-secondary mt-1">
            Each project is its own network canvas. Open one to drop hosts, switches, routers, and wires.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={handleCreateDemo}>
            ⚡ Killer demo
          </Button>
          <Button variant="primary" onClick={() => setShowNew(true)}>
            + New project
          </Button>
        </div>
      </div>

      {error && (
        <Card className="border-danger/40 bg-danger-soft">
          <div className="text-sm text-danger">Failed to load projects: {error}</div>
        </Card>
      )}

      {loading && projects.length === 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <Card key={i}>
              <LoadingSkeleton height="14px" width="60%" />
              <div className="h-2" />
              <LoadingSkeleton height="10px" width="40%" />
              <div className="h-6" />
              <div className="flex gap-2">
                <LoadingSkeleton height="28px" width="100%" />
                <LoadingSkeleton height="28px" width="32px" />
              </div>
            </Card>
          ))}
        </div>
      )}

      {!loading && projects.length === 0 && !error && (
        <EmptyState
          icon={
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden
            >
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <path d="M3 9h18" />
              <path d="M8 14h8" />
            </svg>
          }
          title="Build your first network"
          description="Drag routers, switches, and hosts onto a blank canvas. The system materializes them as real Docker containers."
          action={
            <div className="flex gap-2">
              <Button variant="accent" onClick={handleCreateDemo}>
                ⚡ Try the killer demo
              </Button>
              <Button variant="primary" onClick={() => setShowNew(true)}>
                + New project
              </Button>
            </div>
          }
        />
      )}

      {projects.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              onRequestDelete={setToDelete}
            />
          ))}
        </div>
      )}

      {showNew && (
        <NewProjectModal
          onClose={() => setShowNew(false)}
          onCreated={(id) => {
            setShowNew(false);
            navigate(`/projects/${id}/canvas`);
          }}
        />
      )}

      {toDelete && (
        <DeleteConfirmModal
          project={toDelete}
          onClose={() => setToDelete(null)}
          onDeleted={() => setToDelete(null)}
        />
      )}
    </div>
  );
}
