// Communications page — Trigger panel on the left, log table on the right.

import { useEffect } from 'react';
import { useCommStore } from '../store/commStore';
import TriggerPanel from '../components/trigger/TriggerPanel';
import type { CommStatus } from '../types';

const POLL_MS = 3000;

const statusBadge = (s: CommStatus) => {
  const cls =
    s === 'delivered'
      ? 'bg-online/20 text-online'
      : s === 'failed'
      ? 'bg-offline/20 text-offline'
      : 'bg-unknown/20 text-unknown';
  return `text-[10px] uppercase tracking-wider px-2 py-1 rounded ${cls}`;
};

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString();
}

export default function CommunicationsPage() {
  const communications = useCommStore((s) => s.communications);
  const fetchComms = useCommStore((s) => s.fetchComms);

  useEffect(() => {
    fetchComms();
    const id = setInterval(fetchComms, POLL_MS);
    return () => clearInterval(id);
  }, [fetchComms]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text">Communications</h1>
        <p className="text-sm text-muted mt-1">
          Send host-to-host messages over the virtual LAN and watch them appear
          in the log below.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <TriggerPanel />
        </div>

        <div className="lg:col-span-2 bg-panel border border-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-text">Communication Log</h2>
            <span className="text-xs text-muted">
              {communications.length} entries
            </span>
          </div>

          {communications.length === 0 ? (
            <div className="text-muted text-sm py-12 text-center">
              No communications yet. Send one from the Trigger Panel.
            </div>
          ) : (
            <div className="overflow-auto">
              <table className="w-full text-sm">
                <thead className="text-[10px] uppercase tracking-wider text-muted border-b border-border">
                  <tr>
                    <th className="text-left py-2 px-2">Time</th>
                    <th className="text-left py-2 px-2">From</th>
                    <th className="text-left py-2 px-2">To</th>
                    <th className="text-left py-2 px-2">Proto</th>
                    <th className="text-left py-2 px-2">Payload</th>
                    <th className="text-right py-2 px-2">Latency</th>
                    <th className="text-right py-2 px-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {communications.map((c) => (
                    <tr
                      key={c.id}
                      className="border-b border-border/50 hover:bg-panel2/40"
                    >
                      <td className="py-2 px-2 text-muted font-mono text-xs">
                        {fmtTime(c.timestamp)}
                      </td>
                      <td className="py-2 px-2 font-mono text-xs">
                        {c.source_host_id}
                      </td>
                      <td className="py-2 px-2 font-mono text-xs">
                        {c.dest_host_id}
                      </td>
                      <td className="py-2 px-2 text-muted text-xs">
                        {c.protocol}
                      </td>
                      <td className="py-2 px-2 font-mono text-xs truncate max-w-[200px]">
                        {c.payload}
                      </td>
                      <td className="py-2 px-2 text-right font-mono text-xs">
                        {c.latency_ms != null ? `${c.latency_ms.toFixed(1)} ms` : '—'}
                      </td>
                      <td className="py-2 px-2 text-right">
                        <span className={statusBadge(c.status)}>{c.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}