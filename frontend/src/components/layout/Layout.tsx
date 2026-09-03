// Page shell: sidebar on the left, topbar on top, page content fills the rest.

import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import ToastContainer from '../common/ToastContainer';
import { useHostStore } from '../../store/hostStore';
import { useWebSocket } from '../../hooks/useWebSocket';

const POLL_INTERVAL_MS = 5000;

export default function Layout() {
  const fetchHosts = useHostStore((s) => s.fetchHosts);
  const fetchTopology = useHostStore((s) => s.fetchTopology);

  // Open the singleton WebSocket on mount.
  useWebSocket();

  // Initial fetch + polling fallback (in case WS misses events).
  useEffect(() => {
    fetchHosts();
    fetchTopology();
    const id = setInterval(() => {
      fetchHosts();
      fetchTopology();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchHosts, fetchTopology]);

  return (
    <div className="flex h-screen bg-bg text-text overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
      <ToastContainer />
    </div>
  );
}