// AttacksView — the per-project attacks page (route
// /projects/:projectId/attacks). One card per attacker with a
// mini-controls + the full timeline of all signals from all
// attackers (newest first). Polls /attacks every 2s to keep the
// live counters fresh; the realtime store feeds in new signals
// instantly.

import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Button, Card, StatusPill, toast } from '../components/ui';
import { ProjectsAPI, type AttackRecord, type AttackSignalRow, type AttackMode } from '../api/client';
import { useRealtimeStore } from '../store/realtimeStore';
import { useProjectStore } from '../store/projectStore';
import type { ProjectNode } from '../types';

const POLL_INTERVAL_MS = 2000;
const ACTIVE_PRUNE_MS = 10_000;

const MODE_LABEL: Record<AttackMode, string> = {
  unknown_host: 'Unknown Host',
  duplicate_ip: 'Duplicate IP',
  arp_spoof: 'ARP Spoof',
  tcp_flood: 'TCP SYN Flood',
  http_flood: 'HTTP Flood',
};

export function AttacksView() {
  const { projectId } = useParams<{ projectId: string }>();
  const current = useProjectStore((s) => s.current);
  const fetchProject = useProjectStore((s) => s.fetchProject);
  const [attacks, setAttacks] = useState<AttackRecord[]>([]);
  const [signals, setSignals] = useState<AttackSignalRow[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Realtime: pull attack signals as they arrive.
  const realtimeSignals = useRealtimeStore((s) => s.attackSignals);
  const pruneActive = useRealtimeStore((s) => s.pruneActiveAttackers);

  // Poll /attacks every 2s.
  useEffect(() => {
    if (!projectId) return;
    const pid = projectId;
    let alive = true;
    async function tick() {
      try {
        const res = await ProjectsAPI.attacks.list(pid);
        if (alive) setAttacks(res.attacks || []);
      } catch {
        // ignore
      }
    }
    void tick();
    const t = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [projectId]);

  // Poll every attacker's signals every 5s.
  useEffect(() => {
    if (!projectId || attacks.length === 0) return;
    const pid = projectId;
    let alive = true;
    async function tick() {
      try {
        const lists = await Promise.all(
          attacks.map((a) => ProjectsAPI.attacks.signals(pid, a.node_id, 30)),
        );
        if (!alive) return;
        // Merge, newest first, dedup by id.
        const byId = new Map<string, AttackSignalRow>();
        for (const l of lists) {
          for (const s of l.signals) {
            byId.set(s.id, s);
          }
        }
        const merged = Array.from(byId.values()).sort((a, b) => {
          const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
          const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
          return tb - ta;
        });
        setSignals(merged);
      } catch {
        // ignore
      }
    }
    void tick();
    const t = setInterval(tick, 5000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [projectId, attacks.map((a) => a.node_id).join(',')]);

  // Sweep the active-attackers set every 10s so the canvas red ring
  // fades when the attack actually stops.
  useEffect(() => {
    const t = setInterval(pruneActive, ACTIVE_PRUNE_MS);
    return () => clearInterval(t);
  }, [pruneActive]);

  // Merge realtime + polled signals so the timeline is live.
  const mergedSignals = useMemo(() => {
    const byId = new Map<string, AttackSignalRow>();
    for (const s of signals) byId.set(s.id, s);
    for (const list of realtimeSignals.values()) {
      for (const s of list) {
        byId.set(s.id, s as AttackSignalRow);
      }
    }
    return Array.from(byId.values()).sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
      return tb - ta;
    });
  }, [signals, realtimeSignals]);

  async function startAttack(a: AttackRecord) {
    if (!projectId) return;
    setBusyId(a.node_id);
    try {
      const target = (current?.nodes ?? []).find(
        (n: ProjectNode) => n.id !== a.node_id && n.kind !== 'router' && n.kind !== 'switch' && n.kind !== 'attacker',
      );
      if (!target) {
        toast.warning('No target', 'Add a host/server first.');
        return;
      }
      const mode = (a.state.mode ?? a.attack_mode ?? 'arp_spoof') as AttackMode;
      const res = await ProjectsAPI.attacks.start(projectId, a.node_id, {
        mode,
        target_node_id: target.id,
      });
      if (res.ok) {
        toast.success(`Started ${MODE_LABEL[mode]}`, `→ ${target.name}`);
      } else {
        toast.error('Start failed', res.error || 'see logs');
      }
    } catch (e) {
      toast.error('Error', (e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function stopAttack(a: AttackRecord) {
    if (!projectId) return;
    setBusyId(a.node_id);
    try {
      const res = await ProjectsAPI.attacks.stop(projectId, a.node_id);
      if (res.ok) toast.success('Attack stopped');
      else toast.error('Stop failed', res.error || 'see logs');
    } catch (e) {
      toast.error('Error', (e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  if (!projectId) {
    return <div className="p-8 text-text-muted">Project not found.</div>;
  }

  // Hydrate the full project detail (needed for the node list) if
  // we don't have it yet.
  useEffect(() => {
    if (!current || current.id !== projectId) {
      void fetchProject(projectId);
    }
  }, [current, fetchProject, projectId]);

  const attackers = attacks.filter((a) => a.container_id);

  return (
    <div className="flex flex-col h-full bg-bg-app">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border bg-bg-surface flex items-center gap-4 flex-shrink-0">
        <div className="flex-1 min-w-0">
          <div className="text-lg font-semibold text-text-primary">
            Attacks
          </div>
          <div className="text-2xs text-text-muted font-mono">
            {current?.name ?? projectId} — {attackers.length} attacker{attackers.length === 1 ? '' : 's'}
          </div>
        </div>
        <Link to={`/projects/${projectId}`}>
          <Button variant="ghost" size="sm">← Back to canvas</Button>
        </Link>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-6 space-y-6">
        {/* Per-attacker cards */}
        <section>
          <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-3">
            Attackers
          </h2>
          {attackers.length === 0 ? (
            <Card>
              <div className="text-2xs text-text-muted text-center py-4">
                No attacker nodes. Add one from the canvas toolbox.
              </div>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {attackers.map((a) => (
                <AttackerCard
                  key={a.node_id}
                  attack={a}
                  busy={busyId === a.node_id}
                  onStart={() => startAttack(a)}
                  onStop={() => stopAttack(a)}
                />
              ))}
            </div>
          )}
        </section>

        {/* Live timeline */}
        <section>
          <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-3">
            Live signal timeline
          </h2>
          {mergedSignals.length === 0 ? (
            <Card>
              <div className="text-2xs text-text-muted text-center py-4">
                No signals yet. Start an attack to see live detection.
              </div>
            </Card>
          ) : (
            <div className="space-y-2">
              {mergedSignals.map((s) => (
                <TimelineRow
                  key={s.id}
                  signal={s}
                  attackerName={attackers.find((a) => a.node_id === s.attacker_node_id)?.name ?? '?'}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function AttackerCard({
  attack,
  busy,
  onStart,
  onStop,
}: {
  attack: AttackRecord;
  busy: boolean;
  onStart: () => void;
  onStop: () => void;
}) {
  const running = attack.state.running;
  const mode = attack.state.mode ?? attack.attack_mode;
  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-text-primary truncate flex items-center gap-1.5">
            {attack.name}
            {running && (
              <span className="inline-flex items-center gap-1 text-2xs px-1.5 py-0.5 rounded font-mono font-bold uppercase bg-danger text-white animate-pulse">
                attacking
              </span>
            )}
          </div>
          <div className="text-2xs text-text-muted font-mono mt-0.5">
            {mode ? MODE_LABEL[mode as AttackMode] ?? mode : 'no mode'}
          </div>
        </div>
        <StatusPill
          tone={attack.container_status === 'running' ? 'running' : 'stopped'}
        >
          {attack.container_status}
        </StatusPill>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-3">
        <div>
          <div className="text-2xs text-text-muted uppercase tracking-wider">
            Pkts sent
          </div>
          <div className="text-base font-mono text-text-primary">
            {attack.state.packets_sent}
          </div>
        </div>
        <div>
          <div className="text-2xs text-text-muted uppercase tracking-wider">
            Pkts / sec
          </div>
          <div className="text-base font-mono text-text-primary">
            {Number(attack.state.packets_per_sec.toFixed(1))}
          </div>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        {!running ? (
          <Button
            variant="primary"
            size="sm"
            onClick={onStart}
            disabled={busy || !attack.attack_mode}
            className="flex-1"
          >
            ▶ Start
          </Button>
        ) : (
          <Button
            variant="danger"
            size="sm"
            onClick={onStop}
            disabled={busy}
            className="flex-1"
          >
            ⏹ Stop
          </Button>
        )}
      </div>
    </Card>
  );
}

const SIGNAL_KIND_LABEL: Record<string, string> = {
  arp_rate: 'ARP rate exceeded',
  syn_rate: 'SYN rate exceeded',
  http_rate: 'HTTP rate exceeded',
  new_mac: 'New MAC on link',
  duplicate_ip: 'Duplicate IP detected',
};

const SIGNAL_KIND_TONE: Record<string, 'warn' | 'danger'> = {
  arp_rate: 'warn',
  syn_rate: 'danger',
  http_rate: 'danger',
  new_mac: 'warn',
  duplicate_ip: 'warn',
};

function TimelineRow({
  signal,
  attackerName,
}: {
  signal: AttackSignalRow;
  attackerName: string;
}) {
  const tone = SIGNAL_KIND_TONE[signal.signal_kind] ?? 'warn';
  const label = SIGNAL_KIND_LABEL[signal.signal_kind] ?? signal.signal_kind;
  return (
    <div
      className={[
        'px-3 py-2 rounded border-l-2 bg-bg-surface border border-border',
        tone === 'danger' ? 'border-l-danger' : 'border-l-warn',
      ].join(' ')}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-xs font-medium text-text-primary">
          <span className="font-mono text-text-muted">{attackerName}</span>
          {' — '}
          {label}
        </div>
        <div className="text-2xs text-text-muted font-mono">
          {signal.created_at ? new Date(signal.created_at).toLocaleTimeString() : ''}
        </div>
      </div>
      <div className="text-2xs text-text-muted font-mono mt-0.5">
        value={signal.value.toFixed(2)}  threshold={signal.threshold}  window={signal.window_sec}s
      </div>
    </div>
  );
}