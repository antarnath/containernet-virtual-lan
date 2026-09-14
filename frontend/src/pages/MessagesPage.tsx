// Per-project Messages page — Phase 08.
//
// Renders one console per host in the project. Layout:
//   * ≤ 6 hosts — CSS grid (1/2/3 columns depending on viewport).
//   * > 6 hosts — tabs at the top, one tab per host, click to switch.
//
// Each console streams messages in real time via the WS "message" event.
// On mount, fetches the last 100 messages per host via REST for hydration.

import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import MessageWindow from '../components/message-window/MessageWindow';
import { useMessageStore } from '../store/messageStore';
import { useProjectStore } from '../store/projectStore';

const GRID_THRESHOLD = 6;

export default function MessagesPage() {
  const { projectId } = useParams<{ projectId?: string }>();
  if (!projectId) {
    return (
      <div className="text-muted">Pick a project from the sidebar.</div>
    );
  }
  return <ProjectMessagesPage projectId={projectId} />;
}

function ProjectMessagesPage({ projectId }: { projectId: string }) {
  const fetchProject = useProjectStore((s) => s.fetchProject);
  const project = useProjectStore((s) =>
    s.current?.id === projectId ? s.current : null,
  );

  useEffect(() => {
    void fetchProject(projectId);
  }, [projectId, fetchProject]);

  const hosts = project?.hosts ?? [];
  const sortedHosts = useMemo(
    () =>
      [...hosts].sort((a, b) => {
        // Numeric sort on the host-N suffix; falls back to lexicographic.
        const an = parseInt(a.host_id.replace(/\D/g, ''), 10);
        const bn = parseInt(b.host_id.replace(/\D/g, ''), 10);
        if (!Number.isNaN(an) && !Number.isNaN(bn) && an !== bn) return an - bn;
        return a.host_id.localeCompare(b.host_id);
      }),
    [hosts],
  );

  const clearProjectMessages = useMessageStore((s) => s.clearProjectMessages);

  const useTabs = sortedHosts.length > GRID_THRESHOLD;
  const [activeTab, setActiveTab] = useState<string | null>(
    sortedHosts[0]?.host_id ?? null,
  );

  // Reset active tab when hosts change.
  useEffect(() => {
    if (!activeTab && sortedHosts.length > 0) {
      setActiveTab(sortedHosts[0].host_id);
    } else if (
      activeTab &&
      !sortedHosts.some((h) => h.host_id === activeTab) &&
      sortedHosts.length > 0
    ) {
      setActiveTab(sortedHosts[0].host_id);
    }
  }, [sortedHosts, activeTab]);

  if (sortedHosts.length === 0) {
    return (
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-text">Messages</h1>
            <p className="text-sm text-muted mt-1">
              One console per host. Start the project to spawn hosts.
            </p>
          </div>
          <Link
            to={`/projects/${projectId}/topology`}
            className="text-sm bg-panel border border-border text-text px-3 py-2 rounded-md hover:border-accent"
          >
            ← Back to topology
          </Link>
        </div>
        <div className="text-muted text-sm py-12 text-center bg-panel border border-border rounded-xl">
          This project has no hosts yet. Open the Topology page and click
          Start, or create a project from the LAN Builder.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text">
            Messages
            <span className="ml-2 text-sm font-normal text-muted">
              {project?.name ?? projectId}
            </span>
          </h1>
          <p className="text-sm text-muted mt-1">
            One console per host. Outgoing messages are blue (right-aligned),
            incoming are green (left-aligned). Auto-scrolls until you scroll
            up.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              if (
                confirm(
                  'Clear every in-memory message console for this project? Backend history is preserved.',
                )
              ) {
                clearProjectMessages(projectId);
              }
            }}
            className="text-xs bg-panel border border-border text-muted px-3 py-2 rounded-md hover:text-text hover:border-accent"
          >
            Clear all
          </button>
          <Link
            to={`/projects/${projectId}/topology`}
            className="text-sm bg-panel border border-border text-text px-3 py-2 rounded-md hover:border-accent"
          >
            ← Topology
          </Link>
        </div>
      </div>

      {useTabs ? (
        <div className="space-y-4">
          {/* Tabs */}
          <div className="flex flex-wrap gap-1 bg-panel border border-border rounded-lg p-1">
            {sortedHosts.map((h) => {
              const active = h.host_id === activeTab;
              return (
                <button
                  key={h.host_id}
                  onClick={() => setActiveTab(h.host_id)}
                  className={`text-xs px-3 py-1.5 rounded-md transition-colors ${
                    active
                      ? 'bg-accent text-white'
                      : 'text-muted hover:text-text hover:bg-panel2'
                  }`}
                >
                  {h.hostname}
                </button>
              );
            })}
          </div>
          {/* Active console */}
          {sortedHosts
            .filter((h) => h.host_id === activeTab)
            .map((h) => (
              <MessageWindow
                key={h.host_id}
                projectId={projectId}
                host={h}
              />
            ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sortedHosts.map((h) => (
            <MessageWindow
              key={h.host_id}
              projectId={projectId}
              host={h}
            />
          ))}
        </div>
      )}
    </div>
  );
}