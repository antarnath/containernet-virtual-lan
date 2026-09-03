// Trigger Panel — pick source/destination hosts + protocol + payload, click Send.

import { useEffect, useState } from 'react';
import { useHostStore } from '../../store/hostStore';
import { useCommStore } from '../../store/commStore';
import ProtocolSelector from './ProtocolSelector';

export default function TriggerPanel() {
  const hosts = useHostStore((s) => s.hosts);
  const trigger = useCommStore((s) => s.trigger);
  const loading = useCommStore((s) => s.loading);

  const [source, setSource] = useState<string>('');
  const [destination, setDestination] = useState<string>('');
  const [protocol, setProtocol] = useState<string>('HTTP');
  const [payload, setPayload] = useState<string>('Hello PC2');
  const [lastResult, setLastResult] = useState<string>('');

  // Auto-select first two hosts when the host list first loads.
  useEffect(() => {
    if (!hosts || hosts.hosts.length < 2) return;
    if (!source) setSource(hosts.hosts[0].host_id);
    if (!destination) setDestination(hosts.hosts[1].host_id);
  }, [hosts, source, destination]);

  const canSend =
    !loading &&
    !!source &&
    !!destination &&
    source !== destination &&
    payload.trim().length > 0;

  const onSend = async () => {
    if (!canSend) return;
    setLastResult('');
    const comm = await trigger({
      source_host_id: source,
      destination_host_id: destination,
      protocol,
      payload,
    });
    if (comm) {
      setLastResult(
        `✓ ${comm.source_host_id} → ${comm.dest_host_id} ` +
          `${comm.status} in ${comm.latency_ms?.toFixed(1) ?? '?'} ms`
      );
    } else {
      setLastResult('✗ trigger failed (see browser console)');
    }
  };

  if (!hosts || hosts.hosts.length === 0) {
    return (
      <div className="text-muted text-sm">
        Waiting for hosts to register…
      </div>
    );
  }

  return (
    <div className="bg-panel border border-border rounded-xl p-5 space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-text">Trigger Panel</h2>
        <p className="text-xs text-muted mt-1">
          Send a message from one host to another over the virtual LAN.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="From">
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="w-full bg-panel2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
          >
            {hosts.hosts.map((h) => (
              <option key={h.host_id} value={h.host_id}>
                {h.hostname} ({h.host_id})
              </option>
            ))}
          </select>
        </Field>

        <Field label="To">
          <select
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            className="w-full bg-panel2 border border-border rounded-md px-3 py-2 text-sm text-text focus:outline-none focus:border-accent"
          >
            {hosts.hosts.map((h) => (
              <option key={h.host_id} value={h.host_id}>
                {h.hostname} ({h.host_id})
              </option>
            ))}
          </select>
        </Field>
      </div>

      <Field label="Protocol">
        <ProtocolSelector value={protocol} onChange={setProtocol} />
      </Field>

      <Field label="Payload">
        <input
          type="text"
          value={payload}
          onChange={(e) => setPayload(e.target.value)}
          className="w-full bg-panel2 border border-border rounded-md px-3 py-2 text-sm text-text font-mono focus:outline-none focus:border-accent"
        />
      </Field>

      <button
        onClick={onSend}
        disabled={!canSend}
        className={`w-full py-2 rounded-md text-sm font-semibold transition-colors ${
          canSend
            ? 'bg-accent text-white hover:bg-blue-600'
            : 'bg-panel2 text-muted cursor-not-allowed'
        }`}
      >
        {loading ? 'Sending…' : 'Send'}
      </button>

      {source === destination && (
        <div className="text-xs text-unknown">
          Source and destination must be different.
        </div>
      )}

      {lastResult && (
        <div
          className={`text-xs px-3 py-2 rounded ${
            lastResult.startsWith('✓')
              ? 'bg-online/20 text-online'
              : 'bg-offline/20 text-offline'
          }`}
        >
          {lastResult}
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wider text-muted">
        {label}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}