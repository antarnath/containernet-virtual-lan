// Vertical navigation bar. Uses React Router's NavLink so the active
// link is highlighted automatically.

import { NavLink } from 'react-router-dom';

const links = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/topology', label: 'Topology', icon: '🌐' },
  { to: '/hosts', label: 'Hosts', icon: '🖥️' },
];

export default function Sidebar() {
  return (
    <aside className="w-56 bg-panel border-r border-border flex flex-col">
      <div className="px-5 py-5 border-b border-border">
        <div className="text-lg font-bold text-text">ContainerNet</div>
        <div className="text-xs text-muted mt-1">Virtual LAN Dashboard</div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === '/'}
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
      </nav>

      <div className="px-5 py-4 border-t border-border text-xs text-muted">
        <div>Phase 04</div>
        <div className="mt-1">Topology Visualization</div>
      </div>
    </aside>
  );
}
