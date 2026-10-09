// AttackerPanel — the side panel that opens when the user clicks an
// attacker node. Two tabs:
//
//   * Controls — pick a mode, click Start/Stop, see live counters
//   * Signals  — the per-attacker signal feed (uses the realtime
//                store for live updates; REST snapshot on mount)
//
// A teaching card at the bottom renders the markdown lesson for the
// currently selected mode. The markdown is loaded via
// `import.meta.glob` and rendered with a tiny inline renderer — no
// `react-markdown` dep.

import { useEffect, useMemo, useState } from 'react';

import { Button, Card, StatusPill, toast } from '../components/ui';
import { ProjectsAPI, type AttackMode, type AttackerState, type AttackSignalRow } from '../api/client';
import { useRealtimeStore } from '../store/realtimeStore';
import { Markdown } from './Markdown';
import type { ProjectNode } from '../types';

const POLL_INTERVAL_MS = 2000;
const SIGNAL_POLL_MS = 5000;

// Map mode → human label + accent color
const MODE_LABEL: Record<AttackMode, string> = {
  unknown_host: 'Unknown Host',
  duplicate_ip: 'Duplicate IP',
  arp_spoof: 'ARP Spoof',
  tcp_flood: 'TCP SYN Flood',
  http_flood: 'HTTP Flood',
};

// Load all lesson markdowns eagerly. Keys look like:
//   '../attacks/lessons/arp_spoof.md'
// → strip the prefix and `.md` to get the mode key.
const LESSONS: Record<AttackMode, string> = Object.fromEntries(
  Object.entries(
    (import.meta as unknown as {
      glob: (
        pattern: string,
        opts: { query: string; import: string; eager: boolean },
      ) => Record<string, string>;
    }).glob('./lessons/*.md', {
      query: '?raw',
      import: 'default',
      eager: true,
    }),
  ).map(([k, v]) => {
    const match = k.match(/\/([\w_]+)\.md$/);
    return [match?.[1] ?? 'unknown', v] as const;
  }),
) as Record<AttackMode, string>;

export interface AttackerPanelProps {
  projectId: string;
  nodeId: string;
  nodeName: string;
  containerStatus: string;
  nodes: ProjectNode[];
  onClose: () => void;
}

export function AttackerPanel({
  projectId,
  nodeId,
  nodeName,
  containerStatus,
  nodes,
  onClose,
}: AttackerPanelProps) {
  const [mode, setMode] = useState<AttackMode>('arp_spoof');
  const [state, setState] = useState<AttackerState | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<'controls' | 'signals'>('controls');

  // Derive a target: the first non-router, non-self node on the
  // attacker's first link. (We don't query the backend for this —
  // the same heuristic the backend uses. If there's no peer, the
  // user can still set the target manually via the per-mode fields.)
  const targetNode = useMemo(() => {
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return null;
    // Find the iface for this node. The "peer" iface is the one on
    // the other end of any link attached to this node.
    // (We get this from the API; the simplest read is to look at
    // the *other* node on the first link of this attacker.)
    // For now, just take any non-router, non-attacker node — the
    // attacker UI shows its name as the target.
    const candidate = nodes.find((n) => n.id !== nodeId && n.kind !== 'router' && n.kind !== 'switch');
    return candidate ?? null;
  }, [nodes, nodeId]);

  // Poll /attacks every 2s to keep the live counters fresh. The
  // attack_detector's signals use the realtime WS, but the engine's
  // own packets_per_sec only changes inside the attacker container,
  // so we have to re-fetch /attacks.
  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const res = await ProjectsAPI.attacks.list(projectId);
        const me = res.attacks.find((a) => a.node_id === nodeId);
        if (alive) setState(me?.state ?? null);
      } catch {
        // ignore — toast already on a separate path
      }
    }
    void tick();
    const t = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [projectId, nodeId]);

  // Hydrate the lesson for the current mode
  const lessonText = LESSONS[mode] ?? '';

  async function handleStart() {
    if (!targetNode) {
      toast.warning('No target', 'Add a host or server on the same link.');
      return;
    }
    setBusy(true);
    try {
      const res = await ProjectsAPI.attacks.start(projectId, nodeId, {
        mode,
        target_node_id: targetNode.id,
      });
      if (res.ok && res.state) {
        setState(res.state);
        toast.success(`Started ${MODE_LABEL[mode]}`, `→ ${targetNode.name}`);
        setTab('signals');
      } else {
        toast.error('Start failed', res.error || 'see logs');
      }
    } catch (e) {
      toast.error('Error', (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    setBusy(true);
    try {
      const res = await ProjectsAPI.attacks.stop(projectId, nodeId);
      if (res.ok && res.state) {
        setState(res.state);
        toast.success('Attack stopped');
      } else {
        toast.error('Stop failed', res.error || 'see logs');
      }
    } catch (e) {
      toast.error('Error', (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="w-[480px] flex-shrink-0 h-full flex flex-col bg-bg-surface border-l border-border animate-slide-in">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-start gap-3 flex-shrink-0">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-text-primary truncate flex items-center gap-2">
            {nodeName}
            {state?.running && (
              <span className="inline-flex items-center gap-1 text-2xs px-1.5 py-0.5 rounded font-mono font-bold uppercase bg-danger text-white animate-pulse">
                attacking
              </span>
            )}
          </div>
          <div className="text-2xs text-text-muted font-mono mt-0.5">
            attacker
          </div>
        </div>
        <StatusPill
          tone={containerStatus === 'running' ? 'running' : 'stopped'}
        >
          {containerStatus}
        </StatusPill>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close panel">
          ×
        </Button>
      </div>

      {/* Tabs */}
      <div className="px-4 pt-3 flex gap-1 border-b border-border flex-shrink-0">
        <TabButton active={tab === 'controls'} onClick={() => setTab('controls')}>
          Controls
        </TabButton>
        <TabButton active={tab === 'signals'} onClick={() => setTab('signals')}>
          Signals
        </TabButton>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {tab === 'controls' && (
          <ControlsTab
            mode={mode}
            setMode={setMode}
            state={state}
            targetNode={targetNode}
            busy={busy}
            onStart={handleStart}
            onStop={handleStop}
            containerRunning={containerStatus === 'running'}
          />
        )}
        {tab === 'signals' && (
          <SignalsTab
            projectId={projectId}
            attackerId={nodeId}
          />
        )}
        {tab === 'controls' && (
          <div className="px-4 pb-4">
            <div className="text-2xs text-text-muted uppercase tracking-wider mb-2">
              Lesson — {MODE_LABEL[mode]}
            </div>
            <Card>
              <Markdown source={lessonText} />
            </Card>
          </div>
        )}
      </div>
    </aside>
  );
}

// ─── controls tab ──────────────────────────────────────────────────

function ControlsTab({
  mode,
  setMode,
  state,
  targetNode,
  busy,
  onStart,
  onStop,
  containerRunning,
}: {
  mode: AttackMode;
  setMode: (m: AttackMode) => void;
  state: AttackerState | null;
  targetNode: ProjectNode | null;
  busy: boolean;
  onStart: () => void;
  onStop: () => void;
  containerRunning: boolean;
}) {
  const running = state?.running ?? false;
  return (
    <div className="p-4 space-y-4">
      {/* Mode radios */}
      <div>
        <div className="text-2xs text-text-muted uppercase tracking-wider mb-2">
          Mode
        </div>
        <div className="grid grid-cols-1 gap-1.5">
          {(Object.keys(MODE_LABEL) as AttackMode[]).map((m) => (
            <label
              key={m}
              className={[
                'flex items-start gap-2 px-3 py-2 rounded border cursor-pointer',
                'transition-colors',
                mode === m
                  ? 'border-primary bg-primary-soft text-text-primary'
                  : 'border-border bg-bg-app hover:border-primary/50',
              ].join(' ')}
            >
              <input
                type="radio"
                name="attack-mode"
                value={m}
                checked={mode === m}
                onChange={() => setMode(m)}
                className="mt-0.5"
                disabled={running}
              />
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-text-primary">
                  {MODE_LABEL[m]}
                </div>
                <div className="text-2xs text-text-muted font-mono">
                  {m}
                </div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Target */}
      <div>
        <div className="text-2xs text-text-muted uppercase tracking-wider mb-2">
          Target
        </div>
        <Card>
          {targetNode ? (
            <div className="text-xs">
              <div className="font-mono text-text-primary">{targetNode.name}</div>
              <div className="text-2xs text-text-muted mt-0.5">
                {targetNode.interfaces?.[0]?.ip_address ?? '—'}
              </div>
            </div>
          ) : (
            <div className="text-2xs text-text-muted">
              No host/server on a shared link. Add one to the topology.
            </div>
          )}
        </Card>
      </div>

      {/* Live counters */}
      <div>
        <div className="text-2xs text-text-muted uppercase tracking-wider mb-2">
          Live counters
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Counter label="Packets sent" value={state?.packets_sent ?? 0} />
          <Counter
            label="Packets / sec"
            value={Number((state?.packets_per_sec ?? 0).toFixed(1))}
          />
        </div>
      </div>

      {/* Start / Stop */}
      <div className="flex gap-2">
        {!running ? (
          <Button
            variant="primary"
            size="md"
            onClick={onStart}
            disabled={busy || !containerRunning || !targetNode}
            className="flex-1"
          >
            ▶ Start {MODE_LABEL[mode]}
          </Button>
        ) : (
          <Button
            variant="danger"
            size="md"
            onClick={onStop}
            disabled={busy}
            className="flex-1"
          >
            ⏹ Stop attack
          </Button>
        )}
      </div>
      {!containerRunning && (
        <div className="text-2xs text-warn text-center">
          Start the project before running an attack.
        </div>
      )}
    </div>
  );
}

function Counter({ label, value }: { label: string; value: number | string }) {
  return (
    <Card>
      <div className="text-2xs text-text-muted uppercase tracking-wider">
        {label}
      </div>
      <div className="text-lg font-mono text-text-primary mt-0.5">
        {value}
      </div>
    </Card>
  );
}

// ─── signals tab ───────────────────────────────────────────────────

function SignalsTab({
  projectId,
  attackerId,
}: {
  projectId: string;
  attackerId: string;
}) {
  const realtimeSignals = useRealtimeStore((s) => s.attackSignals.get(attackerId) ?? []);
  const [history, setHistory] = useState<AttackSignalRow[]>([]);

  // Pull the full history on mount + every 5s (the realtime store
  // holds the recent 50, but the user might scroll the list and want
  // the older rows).
  useEffect(() => {
    let alive = true;
    async function tick() {
      try {
        const res = await ProjectsAPI.attacks.signals(projectId, attackerId, 50);
        if (alive) setHistory(res.signals || []);
      } catch {
        // ignore
      }
    }
    void tick();
    const t = setInterval(tick, SIGNAL_POLL_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [projectId, attackerId]);

  // Merge: realtime takes precedence on the top of the list, then
  // history fills in anything we haven't seen yet.
  const merged = useMemo(() => {
    const seen = new Set<string>();
    const out: AttackSignalRow[] = [];
    for (const s of realtimeSignals) {
      if (!seen.has(s.id)) {
        out.push(s as AttackSignalRow);
        seen.add(s.id);
      }
    }
    for (const s of history) {
      if (!seen.has(s.id)) {
        out.push(s);
        seen.add(s.id);
      }
    }
    return out;
  }, [realtimeSignals, history]);

  if (merged.length === 0) {
    return (
      <div className="p-6 text-2xs text-text-muted text-center">
        No signals yet. Start an attack to see live detection.
      </div>
    );
  }

  return (
    <div className="p-3 space-y-2">
      {merged.map((s) => (
        <SignalRow key={s.id} signal={s} />
      ))}
    </div>
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

function SignalRow({ signal }: { signal: AttackSignalRow }) {
  const tone = SIGNAL_KIND_TONE[signal.signal_kind] ?? 'warn';
  const label = SIGNAL_KIND_LABEL[signal.signal_kind] ?? signal.signal_kind;
  return (
    <div
      className={[
        'px-3 py-2 rounded border-l-2 bg-bg-app border border-border',
        tone === 'danger' ? 'border-l-danger' : 'border-l-warn',
      ].join(' ')}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-xs font-medium text-text-primary">{label}</div>
        <div className="text-2xs text-text-muted font-mono">
          {signal.created_at ? new Date(signal.created_at).toLocaleTimeString() : ''}
        </div>
      </div>
      <div className="text-2xs text-text-muted font-mono mt-0.5">
        value={signal.value.toFixed(2)}  threshold={signal.threshold}
      </div>
    </div>
  );
}

// ─── shared bits ───────────────────────────────────────────────────

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
      type="button"
      onClick={onClick}
      className={[
        'px-3 py-1.5 text-xs font-medium rounded-t border-b-2 transition-colors',
        active
          ? 'border-primary text-text-primary'
          : 'border-transparent text-text-muted hover:text-text-primary',
      ].join(' ')}
    >
      {children}
    </button>
  );
}
