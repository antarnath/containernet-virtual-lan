// StatusPill — the single way to surface a state. Every "is this
// running?" indicator in the dashboard (project lifecycle, container
// status, node kind, attack mode) is a StatusPill with a specific
// `tone` and optional `icon`.
//
// Tone → color (semantic, never improvised):
//   idle       muted slate
//   draft      muted slate
//   starting   warn amber
//   running    success emerald
//   partial    warn amber
//   stopped    muted slate
//   error      danger rose
//   info       info indigo
//   accent     accent cyan
//   host / switch / router / server / attacker  → node-kind palette
//   tcp / udp / icmp / arp / http / attack       → protocol palette
//   subnet 1..6                                   → subnet palette

import { type ReactNode } from 'react';

export type StatusTone =
  | 'idle'
  | 'draft'
  | 'starting'
  | 'running'
  | 'partial'
  | 'stopped'
  | 'error'
  | 'info'
  | 'accent'
  | 'warn'
  | 'danger'
  | 'host'
  | 'switch'
  | 'router'
  | 'server'
  | 'attacker'
  | 'tcp'
  | 'udp'
  | 'icmp'
  | 'arp'
  | 'http'
  | 'attack'
  | `subnet-${1 | 2 | 3 | 4 | 5 | 6}`;

interface StatusPillProps {
  tone: StatusTone;
  children: ReactNode;
  /** Render a small dot before the label (default true). */
  dot?: boolean;
  /** Pulse the dot — for live states like "running". */
  pulse?: boolean;
  className?: string;
}

interface ToneStyle {
  text: string;
  bg: string;
  border: string;
  dot: string;
}

const TONE: Record<StatusTone, ToneStyle> = {
  // semantic
  idle:     { text: 'text-text-muted',       bg: 'bg-bg-surface-2', border: 'border-border',       dot: 'bg-text-muted' },
  draft:    { text: 'text-text-secondary',   bg: 'bg-bg-surface-2', border: 'border-border',       dot: 'bg-text-secondary' },
  starting: { text: 'text-warn',             bg: 'bg-warn-soft',    border: 'border-warn/40',      dot: 'bg-warn' },
  running:  { text: 'text-success',          bg: 'bg-success-soft', border: 'border-success/40',   dot: 'bg-success' },
  partial:  { text: 'text-warn',             bg: 'bg-warn-soft',    border: 'border-warn/40',      dot: 'bg-warn' },
  stopped:  { text: 'text-text-muted',       bg: 'bg-bg-surface-2', border: 'border-border',       dot: 'bg-text-muted' },
  error:    { text: 'text-danger',           bg: 'bg-danger-soft',  border: 'border-danger/40',    dot: 'bg-danger' },
  info:     { text: 'text-info',             bg: 'bg-info-soft',    border: 'border-info/40',      dot: 'bg-info' },
  accent:   { text: 'text-accent',           bg: 'bg-accent-soft',  border: 'border-accent/40',    dot: 'bg-accent' },
  warn:     { text: 'text-warn',             bg: 'bg-warn-soft',    border: 'border-warn/40',      dot: 'bg-warn' },
  danger:   { text: 'text-danger',           bg: 'bg-danger-soft',  border: 'border-danger/40',    dot: 'bg-danger' },

  // node-kind palette
  host:     { text: 'text-node-host',        bg: 'bg-node-host/10', border: 'border-node-host/40', dot: 'bg-node-host' },
  switch:   { text: 'text-node-switch',      bg: 'bg-node-switch/10', border: 'border-node-switch/40', dot: 'bg-node-switch' },
  router:   { text: 'text-node-router',      bg: 'bg-node-router/10', border: 'border-node-router/40', dot: 'bg-node-router' },
  server:   { text: 'text-node-server',      bg: 'bg-node-server/10', border: 'border-node-server/40', dot: 'bg-node-server' },
  attacker: { text: 'text-node-attacker',    bg: 'bg-node-attacker/10', border: 'border-node-attacker/40', dot: 'bg-node-attacker' },

  // protocol palette
  tcp:      { text: 'text-protocol-tcp',     bg: 'bg-protocol-tcp/10', border: 'border-protocol-tcp/40', dot: 'bg-protocol-tcp' },
  udp:      { text: 'text-protocol-udp',     bg: 'bg-protocol-udp/10', border: 'border-protocol-udp/40', dot: 'bg-protocol-udp' },
  icmp:     { text: 'text-protocol-icmp',    bg: 'bg-protocol-icmp/10', border: 'border-protocol-icmp/40', dot: 'bg-protocol-icmp' },
  arp:      { text: 'text-protocol-arp',     bg: 'bg-protocol-arp/10', border: 'border-protocol-arp/40', dot: 'bg-protocol-arp' },
  http:     { text: 'text-protocol-http',    bg: 'bg-protocol-http/10', border: 'border-protocol-http/40', dot: 'bg-protocol-http' },
  attack:   { text: 'text-protocol-attack',  bg: 'bg-protocol-attack/10', border: 'border-protocol-attack/40', dot: 'bg-protocol-attack' },

  // subnet palette (one per wire color)
  'subnet-1': { text: 'text-subnet-1',      bg: 'bg-subnet-1/10',  border: 'border-subnet-1/40',  dot: 'bg-subnet-1' },
  'subnet-2': { text: 'text-subnet-2',      bg: 'bg-subnet-2/10',  border: 'border-subnet-2/40',  dot: 'bg-subnet-2' },
  'subnet-3': { text: 'text-subnet-3',      bg: 'bg-subnet-3/10',  border: 'border-subnet-3/40',  dot: 'bg-subnet-3' },
  'subnet-4': { text: 'text-subnet-4',      bg: 'bg-subnet-4/10',  border: 'border-subnet-4/40',  dot: 'bg-subnet-4' },
  'subnet-5': { text: 'text-subnet-5',      bg: 'bg-subnet-5/10',  border: 'border-subnet-5/40',  dot: 'bg-subnet-5' },
  'subnet-6': { text: 'text-subnet-6',      bg: 'bg-subnet-6/10',  border: 'border-subnet-6/40',  dot: 'bg-subnet-6' },
};

export function StatusPill({
  tone,
  children,
  dot = true,
  pulse = false,
  className = '',
}: StatusPillProps) {
  const s = TONE[tone];
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 h-6 px-2 rounded-md',
        'text-2xs font-semibold uppercase tracking-wider',
        'border',
        s.bg,
        s.text,
        s.border,
        className,
      ].join(' ')}
    >
      {dot && (
        <span
          className={[
            'inline-block w-1.5 h-1.5 rounded-full flex-shrink-0',
            s.dot,
            pulse ? 'animate-pulse-dot' : '',
          ].join(' ')}
          aria-hidden
        />
      )}
      <span className="truncate">{children}</span>
    </span>
  );
}
