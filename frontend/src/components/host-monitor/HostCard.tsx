// Card for a single host — used on the Hosts page.
//
// Phase 05: when a `projectId` is passed the card shows live CPU/RAM/
// network fetched from the project's per-host metrics endpoint. Without a
// `projectId` (legacy global /hosts page) we fall back to the bare card.

import { useEffect } from 'react';
import type { Host, HostMetricsSnapshot, ProjectHost } from '../../types';
import StatusLED from '../topology/StatusLED';
import { useHostStore } from '../../store/hostStore';

interface LegacyProps {
  host: Host;
  projectId?: never;
}

interface ProjectProps {
  host: ProjectHost;
  projectId: string;
}

type Props = LegacyProps | ProjectProps;

function formatTime(iso: string | null | undefined): string {
  if (!iso) return 'never';
  const d = new Date(iso);
  return d.toLocaleTimeString();
}

function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  if (n < 1024) return `${n} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(1)} ${units[i]}`;
}

function formatUptime(s: number | null | undefined): string {
  if (s === null || s === undefined) return '—';
  if (s < 60) return `${Math.floor(s)} s`;
  if (s < 3600) return `${Math.floor(s / 60)} m`;
  if (s < 86400) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h} h ${m} m`;
  }
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  return `${d} d ${h} h`;
}

export default function HostCard(props: Props) {
  const { host } = props;
  const isProjectHost = 'projectId' in props && props.projectId !== undefined;
  const projectId = isProjectHost ? props.projectId : undefined;

  const snapshot = useHostStore((s) =>
    projectId
      ? s.metrics[projectId]?.[host.host_id] ?? null
      : null,
  );
  const fetchHostMetrics = useHostStore((s) => s.fetchHostMetrics);

  // Poll metrics for this host every 10s (Phase 05 spec).
  useEffect(() => {
    if (!projectId) return;
    fetchHostMetrics(projectId, host.host_id);
    const id = setInterval(
      () => fetchHostMetrics(projectId, host.host_id),
      10_000,
    );
    return () => clearInterval(id);
  }, [projectId, host.host_id, fetchHostMetrics]);

  return (
    <div className="bg-panel border border-border rounded-xl p-5 hover:border-accent transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <StatusLED status={host.status} size="sm" />
          <div>
            <div className="text-lg font-semibold text-text">{host.hostname}</div>
            <div className="text-xs text-muted font-mono">{host.host_id}</div>
          </div>
        </div>
        <span
          className={`text-[10px] uppercase tracking-wider px-2 py-1 rounded ${
            host.status === 'online'
              ? 'bg-online/20 text-online'
              : host.status === 'offline'
              ? 'bg-offline/20 text-offline'
              : 'bg-unknown/20 text-unknown'
          }`}
        >
          {host.status}
        </span>
      </div>

      <div className="space-y-1 text-sm">
        <Row label="IP address" value={host.ip_address} mono />
        <Row label="Last heartbeat" value={formatTime(host.last_seen)} mono />
        {'created_at' in host && (
          <Row label="Registered" value={formatTime(host.created_at)} mono />
        )}
      </div>

      {/* Phase 05 — live metrics block */}
      {projectId && (
        <div className="mt-4 pt-4 border-t border-border space-y-2 text-sm">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase tracking-wider text-muted">
              Live metrics
            </span>
            {snapshot?.fetched_at && (
              <span className="text-[10px] text-muted font-mono">
                {formatTime(new Date(snapshot.fetched_at).toISOString())}
              </span>
            )}
          </div>
          {snapshot?.error ? (
            <div className="text-xs text-offline bg-offline/10 border border-offline/30 rounded p-2">
              metrics unavailable: {snapshot.error}
            </div>
          ) : (
            <MetricsRow snapshot={snapshot} />
          )}
        </div>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex justify-between">
      <span className="text-muted">{label}</span>
      <span className={`text-text ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}

function MetricsRow({ snapshot }: { snapshot: HostMetricsSnapshot | null }) {
  if (!snapshot) {
    return (
      <div className="text-xs text-muted">Loading metrics…</div>
    );
  }
  const cpu = snapshot.cpu_percent?.toFixed(1) ?? '—';
  const mem = snapshot.memory_percent?.toFixed(1) ?? '—';
  const rx = formatBytes(snapshot.network_rx_bytes);
  const tx = formatBytes(snapshot.network_tx_bytes);
  const up = formatUptime(snapshot.uptime_seconds);

  return (
    <div className="grid grid-cols-2 gap-2">
      <Mini label="CPU %" value={`${cpu}`} />
      <Mini label="Mem %" value={`${mem}`} />
      <Mini label="Net RX" value={rx} />
      <Mini label="Net TX" value={tx} />
      <Mini label="Uptime" value={up} wide />
    </div>
  );
}

function Mini({
  label,
  value,
  wide = false,
}: {
  label: string;
  value: string;
  wide?: boolean;
}) {
  return (
    <div
      className={`bg-bg border border-border rounded-md px-2 py-1.5 ${
        wide ? 'col-span-2' : ''
      }`}
    >
      <div className="text-[9px] uppercase tracking-wider text-muted">
        {label}
      </div>
      <div className="text-xs font-mono text-text mt-0.5">{value}</div>
    </div>
  );
}