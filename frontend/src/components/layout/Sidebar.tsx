// Vertical navigation bar.
//
// Phase 05 additions:
//   * A project switcher dropdown at the top — when a project is loaded
//     into `useProjectStore.current`, jumping to /projects routes auto-
//     picks that project.
//   * A nested section under the active project: Topology + Hosts links.
//
// Phase 06 additions:
//   * The nested section now also has a Communications link (scoped to
//     the active project).
//
// Phase 07:
//   * No UI changes here — the per-project WS subscriptions happen below
//     the navigation layer, in useWebSocket + the realtime store.
//
// Each nested link is enabled ONLY when a project is currently loaded.
// Global links (Dashboard, Projects, LAN Builder, Comms legacy, Hosts
// legacy) stay always-visible.

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
  const fetchProjects = useProjectStore((s) => s.fetchProjects);
  const navigate = useNavigate();

  // Make sure the project list is hydrated for the dropdown, regardless of
  // which page is currently active.
  // (Cheap to call: the store memoizes; harmless if already loaded.)
  if (projects.length === 0) {
    // Schedule the fetch once; don't block render.
    setTimeout(() => fetchProjects(), 0);
  }

  return (
    <aside className="w-60 bg-panel border-r border-border flex flex-col">
      <div className="px-5 py-5 border-b border-border">
        <div className="text-lg font-bold text-text">ContainerNet</div>
        <div className="text-xs text-muted mt-1">Dynamic Virtual LAN</div>
      </div>

      {/* Project switcher (Phase 05) */}
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

        {/* Per-project nested section (Phase 05/06) */}
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
          </div>
        )}
      </nav>

      <div className="px-5 py-3 border-t border-border text-[10px] text-muted">
        v0.10.0 · Phase 08 (in progress)
      </div>
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