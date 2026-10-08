// Page shell: sidebar on the left, topbar on top, page content fills the rest.
//
// M4 phase 01: no WebSocket (no live events yet — that's phase 05+),
// no global host polling (hosts are project-scoped, fetched when the
// user opens a project). The layout is just chrome around <Outlet />.

import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import { Toaster } from '../ui';

export default function Layout() {
  return (
    <div className="flex h-screen bg-bg-base text-text-primary overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
      <Toaster />
    </div>
  );
}
