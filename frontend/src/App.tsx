// Top-level routing. Each route is rendered inside the shared Layout
// (sidebar + topbar + content area).
//
// Project-scoped routes:
//   /builder                       — LAN Builder form (create a new project)
//   /projects                      — grid of project cards
//   /projects/:projectId/topology  — interactive topology view + lifecycle controls
//   /projects/:projectId/hosts     — hosts list + live metrics for one project
//   /projects/:projectId/communications — trigger panel + log for one project
//   /projects/:projectId/messages  — one console per host, streams in real time
//
// Legacy global routes (/topology, /hosts, /communications) are kept for
// the static ContainerNet edition. They render a project-less view that
// reads the legacy flat endpoints; new code should target the per-project
// routes above.

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/layout/Layout';
import Dashboard from './pages/Dashboard';
import TopologyPage from './pages/TopologyPage';
import HostsPage from './pages/HostsPage';
import CommunicationsPage from './pages/CommunicationsPage';
import MessagesPage from './pages/MessagesPage';
import LANBuilderPage from './pages/LANBuilderPage';
import ProjectsPage from './pages/ProjectsPage';
import ProjectLog from './pages/ProjectLog';

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
          <Route
            path="/projects/:projectId/communications"
            element={<CommunicationsPage />}
          />
          <Route
            path="/projects/:projectId/messages"
            element={<MessagesPage />}
          />
          <Route
            path="/projects/:projectId/log"
            element={<ProjectLog />}
          />
          {/* Legacy global routes for the static edition. New code should
              target the per-project routes above. */}
          <Route path="/topology" element={<TopologyPage />} />
          <Route path="/hosts" element={<HostsPage />} />
          <Route path="/communications" element={<CommunicationsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
