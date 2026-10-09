// Top-level routing. Each route is rendered inside the shared Layout
// (sidebar + topbar + content area).
//
// M4 routes (this milestone):
//   /                                       — dashboard summary
//   /projects                               — grid of project cards
//   /projects/:projectId/canvas             — interactive topology editor
//   /projects/:projectId/wires/:linkId      — per-wire live packet stream
//
// Future M4 routes (added by later phases):
//   /projects/:projectId/trigger            — trigger panel + console
//   /projects/:projectId/attacks            — attack run + log

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/layout/Layout';
import Dashboard from './pages/Dashboard';
import ProjectsPage from './pages/ProjectsPage';
import ProjectCanvas from './pages/ProjectCanvas';
import WireView from './pages/WireView';
import { AttacksView } from './attacks/AttacksView';
import { LogsView } from './logs/LogsView';
import { ErrorBoundary } from './components/ErrorBoundary';

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route
              path="/projects/:projectId/canvas"
              element={<ProjectCanvas />}
            />
            <Route
              path="/projects/:projectId/wires/:linkId"
              element={<WireView />}
            />
            <Route
              path="/projects/:projectId/attacks"
              element={<AttacksView />}
            />
            <Route
              path="/projects/:projectId/logs"
              element={<LogsView />}
            />
          </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
