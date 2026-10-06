// ConversationCard — one card per detected TCP/IP conversation.
// Renders the conversation header, all step cards, and a summary footer.

import type { PacketEvent } from '../../types';
import type { Conversation } from '../../utils/tcpClassifier';
import { StepCard } from './StepCard';

interface Props {
  conversation: Conversation;
  onSelectPacket: (e: PacketEvent) => void;
}

export function ConversationCard({ conversation, onSelectPacket }: Props) {
  const c = conversation;
  const allChecksumsOk =
    c.stats.ipChecksumOk === c.stats.ipChecksumTotal &&
    c.stats.tcpChecksumOk === c.stats.tcpChecksumTotal &&
    c.stats.ipChecksumTotal + c.stats.tcpChecksumTotal > 0;

  return (
    <article className="border border-zinc-800 rounded-xl overflow-hidden bg-zinc-950">
      {/* header */}
      <header className="bg-gradient-to-r from-zinc-900 to-zinc-950 border-b border-zinc-800 px-5 py-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <div className="text-zinc-100 text-sm font-semibold">
              {c.clientIp}:{c.clientPort} → {c.serverIp}:{c.serverPort}
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">
              started {fmtTs(c.startedAt)} · took {c.duration_ms.toFixed(2)} ms ·{' '}
              {c.steps.length} step{c.steps.length !== 1 ? 's' : ''}
            </div>
          </div>
        </div>
      </header>

      {/* steps */}
      <div className="p-4 space-y-3">
        {c.steps.map((step) => (
          <StepCard
            key={`${c.id}-${step.index}`}
            step={step}
            onSelectPacket={onSelectPacket}
          />
        ))}
      </div>

      {/* footer */}
      <footer className="bg-zinc-900 border-t border-zinc-800 px-5 py-2.5 text-xs flex flex-wrap gap-4">
        <Stat label="packets" value={String(c.stats.totalPackets)} />
        <Stat
          label="app bytes in"
          value={`${c.stats.appBytesReceived} B`}
          color="text-emerald-300"
        />
        <Stat
          label="app bytes out"
          value={`${c.stats.appBytesSent} B`}
          color="text-emerald-300"
        />
        <Stat label="duration" value={`${c.duration_ms.toFixed(2)} ms`} />
        <Stat
          label="checksums"
          value={`${c.stats.ipChecksumOk + c.stats.tcpChecksumOk}/${
            c.stats.ipChecksumTotal + c.stats.tcpChecksumTotal
          } ${allChecksumsOk ? '✓' : '✗'}`}
          color={allChecksumsOk ? 'text-emerald-400' : 'text-rose-400'}
        />
      </footer>
    </article>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <span className="text-zinc-500">
      <span className="text-zinc-600">{label}: </span>
      <span className={color ?? 'text-zinc-200'}>{value}</span>
    </span>
  );
}

function fmtTs(iso: string): string {
  if (!iso) return '?';
  return new Date(iso).toLocaleTimeString();
}
