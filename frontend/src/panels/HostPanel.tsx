// HostPanel — the side panel that opens when the user clicks a
// non-router node (host / server / attacker). Two tabs:
//
//   * Interfaces — the node's interfaces with IP / MAC
//   * Messages   — the message history filtered to this node
//
// Plus a header button "+ Send" that opens the TriggerPanel
// pre-filled with this node as the source.

import { useEffect, useState } from 'react';

import { AddInterfaceForm } from '../components/AddInterfaceForm';
import { Button, LoadingSkeleton, StatusPill, Table, toast } from '../components/ui';
import { TriggerAPI } from '../trigger/api';
import { TriggerPanel } from '../trigger/TriggerPanel';
import { useProjectStore } from '../store/projectStore';
import type { MessageRow } from '../trigger/types';
import type { ProjectNode } from '../types';

type Tab = 'interfaces' | 'messages';

export interface HostPanelProps {
  projectId: string;
  nodeId: string;
  nodeName: string;
  nodeKind: string;
  containerStatus: string;
  /** All project nodes — used by the TriggerPanel's "To" dropdown. */
  nodes: ProjectNode[];
  onClose: () => void;
}

const POLL_INTERVAL_MS = 5000;

export function HostPanel({
  projectId,
  nodeId,
  nodeName,
  nodeKind,
  containerStatus,
  nodes,
  onClose,
}: HostPanelProps) {
  const [tab, setTab] = useState<Tab>('interfaces');
  const [triggerOpen, setTriggerOpen] = useState(false);

  const node = nodes.find((n) => n.id === nodeId);

  return (
    <aside className="w-[480px] flex-shrink-0 h-full flex flex-col bg-bg-surface border-l border-border animate-slide-in">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-start gap-3 flex-shrink-0">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-text-primary truncate">
            {nodeName}
          </div>
          <div className="text-2xs text-text-muted font-mono mt-0.5">
            {nodeKind}
          </div>
        </div>
        <StatusPill
          tone={containerStatus === 'running' ? 'running' : 'stopped'}
        >
          {containerStatus}
        </StatusPill>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setTriggerOpen(true)}
          aria-label="Send message"
        >
          + Send
        </Button>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close panel">
          ×
        </Button>
      </div>

      {/* Tabs */}
      <div className="px-4 pt-3 flex gap-1 border-b border-border flex-shrink-0">
        <TabButton active={tab === 'interfaces'} onClick={() => setTab('interfaces')}>
          Interfaces
        </TabButton>
        <TabButton active={tab === 'messages'} onClick={() => setTab('messages')}>
          Messages
        </TabButton>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {tab === 'interfaces' && node && (
          <InterfacesTab
            node={node}
            containerStatus={containerStatus}
          />
        )}
        {tab === 'messages' && (
          <MessagesTab projectId={projectId} nodeId={nodeId} />
        )}
      </div>

      {triggerOpen && (
        <TriggerPanel
          projectId={projectId}
          nodes={nodes}
          initialSrcNodeId={nodeId}
          onClose={() => setTriggerOpen(false)}
          onSent={() => {
            // Switch to messages so the user sees the new bubble.
            setTab('messages');
          }}
        />
      )}
    </aside>
  );
}

// ─── tabs ─────────────────────────────────────────────────────────

function InterfacesTab({
  node,
  containerStatus,
}: {
  node: ProjectNode;
  containerStatus: string;
}) {
  const ifaces = node.interfaces || [];
  const addInterface = useProjectStore((s) => s.addInterface);
  const [formOpen, setFormOpen] = useState(ifaces.length === 0);

  return (
    <div className="p-3 space-y-3">
      {containerStatus !== 'running' && (
        <div className="text-2xs text-text-muted text-center py-2">
          Container is not running. Start the project to see live
          interface state.
        </div>
      )}

      {formOpen ? (
        <AddInterfaceForm
          nodeKind={node.kind}
          canClose={ifaces.length > 0}
          onSubmit={async (body) => {
            try {
              await addInterface(node.project_id, node.id, body);
              toast.success('Interface added', `${body.name} is ready to wire.`);
              if (ifaces.length > 0) setFormOpen(false);
            } catch (e) {
              const msg =
                (e as { response?: { data?: { detail?: unknown } } })?.response
                  ?.data?.detail ?? (e as Error).message;
              const text = typeof msg === 'string' ? msg : JSON.stringify(msg);
              toast.error('Could not add interface', text);
              throw e;
            }
          }}
        />
      ) : (
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setFormOpen(true)}
        >
          + Add interface
        </Button>
      )}

      {ifaces.length > 0 && (
        <Table
          columns={[
            { key: 'name', label: 'Name', mono: true },
            { key: 'ip_mask', label: 'IP / mask', mono: true },
            { key: 'mac', label: 'MAC', mono: true },
          ]}
          rows={ifaces.map((i) => ({
            id: i.id,
            name: i.name,
            ip_mask: i.ip_address
              ? `${i.ip_address}${i.subnet_mask || ''}`
              : '—',
            mac: i.mac_address || '—',
          }))}
        />
      )}
    </div>
  );
}

// ─── messages tab ─────────────────────────────────────────────────────

function MessagesTab({ projectId, nodeId }: { projectId: string; nodeId: string }) {
  const [rows, setRows] = useState<MessageRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function fetchOnce() {
      try {
        const res = await TriggerAPI.listMessages(projectId, nodeId, 200);
        if (!alive) return;
        setRows(res.messages || []);
        setError(null);
      } catch (e) {
        if (!alive) return;
        setError((e as Error).message);
      }
    }
    void fetchOnce();
    const t = setInterval(fetchOnce, POLL_INTERVAL_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [projectId, nodeId]);

  // We rely on the polling for now; WS would let us append
  // immediately, but a 5s poll keeps the list in sync with the
  // server-side history (which is the truth even if the WS
  // missed a beat).
  if (error) {
    return (
      <div className="m-3 rounded-md border border-danger/40 bg-danger-soft p-3 text-2xs text-danger">
        {error}
      </div>
    );
  }
  if (rows === null) {
    return (
      <div className="p-3 space-y-2">
        <LoadingSkeleton width="100%" height="32px" />
        <LoadingSkeleton width="80%" height="32px" />
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div className="p-6 text-2xs text-text-muted text-center">
        No messages yet. Click "+ Send" to fire one.
      </div>
    );
  }

  return (
    <div className="divide-y divide-border-muted">
      {rows.map((m) => (
        <MessageRowView key={m.id} row={m} hostId={nodeId} />
      ))}
    </div>
  );
}

function MessageRowView({ row, hostId }: { row: MessageRow; hostId: string }) {
  const direction: 'in' | 'out' =
    row.src_node_id === hostId ? 'out' : 'in';
  const tone =
    row.status === 'delivered'
      ? 'running'
      : row.status === 'unreachable'
        ? 'warn'
        : row.status === 'failed'
          ? 'danger'
          : 'idle';
  const ts = row.created_at ? new Date(row.created_at) : null;
  const timeLabel = ts ? formatTime(ts) : '—';
  const payload = (row.payload || '').slice(0, 80) +
    (row.payload && row.payload.length > 80 ? '…' : '');
  return (
    <div className="px-3 py-2 flex items-center gap-3 hover:bg-bg-surface-2">
      <span className="text-2xs font-mono text-text-muted whitespace-nowrap">
        {timeLabel}
      </span>
      <span
        className={[
          'inline-flex w-6 justify-center font-mono text-sm',
          direction === 'in' ? 'text-success' : 'text-accent',
        ].join(' ')}
        aria-label="direction"
      >
        {direction === 'in' ? '←' : '→'}
      </span>
      <div className="flex-1 min-w-0 flex items-center gap-2">
        <span className="text-2xs font-mono text-text-secondary whitespace-nowrap">
          {row.protocol}
        </span>
        <span className="text-2xs text-text-muted truncate">
          {direction === 'out' ? '→' : '←'} {row.dst_ip}
        </span>
        <span className="text-2xs font-mono text-text-primary truncate flex-1">
          {payload}
        </span>
      </div>
      <StatusPill tone={tone}>{row.status}</StatusPill>
    </div>
  );
}

// ─── sub-components ───────────────────────────────────────────────

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
        'h-9 px-3 text-sm font-medium border-b-2 -mb-px transition-colors duration-fast',
        active
          ? 'text-accent border-accent'
          : 'text-text-secondary border-transparent hover:text-text-primary',
      ].join(' ')}
    >
      {children}
    </button>
  );
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}
