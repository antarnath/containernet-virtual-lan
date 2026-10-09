// WireView — the M4 phase 04 per-wire page.
//
//   /projects/:projectId/wires/:linkId
//
// Layout (full-screen, escapes the Layout's padding with -m-6):
//   ┌─────────────────────────────────────────┐
//   │ WireViewHeader (breadcrumb + status)    │  48px
//   ├─────────────────────────────────────────┤
//   │ WireViewTabs (Raw / Conv / Attackers)   │  36px
//   ├─────────────────────────────────────────┤
//   │ PacketFilter (chip row)                 │  40px
//   ├─────────────────────────────────────────┤
//   │                                         │
//   │  PacketList (auto-scroll, 32px rows)    │  flex
//   │                                         │
//   └─────────────────────────────────────────┘
//
// The packet stream itself comes from usePacketStream (SSE).
// Recent / pause / clear are exposed in the header.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useProjectStore } from '../store/projectStore';
import { useRealtimeStore } from '../store/realtimeStore';
import { Button, Card, EmptyState, LoadingSkeleton, toast } from '../components/ui';
import { WireViewHeader } from '../wire-view/WireViewHeader';
import { WireViewTabs } from '../wire-view/WireViewTabs';
import { PacketFilter } from '../wire-view/PacketFilter';
import { PacketList } from '../wire-view/PacketList';
import { usePacketStream } from '../wire-view/usePacketStream';
import type { PacketFilter as PacketFilterState, WireViewTab } from '../wire-view/types';

export default function WireView() {
  const { projectId, linkId } = useParams<{ projectId: string; linkId: string }>();
  const navigate = useNavigate();

  const current = useProjectStore((s) => s.current);
  const loading = useProjectStore((s) => s.currentLoading);
  const error = useProjectStore((s) => s.currentError);
  const fetchProject = useProjectStore((s) => s.fetchProject);
  const clearCurrent = useProjectStore((s) => s.clearCurrent);

  // Connect the realtime store so canvas / other consumers stay in sync.
  useEffect(() => {
    if (!projectId) return;
    useRealtimeStore.getState().connect(projectId);
    return () => {
      useRealtimeStore.getState().disconnect();
    };
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    void fetchProject(projectId);
    return () => {
      clearCurrent();
    };
  }, [projectId, fetchProject, clearCurrent]);

  const [tab, setTab] = useState<WireViewTab>('raw');
  const [filter, setFilter] = useState<PacketFilterState>({
    protocols: new Set(),
    attackOnly: false,
  });

  // SSE stream. We open it for every page mount and let the hook
  // close it on unmount.
  const stream = usePacketStream(projectId ?? null, linkId ?? null);
  const { packets, paused, status, pause, resume, clear } = stream;

  const link = useMemo(() => {
    if (!current) return null;
    return current.links.find((l) => l.id === linkId) ?? null;
  }, [current, linkId]);

  const wireLabel = link?.subnet_cidr ?? '';
  const attackerCount = useMemo(
    () => packets.filter((p) => p.src_node_kind === 'attacker').length,
    [packets],
  );

  const handleTogglePause = useCallback(() => {
    if (paused) resume();
    else pause();
  }, [paused, pause, resume]);

  const handleClear = useCallback(() => {
    clear();
  }, [clear]);

  if (error) {
    return (
      <div className="h-full flex items-center justify-center p-6">
        <Card className="max-w-md w-full">
          <div className="text-sm font-semibold text-text-primary mb-1">
            Could not load project
          </div>
          <div className="text-xs text-text-secondary mb-4">{error}</div>
          <Button variant="secondary" onClick={() => navigate('/projects')}>
            Back to projects
          </Button>
        </Card>
      </div>
    );
  }

  if (loading || !current || current.id !== projectId) {
    return (
      <div className="h-full flex flex-col">
        <div className="h-12 border-b border-border flex items-center px-4 gap-3 bg-bg-surface">
          <LoadingSkeleton width="160px" height="14px" />
          <LoadingSkeleton width="80px" height="20px" />
        </div>
        <div className="flex-1 flex items-center justify-center">
          <LoadingSkeleton width="220px" height="14px" />
        </div>
      </div>
    );
  }

  if (!link) {
    return (
      <div className="h-full flex items-center justify-center p-6">
        <EmptyState
          title="Link not found"
          description={`The wire ${linkId} doesn't belong to project ${current.name}.`}
          action={
            <Button variant="secondary" onClick={() => navigate(`/projects/${current.id}/canvas`)}>
              Back to canvas
            </Button>
          }
        />
      </div>
    );
  }

  // Apply the active tab to the visible packet list:
  //   * 'raw'         → show everything (subject to filter)
  //   * 'attackers'   → show only attacker-sourced packets
  //   * 'conversations' → placeholder; show a "coming soon" hint
  const tabFilter: PacketFilterState =
    tab === 'attackers'
      ? { protocols: new Set(), attackOnly: true }
      : tab === 'raw'
        ? filter
        : filter;

  return (
    <div className="h-full flex flex-col -m-6">
      <WireViewHeader
        projectId={current.id}
        projectName={current.name}
        projectStatus={current.status}
        wireLabel={wireLabel}
        paused={paused}
        onTogglePause={handleTogglePause}
        onClear={handleClear}
        packetCount={packets.length}
      />
      <WireViewTabs
        active={tab}
        onChange={setTab}
        counts={{ raw: packets.length, attackers: attackerCount }}
      />
      {tab === 'conversations' ? (
        <div className="flex-1 min-h-0 flex items-center justify-center p-6 text-text-secondary text-sm">
          <Card className="max-w-md w-full text-center">
            <div className="text-sm font-semibold text-text-primary mb-1">
              Conversations
            </div>
            <div className="text-xs">
              Per-5-tuple grouping arrives in a later phase. The Raw and
              Attackers tabs stream every packet on this wire in real time.
            </div>
          </Card>
        </div>
      ) : (
        <>
          <PacketFilter filter={tabFilter} onChange={setFilter} />
          <PacketList
            packets={packets}
            filter={tabFilter}
            paused={paused}
            wireLabel={wireLabel}
          />
          {status !== 'open' && packets.length === 0 && (
            <div className="px-3 py-1 text-2xs font-mono text-text-muted text-center">
              stream {status}…
            </div>
          )}
          {status === 'error' && packets.length > 0 && (
            <div className="px-3 py-1 text-2xs font-mono text-warn text-center">
              stream lost; retrying…
            </div>
          )}
        </>
      )}
    </div>
  );
}
