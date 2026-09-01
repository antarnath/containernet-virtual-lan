// Top-level routing. Each route is rendered inside the shared Layout
// (sidebar + topbar + content area).

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/layout/Layout';
import Dashboard from './pages/Dashboard';
import TopologyPage from './pages/TopologyPage';
import HostsPage from './pages/HostsPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/topology" element={<TopologyPage />} />
          <Route path="/hosts" element={<HostsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
