// Single message row inside a MessageWindow console.
//
// Outgoing messages (this host initiated) render right-aligned in blue.
// Incoming messages render left-aligned in green. Errors (status === failed)
// would be red — but the message stream itself doesn't carry a status field
// (the orchestrator's Communication row does). We keep the visual minimal.

import type { MessageRecord } from '../../types';

export default function MessageBubble({ msg }: { msg: MessageRecord }) {
  const isOut = msg.direction === 'out';
  const peer = msg.peer_host_id ?? '?';
  const arrow = isOut ? '→' : '←';
  const bubbleCls = isOut
    ? 'bg-blue-500/20 text-blue-200 border-blue-500/30'
    : 'bg-green-500/20 text-green-200 border-green-500/30';
  const meta = isOut ? 'text-blue-300/80' : 'text-green-300/80';
  const time = new Date(msg.timestamp).toLocaleTimeString();
  return (
    <div
      className={`flex ${isOut ? 'justify-end' : 'justify-start'} my-1 px-2`}
      title={`${msg.direction.toUpperCase()} · ${msg.protocol} · ${time}`}
    >
      <div
        className={`max-w-[85%] px-3 py-2 rounded-lg text-sm border ${bubbleCls}`}
      >
        <div className={`text-[10px] font-mono mb-1 ${meta}`}>
          {arrow} {peer} · {msg.protocol}
        </div>
        <div className="font-mono break-words whitespace-pre-wrap">
          {msg.payload}
        </div>
        <div className="text-[10px] text-muted mt-1 text-right">{time}</div>
      </div>
    </div>
  );
}