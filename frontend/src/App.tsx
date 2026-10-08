// Top-level routing. Each route is rendered inside the shared Layout
// (sidebar + topbar + content area).
//
// M4 routes (this milestone):
//   /                                 — dashboard summary
//   /projects                         — grid of project cards
//   /projects/:projectId/canvas       — interactive topology editor
//
// Future M4 routes (added by later phases):
//   /projects/:projectId/wires        — per-wire capture view
//   /projects/:projectId/trigger      — trigger panel + console
//   /projects/:projectId/attacks      — attack run + log
//   /projects/:projectId/router       — router configuration panel

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/layout/Layout';
import Dashboard from './pages/Dashboard';
import ProjectsPage from './pages/ProjectsPage';
import ProjectCanvas from './pages/ProjectCanvas';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route
            path="/projects/:projectId/canvas"
            element={<ProjectCanvas />}
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
