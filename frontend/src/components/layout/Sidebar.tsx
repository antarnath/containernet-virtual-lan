// Vertical navigation bar. Uses React Router's NavLink so the active
// link is highlighted automatically.

import { NavLink } from 'react-router-dom';

const links = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/projects', label: 'Projects', icon: '🗂️' },
  { to: '/builder', label: 'LAN Builder', icon: '✨' },
  { to: '/hosts', label: 'Hosts', icon: '🖥️' },
  { to: '/communications', label: 'Comms', icon: '💬' },
];

export default function Sidebar() {
  return (
    <aside className="w-56 bg-panel border-r border-border flex flex-col">
      <div className="px-5 py-5 border-b border-border">
        <div className="text-lg font-bold text-text">ContainerNet</div>
        <div className="text-xs text-muted mt-1">Dynamic Virtual LAN</div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === '/' || link.to === '/projects'}
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
    </aside>
  );
}
