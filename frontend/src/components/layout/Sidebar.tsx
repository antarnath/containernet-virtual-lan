// Vertical navigation bar.
//
// Two layers:
//   * Global links — Dashboard, Projects, LAN Builder, legacy Hosts/Comms.
//   * Per-project nested section — Topology, Hosts, Communications, Messages
//     for the project currently loaded into `useProjectStore.current`.
//     Hidden until the user picks (or opens) a project.

import { useEffect } from 'react';
import { useNavigate, NavLink } from 'react-router-dom';
import { useProjectStore } from '../../store/projectStore';

interface LinkSpec {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

const globalLinks: LinkSpec[] = [
  { to: '/', label: 'Dashboard', icon: '📊', end: true },
  { to: '/projects', label: 'Projects', icon: '🗂️', end: true },
  { to: '/builder', label: 'LAN Builder', icon: '✨' },
  { to: '/hosts', label: 'Hosts', icon: '🖥️' },
  { to: '/communications', label: 'Comms', icon: '💬' },
];

export default function Sidebar() {
  const current = useProjectStore((s) => s.current);
  const projects = useProjectStore((s) => s.projects);
  const projectsLoading = useProjectStore((s) => s.projectsLoading);
  const fetchProjects = useProjectStore((s) => s.fetchProjects);
  const navigate = useNavigate();

  // Hydrate the project list once (cheap; the store memoizes the result).
  // Guard with projectsLoading so we don't kick off a duplicate fetch while
  // the first one is in-flight — the old `setTimeout(...)` pattern could
  // re-fire on every render and caused the empty-state flicker.
  useEffect(() => {
    if (projects.length === 0 && !projectsLoading) {
      void fetchProjects();
    }
  }, [projects.length, projectsLoading, fetchProjects]);

  return (
    <aside className="w-60 bg-panel border-r border-border flex flex-col">
      <div className="px-5 py-5 border-b border-border">
        <div className="text-lg font-bold text-text">ContainerNet</div>
        <div className="text-xs text-muted mt-1">Dynamic Virtual LAN</div>
      </div>

      {/* Project switcher — when a project is loaded into the store,
          jumping to /projects auto-picks that project. */}
      <div className="px-3 pt-3">
        <div className="text-[10px] uppercase tracking-wider text-muted mb-1 px-2">
          Active project
        </div>
        <select
          value={current?.id ?? ''}
          onChange={(e) => {
            const id = e.target.value;
            if (id) {
              navigate(`/projects/${id}/topology`);
            } else {
              navigate('/projects');
            }
          }}
          className="w-full bg-bg border border-border rounded-md px-2 py-1.5 text-xs text-text"
        >
          <option value="">— none —</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.status})
            </option>
          ))}
        </select>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-auto">
        {globalLinks.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                isActive
                  ? 'bg-accent text-white'
                  : 'text-muted hover:bg-panel2 hover:text-text'
              }`
            }
          >
            <span className="text-lg">{link.icon}</span>
            <span>{link.label}</span>
          </NavLink>
        ))}

        {/* Per-project nested section — shows Topology / Hosts / Communications
            / Messages for the active project. */}
        {current && (
          <div className="pt-4 mt-2 border-t border-border">
            <div className="text-[10px] uppercase tracking-wider text-muted px-3 mb-1">
              {current.name}
            </div>
            <NestedLink
              to={`/projects/${current.id}/topology`}
              label="Topology"
              icon="🕸️"
            />
            <NestedLink
              to={`/projects/${current.id}/hosts`}
              label="Hosts"
              icon="🖥️"
            />
            <NestedLink
              to={`/projects/${current.id}/communications`}
              label="Communications"
              icon="💬"
            />
            <NestedLink
              to={`/projects/${current.id}/messages`}
              label="Messages"
              icon="📨"
            />
          </div>
        )}
      </nav>
    </aside>
  );
}

function NestedLink({ to, label, icon }: { to: string; label: string; icon: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-3 pl-6 pr-3 py-1.5 rounded-md text-sm transition-colors ${
          isActive
            ? 'bg-panel2 text-accent'
            : 'text-muted hover:bg-panel2 hover:text-text'
        }`
      }
    >
      <span className="text-sm">{icon}</span>
      <span>{label}</span>
    </NavLink>
  );
}