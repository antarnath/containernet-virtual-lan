// RouterPanel — side panel that opens when the user clicks a router
// on the canvas. Polls the live router state every 2s, shows
// routes / ARP / interfaces in three tabs, and surfaces anomaly
// events from the realtime store (the project-wide WebSocket
// connection).
//
// Design system contract (§7.3): header strip + tabs + tab body +
// footer. Uses Table for the three data tables and AnomalyBanner
// for live alerts.

import { useEffect, useMemo, useState } from 'react';

import {
  AnomalyBanner,
  Button,
  Card,
  LoadingSkeleton,
  StatusPill,
  Table,
  type TableColumn,
} from '../components/ui';
import { ProjectsAPI, type AnomalyEvent, type NodeLiveState } from '../api/client';
import { useRealtimeStore } from '../store/realtimeStore';

type Tab = 'routes' | 'arp' | 'ifaces';

export type { AnomalyEvent };

export interface RouterPanelProps {
  projectId: string;
  nodeId: string;
  nodeName: string;
  containerStatus: string;
  onClose: () => void;
}

const POLL_INTERVAL_MS = 2000;

export function RouterPanel({
  projectId,
  nodeId,
  nodeName,
  containerStatus,
  onClose,
}: RouterPanelProps) {
  const [tab, setTab] = useState<Tab>('routes');
  const [state, setState] = useState<NodeLiveState['router'] | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastTick, setLastTick] = useState(Date.now());
  const [pollError, setPollError] = useState<string | null>(null);

  // Pull from the project-wide realtime store. Filtered to this node.
  const allAnomalies = useRealtimeStore((s) => s.anomalies);
  const dismissAnomaly = useRealtimeStore((s) => s.dismissAnomaly);
  const dismissedIds = useRealtimeStore((s) => s.dismissedIds);
  const anomalies = useMemo(
    () =>
      allAnomalies
        .filter((a) => a.node_id === nodeId)
        // Hide anything the user has already dismissed locally.
        .filter((a) => !dismissedIds.has(a.id)),
    [allAnomalies, nodeId, dismissedIds],
  );

  // Poll every 2s. Stop polling when the panel unmounts.
  useEffect(() => {
    let alive = true;
    async function fetchOnce() {
      try {
        const res = await ProjectsAPI.nodes.state(projectId, nodeId);
        if (!alive) return;
        setState(res.router);
        setLoading(false);
        setLastTick(Date.now());
        setPollError(null);
      } catch (e) {
        if (!alive) return;
        setLoading(false);
        setPollError((e as Error).message);
      }
    }
    void fetchOnce();
    const t = setInterval(fetchOnce, POLL_INTERVAL_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [projectId, nodeId]);

  // Re-tick the "last updated" label every second.
  useEffect(() => {
    const t = setInterval(() => setLastTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const openCount = anomalies.filter((a) => !a.resolved_at).length;

  return (
    <aside className="w-[480px] flex-shrink-0 h-full flex flex-col bg-bg-surface border-l border-border animate-slide-in">
      {/* Header strip */}
      <div className="px-4 py-3 border-b border-border flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-text-primary truncate">
            {nodeName}
          </div>
          <div className="text-2xs text-text-muted font-mono mt-0.5">
            router · {state?.ifaces?.[1]?.ip_mask?.split('/')?.[0] || '—'}
          </div>
        </div>
        <StatusPill tone={containerStatus === 'running' ? 'running' : 'stopped'}>
          {containerStatus}
        </StatusPill>
        <div className="text-2xs text-text-muted font-mono whitespace-nowrap">
          {formatLastUpdated(state?.fetched_at, lastTick)}
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close panel">
          ×
        </Button>
      </div>

      {/* Anomaly banner stack (only open ones) */}
      {anomalies.filter((a) => !a.resolved_at).length > 0 && (
        <div className="px-4 pt-3 space-y-2">
          {anomalies
            .filter((a) => !a.resolved_at)
            .slice(0, 3)
            .map((a) => (
              <AnomalyBanner
                key={a.id}
                kind={a.kind}
                severity={a.severity}
                summary={a.summary}
                detail={formatAnomalyDetail(a)}
                createdAt={a.created_at}
                onDismiss={() => {
                  void dismissAnomaly(a.id);
                }}
              />
            ))}
        </div>
      )}

      {/* Tabs */}
      <div className="px-4 pt-3 flex gap-1 border-b border-border">
        <TabButton active={tab === 'routes'} onClick={() => setTab('routes')}>
          Routes
          {state?.routes ? <span className="ml-1 text-2xs text-text-muted">({state.routes.length})</span> : null}
        </TabButton>
        <TabButton active={tab === 'arp'} onClick={() => setTab('arp')}>
          ARP
          {state?.neigh ? <span className="ml-1 text-2xs text-text-muted">({state.neigh.length})</span> : null}
        </TabButton>
        <TabButton active={tab === 'ifaces'} onClick={() => setTab('ifaces')}>
          Interfaces
          {state?.ifaces ? <span className="ml-1 text-2xs text-text-muted">({state.ifaces.length})</span> : null}
        </TabButton>
      </div>

      {/* Tab body */}
      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
        {loading && !state ? (
          <LoadingSkeleton width="100%" height="120px" />
        ) : state?.error ? (
          <Card>
            <div className="text-xs text-danger">
              Could not reach the router agent: {state.error}
            </div>
            <div className="text-2xs text-text-muted mt-1">
              Make sure the project is running and the router's :9090 is reachable.
            </div>
          </Card>
        ) : pollError ? (
          <Card>
            <div className="text-xs text-danger">State poll failed: {pollError}</div>
          </Card>
        ) : tab === 'routes' ? (
          <RoutesTab routes={state?.routes ?? []} />
        ) : tab === 'arp' ? (
          <ArpTab neigh={state?.neigh ?? []} anomalies={anomalies} />
        ) : (
          <IfacesTab ifaces={state?.ifaces ?? []} />
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-border flex items-center justify-between text-2xs text-text-muted">
        <span>
          {openCount} open anomal{openCount === 1 ? 'y' : 'ies'}
        </span>
        <span>polls every 2s</span>
      </div>
    </aside>
  );
}

// ─── tab bodies ────────────────────────────────────────────────────────

type RouteRow = NonNullable<NodeLiveState['router']>['routes'][number];
type NeighRow = NonNullable<NodeLiveState['router']>['neigh'][number];
type IfaceRow = NonNullable<NodeLiveState['router']>['ifaces'][number];

function RoutesTab({ routes }: { routes: RouteRow[] }) {
  const columns: TableColumn<RouteRow>[] = [
    { key: 'destination', label: 'Destination', mono: true, width: '28%' },
    { key: 'gateway', label: 'Gateway', mono: true, width: '24%' },
    { key: 'iface', label: 'Iface', mono: true, width: '14%' },
    { key: 'protocol', label: 'Proto', width: '14%' },
    { key: 'scope', label: 'Scope', width: '10%' },
    { key: 'source', label: 'Source', mono: true, width: '20%' },
  ];
  return <Table columns={columns} rows={routes} emptyMessage="no routes" />;
}

function ArpTab({
  neigh,
  anomalies,
}: {
  neigh: NeighRow[];
  anomalies: AnomalyEvent[];
}) {
  // The set of (ip, old_mac) pairs that have an open anomaly
  // for this router. Outlined rows highlight the offender.
  const anomalyIps = useMemo(() => {
    const s = new Set<string>();
    for (const a of anomalies) {
      if (a.resolved_at) continue;
      if (a.detail && typeof a.detail === 'object' && 'ip' in a.detail) {
        s.add(String((a.detail as Record<string, unknown>).ip));
      }
    }
    return s;
  }, [anomalies]);

  const columns: TableColumn<NeighRow>[] = [
    { key: 'ip', label: 'IP', mono: true, width: '30%' },
    { key: 'iface', label: 'Iface', mono: true, width: '16%' },
    {
      key: 'mac',
      label: 'MAC',
      mono: true,
      width: '34%',
      className: 'text-text-primary',
    },
    { key: 'state', label: 'State', width: '20%' },
  ];
  return (
    <Table
      columns={columns}
      rows={neigh}
      isOutlined={(r) => anomalyIps.has(r.ip)}
      emptyMessage="no neighbours"
    />
  );
}

function IfacesTab({ ifaces }: { ifaces: IfaceRow[] }) {
  const columns: TableColumn<IfaceRow>[] = [
    { key: 'name', label: 'Iface', mono: true, width: '24%' },
    { key: 'state', label: 'State', width: '18%' },
    { key: 'ip_mask', label: 'IP / Mask', mono: true, width: '32%' },
    { key: 'mac', label: 'MAC', mono: true, width: '26%' },
  ];
  return <Table columns={columns} rows={ifaces} emptyMessage="no interfaces" />;
}

// ─── helpers ───────────────────────────────────────────────────────────

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        'px-3 py-2 text-xs font-medium transition-colors duration-fast',
        'border-b-2 -mb-px',
        active
          ? 'text-text-primary border-accent'
          : 'text-text-muted border-transparent hover:text-text-secondary',
      ].join(' ')}
    >
      {children}
    </button>
  );
}

function formatLastUpdated(fetchedAt: number | undefined, now: number): string {
  if (!fetchedAt) return '—';
  const diff = Math.max(0, Math.floor((now - fetchedAt * 1000) / 1000));
  if (diff < 1) return 'just now';
  return `${diff}s ago`;
}

function formatAnomalyDetail(a: AnomalyEvent): string {
  const d = a.detail || {};
  if (a.kind === 'arp_mac_change') {
    return `${d.ip}  ${d.old_mac} → ${d.new_mac}`;
  }
  return JSON.stringify(d);
}
