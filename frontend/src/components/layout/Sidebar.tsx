// Vertical navigation bar.
//
// M4 phase 01: just Dashboard and Projects. Future phases will
// add a per-project nested section (Wires, Triggers, Attacks, Router)
// once those pages exist.

import { NavLink } from 'react-router-dom';

interface LinkSpec {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

const globalLinks: LinkSpec[] = [
  { to: '/', label: 'Dashboard', icon: '◧', end: true },
  { to: '/projects', label: 'Projects', icon: '◫', end: true },
];

export default function Sidebar() {
  return (
    <aside className="w-60 flex-shrink-0 bg-bg-surface border-r border-border flex flex-col">
      <div className="px-5 py-5 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-md bg-accent/15 border border-accent/40 flex items-center justify-center text-accent text-sm font-bold">
            ⊕
          </div>
          <div>
            <div className="text-sm font-bold text-text-primary leading-none">
              ContainerNet
            </div>
            <div className="text-2xs text-text-muted mt-1">
              Virtual network lab
            </div>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {globalLinks.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors duration-fast',
                isActive
                  ? 'bg-accent/15 text-accent border border-accent/40'
                  : 'text-text-secondary hover:bg-bg-surface-2 hover:text-text-primary border border-transparent',
              ].join(' ')
            }
          >
            <span className="text-base w-5 text-center" aria-hidden>
              {link.icon}
            </span>
            <span>{link.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="px-5 py-3 border-t border-border text-2xs text-text-muted">
        M4 · phase 01
      </div>
    </aside>
  );
}
