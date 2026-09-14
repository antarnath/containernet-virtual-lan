// Top-level routing. Each route is rendered inside the shared Layout
// (sidebar + topbar + content area).
//
// Phase 04 introduces project-scoped routes:
//   /builder                       — LAN Builder form (create a new project)
//   /projects                      — grid of project cards
//   /projects/:projectId/topology  — interactive topology view + lifecycle controls
//
// Phase 05 adds per-project hosts:
//   /projects/:projectId/hosts     — hosts list + live metrics for one project
//
// Legacy global routes (/topology, /hosts, /communications) are kept for
// now — they still work against the static ContainerNet while we
// transition. They'll be removed in Phase 09 polish.

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/layout/Layout';
import Dashboard from './pages/Dashboard';
import TopologyPage from './pages/TopologyPage';
import HostsPage from './pages/HostsPage';
import CommunicationsPage from './pages/CommunicationsPage';
import LANBuilderPage from './pages/LANBuilderPage';
import ProjectsPage from './pages/ProjectsPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/builder" element={<LANBuilderPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route
            path="/projects/:projectId/topology"
            element={<TopologyPage />}
          />
          <Route
            path="/projects/:projectId/hosts"
            element={<HostsPage />}
          />
          {/* Legacy global routes — kept during transition. */}
          <Route path="/topology" element={<TopologyPage />} />
          <Route path="/hosts" element={<HostsPage />} />
          <Route path="/communications" element={<CommunicationsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
