// DhcpTab — the DHCP view inside the router side panel.
//
// Three sections, one per router interface:
//
//   1. DHCP server  — toggle + pool start/end, lease time, DNS.
//                    Writes PUT .../interfaces/<iid>/dhcp.
//   2. DHCP relay   — toggle + upstream server IP. Mutually
//                    exclusive with the server on the same iface.
//   3. Leases       — live table, polled from the router agent
//                    (GET .../nodes/<nid>/dhcp/leases).
//   4. Reservations — MAC → fixed-IP bindings, written back with
//                    PUT .../interfaces/<iid>/dhcp/reservations.
//
// Design-system contract: Card for each surface, Table for the two
// data grids, Button for every action, StatusPill for the on/off
// state. No raw colours.
//
// Persistence note: DHCP config is written to the DB immediately,
// but the dnsmasq config file is only regenerated when the project
// starts. The "restart to apply" hint below each section makes that
// explicit so users aren't confused when the toggle flips but the
// leases table stays empty.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ProjectsAPI } from '../api/client';
import {
  Button,
  Card,
  CardHeader,
  LoadingSkeleton,
  StatusPill,
  Table,
  toast,
  type TableColumn,
} from '../components/ui';
import { useProjectStore } from '../store/projectStore';
import type {
  DHCPLease,
  DHCPLeasesResponse,
  DHCPReservation,
  DHCPReservationInput,
  DHCPPoolSuggestion,
  ProjectInterface,
} from '../types';

const LEASE_POLL_MS = 5000;
const MAC_RE = /^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$/;
const IPV4_RE = /^(\d{1,3}\.){3}\d{1,3}$/;

// 12 hours — the backend's allowed range is 60..86400, and this is
// what the DHCP tab shows for an interface that has never been
// configured. Using the same value here as the fallback in the
// re-sync effect keeps the two in step.
const DEFAULT_LEASE_SECONDS = 43200;

export interface DhcpTabProps {
  projectId: string;
  nodeId: string;
}

export function DhcpTab({ projectId, nodeId }: DhcpTabProps) {
  // The design-time interface list. Each row here is one DHCP
  // server / relay the user can configure.
  const node = useProjectStore((s) =>
    s.current?.nodes.find((n) => n.id === nodeId),
  );
  const refreshProject = useProjectStore((s) => s.fetchProject);
  const ifaces = node?.interfaces ?? [];

  const [leases, setLeases] = useState<DHCPLeasesResponse | null>(null);
  const [leasesBusy, setLeasesBusy] = useState(true);

  // Poll the leases. Only while the panel is on this tab — the
  // parent unmounts the tab body when another tab is active, so
  // this effect naturally stops.
  const pollLeases = useCallback(async () => {
    try {
      const res = await ProjectsAPI.dhcp.leases(projectId, nodeId);
      setLeases(res);
    } catch {
      setLeases(null);
    } finally {
      setLeasesBusy(false);
    }
  }, [projectId, nodeId]);

  useEffect(() => {
    void pollLeases();
    const t = setInterval(() => void pollLeases(), LEASE_POLL_MS);
    return () => clearInterval(t);
  }, [pollLeases]);

  // Keep the leases table in sync right after any write that
  // changes the pool, so the user sees the new range immediately.
  const handleSaved = useCallback(async () => {
    await refreshProject(projectId);
    await pollLeases();
  }, [projectId, pollLeases, refreshProject]);

  return (
    <div className="space-y-3">
      {ifaces.length === 0 ? (
        <Card>
          <div className="text-xs text-text-secondary">
            This router has no interfaces yet.
          </div>
          <div className="text-2xs text-text-muted mt-1">
            Add one on the Interfaces tab first — a DHCP server needs an
            interface with an IP address to bind to.
          </div>
        </Card>
      ) : (
        <>
          {ifaces.map((iface) => (
            <InterfaceDhcpCard
              key={iface.id}
              projectId={projectId}
              nodeId={nodeId}
              iface={iface}
              onSaved={handleSaved}
            />
          ))}

          <LeasesCard
            busy={leasesBusy}
            data={leases}
            onRefresh={() => void pollLeases()}
          />
        </>
      )}
    </div>
  );
}

// ─── per-interface DHCP server + relay ─────────────────────────────────

function InterfaceDhcpCard({
  projectId,
  nodeId,
  iface,
  onSaved,
}: {
  projectId: string;
  nodeId: string;
  iface: ProjectInterface;
  onSaved: () => Promise<void>;
}) {
  const [mode, setMode] = useState<'off' | 'server' | 'relay'>(() =>
    iface.dhcp_enabled ? 'server' : iface.dhcp_relay_enabled ? 'relay' : 'off',
  );
  const [poolStart, setPoolStart] = useState(iface.dhcp_pool_start ?? '');
  const [poolEnd, setPoolEnd] = useState(iface.dhcp_pool_end ?? '');
  const [leaseTime, setLeaseTime] = useState(
    iface.dhcp_lease_time == null
      ? String(DEFAULT_LEASE_SECONDS)
      : String(iface.dhcp_lease_time),
  );
  const [dns, setDns] = useState(iface.dhcp_dns ?? '');
  const [relayServer, setRelayServer] = useState(iface.dhcp_relay_server ?? '');

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  // ─── auto-suggested pool ───────────────────────────────────────
  //
  // Every field of a working DHCP server is derivable from what the
  // user already configured: the interface's own address and the
  // link's subnet. Making them type four fields per interface was
  // busywork — and a frequent source of the red validation errors,
  // since the rules (pool inside the subnet, router's own IP
  // excluded) aren't obvious. So ask the backend for a pool it
  // already knows will pass, and pre-fill.
  //
  // Advisory throughout: the fields stay editable and `dirty` is NOT
  // set, so pre-filling never looks like an unsaved edit. A failed
  // suggestion is silently ignored — an interface with no IP or no
  // wired link has no sensible pool, and the user will find out from
  // Save's error message rather than from a blocking banner.
  const [suggestion, setSuggestion] = useState<DHCPPoolSuggestion | null>(null);
  const suggestedRef = useRef(false);

  const applySuggestion = useCallback(async () => {
    try {
      const s = await ProjectsAPI.dhcp.suggestPool(projectId, nodeId, iface.id);
      setSuggestion(s);
      // Only fill fields the user hasn't already set. Re-running after
      // they typed would otherwise stomp their edits.
      setPoolStart((cur) => (cur.trim() ? cur : s.pool_start));
      setPoolEnd((cur) => (cur.trim() ? cur : s.pool_end));
      setDns((cur) => (cur.trim() ? cur : s.dns));
      // Tell the re-sync effect the fields now hold a suggestion, so
      // it stops treating "empty" as the user's intent and wiping it.
      suggestedRef.current = true;
    } catch {
      setSuggestion(null);
    }
  }, [projectId, nodeId, iface.id]);

  // Fetch once so the hint can explain itself, and again whenever
  // the panel comes back after a re-sync reset the fields to ''.
  useEffect(() => {
    if (mode === 'server' || suggestedRef.current) {
      void applySuggestion();
    }
    // Only re-fetch when the identity changes — re-running on every
    // keystroke would fight the user for the field contents.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applySuggestion, mode]);

  // Re-sync when the server returns a newer version of the row
  // (e.g. after another tab saved a change).
  //
  // Keyed on the persisted VALUES, not on ``iface``. The parent
  // builds these objects from ``ifaces.map(...)``, so ``iface`` is
  // a fresh object literal on every parent render — and the leases
  // poll re-renders the panel every 5s. Depending on ``iface``
  // re-ran this effect on every tick and wiped whatever the user
  // had typed back to the last-saved (empty) value, so the pool
  // fields never survived long enough to be submitted. Depending
  // on the individual fields means the effect only fires when a
  // value genuinely changed on the server.
  const serverEnabled = !!iface.dhcp_enabled;
  const relayEnabled = !!iface.dhcp_relay_enabled;
  const poolStartSaved = iface.dhcp_pool_start ?? '';
  const poolEndSaved = iface.dhcp_pool_end ?? '';
  const leaseTimeSaved = iface.dhcp_lease_time;
  const dnsSaved = iface.dhcp_dns ?? '';
  const relayServerSaved = iface.dhcp_relay_server ?? '';

  useEffect(() => {
    setMode(serverEnabled ? 'server' : relayEnabled ? 'relay' : 'off');
    // Once a pool has been suggested, fall back to the suggestion
    // instead of blanking the fields. The server legitimately stores
    // NULL until the first Save, and wiping a valid pre-fill on every
    // re-sync would reintroduce the "I typed it and it vanished" bug
    // this effect was already rewritten to fix.
    setPoolStart(poolStartSaved || (suggestion?.pool_start ?? ''));
    setPoolEnd(poolEndSaved || (suggestion?.pool_end ?? ''));
    // A null lease_time renders as the string "null", which then
    // fails the 60-86400 range check on save. Fall back to the
    // 12-hour default the form intends.
    setLeaseTime(
      leaseTimeSaved == null ? String(DEFAULT_LEASE_SECONDS) : String(leaseTimeSaved),
    );
    setDns(dnsSaved || (suggestion?.dns ?? ''));
    setRelayServer(relayServerSaved);
    setDirty(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverEnabled, relayEnabled, poolStartSaved, poolEndSaved, leaseTimeSaved, dnsSaved, relayServerSaved]);

  function markDirty() {
    setDirty(true);
    setError(null);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      if (mode === 'server') {
        if (!IPV4_RE.test(poolStart.trim())) {
          setError('Pool start must be a dotted IPv4 (e.g. 10.30.10.100).');
          return;
        }
        if (!IPV4_RE.test(poolEnd.trim())) {
          setError('Pool end must be a dotted IPv4 (e.g. 10.30.10.200).');
          return;
        }
        const secs = Number(leaseTime);
        if (!Number.isFinite(secs) || secs < 60 || secs > 86400) {
          setError('Lease time must be between 60 and 86400 seconds.');
          return;
        }
        // Turning the server on must first turn the relay off —
        // the backend rejects both at once with a 422.
        if (iface.dhcp_relay_enabled) {
          await ProjectsAPI.dhcp.setRelay(projectId, nodeId, iface.id, {
            enabled: false,
            server_ip: null,
          });
        }
        await ProjectsAPI.dhcp.setServer(projectId, nodeId, iface.id, {
          enabled: true,
          pool_start: poolStart.trim(),
          pool_end: poolEnd.trim(),
          lease_time: secs,
          dns: dns.trim() || null,
        });
      } else if (mode === 'relay') {
        if (!IPV4_RE.test(relayServer.trim())) {
          setError('Relay server must be a dotted IPv4 (e.g. 10.30.10.1).');
          return;
        }
        if (iface.dhcp_enabled) {
          await ProjectsAPI.dhcp.setServer(projectId, nodeId, iface.id, {
            enabled: false,
            pool_start: null,
            pool_end: null,
          });
        }
        await ProjectsAPI.dhcp.setRelay(projectId, nodeId, iface.id, {
          enabled: true,
          server_ip: relayServer.trim(),
        });
      } else {
        // Turning everything off — clear both so the DB reflects
        // the intent rather than leaving a stale pool behind.
        if (iface.dhcp_enabled) {
          await ProjectsAPI.dhcp.setServer(projectId, nodeId, iface.id, {
            enabled: false,
            pool_start: null,
            pool_end: null,
          });
        }
        if (iface.dhcp_relay_enabled) {
          await ProjectsAPI.dhcp.setRelay(projectId, nodeId, iface.id, {
            enabled: false,
            server_ip: null,
          });
        }
      }
      setDirty(false);
      await onSaved();
      toast.success(
        `${iface.name} DHCP saved`,
        mode === 'off'
          ? 'DHCP is off on this interface.'
          : 'Restart the project to push the config to the router.',
      );
    } catch (e) {
      setError(extractError(e));
    } finally {
      setBusy(false);
    }
  }

  const isOff = mode === 'off';

  return (
    <Card>
      <CardHeader
        title={iface.name}
        subtitle={iface.ip_address ? `${iface.ip_address}${iface.subnet_mask ?? ''}` : 'no IP — cannot serve DHCP'}
        right={
          <StatusPill tone={isOff ? 'stopped' : 'running'}>
            {isOff ? 'off' : mode === 'server' ? 'server' : 'relay'}
          </StatusPill>
        }
      />

      <div className="space-y-3">
        {/* mode selector */}
        <div className="flex gap-1 p-1 rounded-md bg-bg-surface-2 border border-border">
          <ModeButton
            active={mode === 'off'}
            onClick={() => {
              setMode('off');
              markDirty();
            }}
          >
            Off
          </ModeButton>
          <ModeButton
            active={mode === 'server'}
            disabled={!iface.ip_address}
            onClick={() => {
              setMode('server');
              markDirty();
            }}
          >
            Server
          </ModeButton>
          <ModeButton
            active={mode === 'relay'}
            disabled={!iface.ip_address}
            onClick={() => {
              setMode('relay');
              markDirty();
            }}
          >
            Relay
          </ModeButton>
        </div>

        {mode === 'server' && (
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Pool start">
                <input
                  value={poolStart}
                  onChange={(e) => {
                    setPoolStart(e.target.value);
                    markDirty();
                  }}
                  placeholder="10.30.10.100"
                  className={inputCls}
                  disabled={busy}
                />
              </Field>
              <Field label="Pool end">
                <input
                  value={poolEnd}
                  onChange={(e) => {
                    setPoolEnd(e.target.value);
                    markDirty();
                  }}
                  placeholder="10.30.10.200"
                  className={inputCls}
                  disabled={busy}
                />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Lease time (s)">
                <input
                  value={leaseTime}
                  onChange={(e) => {
                    setLeaseTime(e.target.value);
                    markDirty();
                  }}
                  placeholder="43200"
                  className={inputCls}
                  disabled={busy}
                />
              </Field>
              <Field label="DNS (optional)">
                <input
                  value={dns}
                  onChange={(e) => {
                    setDns(e.target.value);
                    markDirty();
                  }}
                  placeholder="10.30.10.1"
                  className={inputCls}
                  disabled={busy}
                />
              </Field>
            </div>
            <ReservationsEditor projectId={projectId} nodeId={nodeId} iface={iface} />
            {suggestion && (
              <div className="text-2xs text-text-muted">
                Pool and DNS were filled in from {suggestion.subnet_cidr} —{' '}
                {suggestion.why}
              </div>
            )}
          </div>
        )}

        {mode === 'relay' && (
          <Field label="Upstream DHCP server IP">
            <input
              value={relayServer}
              onChange={(e) => {
                setRelayServer(e.target.value);
                markDirty();
              }}
              placeholder="10.30.10.1"
              className={inputCls}
              disabled={busy}
            />
          </Field>
        )}

        {isOff && (
          <div className="text-2xs text-text-muted">
            DHCP is off on {iface.name}. Hosts on this link use the static
            address you typed on their interface.
          </div>
        )}

        {!iface.ip_address && !isOff && (
          <div className="text-2xs text-warn">
            {iface.name} has no IP address. A DHCP server needs one to bind
            to — set it on the Interfaces tab first.
          </div>
        )}

        {error && <div className="text-2xs text-danger">{error}</div>}

        <div className="flex items-center justify-between gap-2">
          <div className="text-2xs text-text-muted">
            {!isOff && 'Applies on next project restart.'}
          </div>
          <Button
            variant="primary"
            size="sm"
            loading={busy}
            disabled={busy || !dirty}
            onClick={() => void save()}
          >
            Save
          </Button>
        </div>
      </div>
    </Card>
  );
}

// ─── reservations (per DHCP-server interface) ─────────────────────────

function ReservationsEditor({
  projectId,
  nodeId,
  iface,
}: {
  projectId: string;
  nodeId: string;
  iface: ProjectInterface;
}) {
  const [rows, setRows] = useState<DHCPReservation[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await ProjectsAPI.dhcp.listReservations(projectId, nodeId, iface.id);
      setRows(res.reservations);
    } catch (e) {
      setError(extractError(e));
    }
  }, [projectId, nodeId, iface.id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function persist(next: DHCPReservationInput[]) {
    setBusy(true);
    setError(null);
    try {
      const res = await ProjectsAPI.dhcp.setReservations(projectId, nodeId, iface.id, next);
      setRows(res.reservations);
      toast.success('Reservations saved', 'Restart the project to apply them.');
    } catch (e) {
      setError(extractError(e));
    } finally {
      setBusy(false);
    }
  }

  const asInputs = (list: DHCPReservation[]): DHCPReservationInput[] =>
    list.map((r) => ({
      mac_address: r.mac_address,
      ip_address: r.ip_address,
      hostname: r.hostname,
    }));

  if (rows === null) {
    return <LoadingSkeleton width="100%" height="56px" />;
  }

  return (
    <div className="space-y-2 pt-1">
      <div className="flex items-center justify-between">
        <div className="text-2xs font-semibold uppercase tracking-wide text-text-muted">
          Reservations
        </div>
        <div className="text-2xs text-text-muted">
          {rows.length} {rows.length === 1 ? 'row' : 'rows'}
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="text-2xs text-text-muted">
          None. A reservation pins a MAC to a fixed pool IP — useful for a
          "printer" or "server" that must keep its address across restarts.
        </div>
      ) : (
        <div className="space-y-1">
          {rows.map((r) => (
            <div
              key={r.id}
              className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-bg-surface-2 border border-border"
            >
              <span className="font-mono text-2xs text-text-primary flex-1 min-w-0 truncate">
                {r.mac_address}
              </span>
              <span className="font-mono text-2xs text-text-secondary">
                → {r.ip_address}
              </span>
              {r.hostname && (
                <span className="font-mono text-2xs text-text-muted truncate max-w-[80px]">
                  {r.hostname}
                </span>
              )}
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() =>
                  void persist(asInputs(rows.filter((x) => x.id !== r.id)))
                }
                aria-label={`Delete reservation ${r.mac_address}`}
              >
                ×
              </Button>
            </div>
          ))}
        </div>
      )}

      <AddReservationForm
        busy={busy}
        onAdd={(entry) => void persist([...asInputs(rows), entry])}
      />

      {error && <div className="text-2xs text-danger">{error}</div>}
    </div>
  );
}

function AddReservationForm({
  busy,
  onAdd,
}: {
  busy: boolean;
  onAdd: (entry: DHCPReservationInput) => void;
}) {
  const [mac, setMac] = useState('');
  const [ip, setIp] = useState('');
  const [hostname, setHostname] = useState('');
  const [err, setErr] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!MAC_RE.test(mac.trim())) {
      setErr('MAC must look like aa:bb:cc:dd:ee:ff.');
      return;
    }
    if (!IPV4_RE.test(ip.trim())) {
      setErr('IP must be a dotted IPv4 inside the pool.');
      return;
    }
    const host = hostname.trim();
    if (host && !/^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$/.test(host)) {
      setErr('Hostname must be alphanumeric (hyphens allowed).');
      return;
    }
    onAdd({
      mac_address: mac.trim().toLowerCase(),
      ip_address: ip.trim(),
      hostname: host || null,
    });
    setMac('');
    setIp('');
    setHostname('');
  }

  return (
    <form
      onSubmit={submit}
      className="grid grid-cols-[1fr_1fr_auto] gap-2 items-end pt-1"
    >
      <Field label="MAC">
        <input
          value={mac}
          onChange={(e) => setMac(e.target.value)}
          placeholder="aa:bb:cc:dd:ee:ff"
          className={inputCls}
          disabled={busy}
        />
      </Field>
      <Field label="IP">
        <input
          value={ip}
          onChange={(e) => setIp(e.target.value)}
          placeholder="10.30.10.150"
          className={inputCls}
          disabled={busy}
        />
      </Field>
      <Button type="submit" variant="secondary" size="sm" loading={busy} disabled={busy}>
        Add
      </Button>
      <div className="col-span-3 text-2xs text-text-muted">
        Hostname (optional):
      </div>
      <div className="col-span-3">
        <input
          value={hostname}
          onChange={(e) => setHostname(e.target.value)}
          placeholder="printer"
          className={inputCls}
          disabled={busy}
        />
      </div>
      {err && <div className="col-span-3 text-2xs text-danger">{err}</div>}
    </form>
  );
}

// ─── leases ────────────────────────────────────────────────────────────

function LeasesCard({
  busy,
  data,
  onRefresh,
}: {
  busy: boolean;
  data: DHCPLeasesResponse | null;
  onRefresh: () => void;
}) {
  // `Table` requires an index signature, so widen the agent's
  // DHCPLease shape into a local row type. `expires_text` is the
  // pre-formatted column; `mac` doubles as the React key since
  // a MAC is unique within a lease file.
  type LeaseRow = Record<string, unknown> & {
    id: string;
    ip: string;
    mac: string;
    hostname: string;
    expires_text: string;
  };

  const columns: TableColumn<LeaseRow>[] = [
    { key: 'ip', label: 'IP', mono: true, width: '28%' },
    { key: 'mac', label: 'MAC', mono: true, width: '38%' },
    { key: 'hostname', label: 'Hostname', mono: true, width: '20%' },
    { key: 'expires_text', label: 'Expires', width: '14%' },
  ];

  const rows = useMemo<LeaseRow[]>(() => {
    const list: DHCPLease[] = data?.leases ?? [];
    // Soonest expiry first — a lease about to lapse is the one a
    // user debugging a host would care about.
    return [...list]
      .sort((a, b) => a.expires_at - b.expires_at)
      .map((l) => ({
        id: l.mac,
        ip: l.ip,
        mac: l.mac,
        hostname: l.hostname || '*',
        expires_text: formatExpiry(l.expires_at),
      }));
  }, [data]);

  const summary = data
    ? data.server_ifaces.length > 0
      ? `serving on ${data.server_ifaces.join(', ')}`
      : data.relay_ifaces.length > 0
        ? `relaying on ${data.relay_ifaces.join(', ')}`
        : 'no DHCP configured'
    : '—';

  return (
    <Card>
      <CardHeader
        title="Leases"
        subtitle={summary}
        right={
          <Button variant="ghost" size="sm" onClick={onRefresh} aria-label="Refresh leases">
            ↻
          </Button>
        }
      />
      {busy && rows.length === 0 ? (
        <LoadingSkeleton width="100%" height="80px" />
      ) : (
        <>
          <Table
            columns={columns}
            rows={rows}
            rowKey="id"
            emptyMessage="no leases — no client has asked for an address yet"
          />
          {data?.error && (
            <div className="text-2xs text-text-muted mt-2">{data.error}</div>
          )}
        </>
      )}
    </Card>
  );
}

/** Human-friendly lease expiry. dnsmasq writes epoch seconds; 0 or a
 *  past value means the lease has already lapsed. */
function formatExpiry(epochSeconds: number): string {
  if (!epochSeconds) return 'expired';
  const delta = epochSeconds - Math.floor(Date.now() / 1000);
  if (delta <= 0) return 'expired';
  if (delta < 60) return `${delta}s`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h`;
  return `${Math.floor(delta / 86400)}d`;
}

// ─── small shared bits ─────────────────────────────────────────────────

const inputCls =
  'w-full h-8 px-2 rounded-md bg-bg-base border border-border text-sm font-mono text-text-primary focus:outline-none focus:border-accent disabled:opacity-50';

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 min-w-0">
      <span className="text-2xs font-medium text-text-muted">{label}</span>
      {children}
    </label>
  );
}

function ModeButton({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={[
        'flex-1 px-2 py-1.5 text-2xs font-medium rounded transition-colors duration-fast',
        disabled ? 'text-text-muted/50 cursor-not-allowed' : '',
        active
          ? 'bg-accent/20 text-text-primary border border-accent/40'
          : 'text-text-muted border border-transparent hover:text-text-secondary',
      ].join(' ')}
    >
      {children}
    </button>
  );
}

/** Pull a human-readable message out of an axios error. The backend
 *  returns `{detail: {...}}` for 422s and `{error, message}` for
 *  some others, so we probe both shapes. */
function extractError(e: unknown): string {
  const resp = (e as { response?: { data?: { detail?: unknown; message?: unknown; error?: unknown } } })
    ?.response;
  const detail = resp?.data?.detail ?? resp?.data?.message ?? resp?.data?.error;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'message' in (detail as Record<string, unknown>)) {
    return String((detail as Record<string, unknown>).message);
  }
  if (detail) return JSON.stringify(detail);
  return (e as Error).message ?? 'unknown error';
}