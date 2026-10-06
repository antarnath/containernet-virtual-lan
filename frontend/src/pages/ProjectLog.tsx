// ProjectLog — M2-07 §1 — packet-by-packet dashboard for one project.
// Two tabs:
//   1. Conversation view (default) — one card per detected TCP/IP
//      conversation, with per-step teaching tips and a click-to-expand
//      envelope modal showing the full L2/L3/L4/L7 breakdown.
//   2. Raw packet log — today's behavior: every packet including noise,
//      with filter chips and one row per packet.
//
// Both tabs share the same SSE-backed event stream from usePacketStream.

import { Link, useParams } from 'react-router-dom';
import { useState } from 'react';
import { usePacketStream } from '../hooks/usePacketStream';
import type { StreamState } from '../hooks/usePacketStream';
import { ConversationView } from '../components/log/ConversationView';
import { RawPacketView } from '../components/log/RawPacketView';

type Tab = 'conversation' | 'raw';

export default function ProjectLog() {
  const { projectId } = useParams<{ projectId: string }>();
  const { events, state, pause, resume, reset, save } = usePacketStream(
    projectId ?? '',
  );
  const [tab, setTab] = useState<Tab>('conversation');

  if (!projectId) {
    return (
      <div className="p-6 text-zinc-400">Missing project id in URL.</div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <LogHeader
        projectId={projectId}
        state={state}
        events={events}
        tab={tab}
        onTabChange={setTab}
        onPause={pause}
        onResume={resume}
        onReset={reset}
        onSave={save}
      />
      {tab === 'conversation' ? (
        <ConversationView events={events} projectId={projectId} />
      ) : (
        <RawPacketView events={events} />
      )}
    </div>
  );
}

// ─── header (controls + tab toggle) ───────────────────────────────────────

function LogHeader({
  projectId,
  state,
  events,
  tab,
  onTabChange,
  onPause,
  onResume,
  onReset,
  onSave,
}: {
  projectId: string;
  state: StreamState;
  events: unknown[];
  tab: Tab;
  onTabChange: (t: Tab) => void;
  onPause: () => void;
  onResume: () => void;
  onReset: () => void;
  onSave: () => void;
}) {
  const recording = state === 'streaming';
  return (
    <div className="sticky top-0 z-10 bg-zinc-900/95 backdrop-blur border-b border-zinc-800 px-4 py-3 text-sm">
      <div className="flex items-center gap-3 flex-wrap">
        <Link
          to={`/projects/${projectId}/communications`}
          className="text-zinc-400 hover:text-zinc-100"
        >
          /projects/{projectId.slice(0, 8)}…/log
        </Link>
        <span className="text-zinc-500">·</span>
        <span className="text-zinc-100 font-medium">packets</span>
        <span
          className={`ml-2 px-2 py-0.5 rounded text-xs uppercase tracking-wider ${
            recording
              ? 'bg-rose-500/15 text-rose-400 animate-pulse'
              : 'bg-zinc-700/40 text-zinc-400'
          }`}
        >
          {recording ? '● recording' : state}
        </span>

        <div className="ml-auto flex gap-2 items-center">
          {state === 'streaming' ? (
            <button
              onClick={onPause}
              className="px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700"
            >
              ⏸ pause
            </button>
          ) : (
            <button
              onClick={onResume}
              className="px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700"
            >
              ▶ resume
            </button>
          )}
          <button
            onClick={onReset}
            className="px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700"
          >
            ⏹ reset
          </button>
          <button
            onClick={onSave}
            className="px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700"
          >
            💾 save ({events.length})
          </button>
        </div>
      </div>

      {/* tab toggle */}
      <div className="mt-2 flex gap-1">
        <TabButton
          active={tab === 'conversation'}
          onClick={() => onTabChange('conversation')}
        >
          Conversation view
        </TabButton>
        <TabButton
          active={tab === 'raw'}
          onClick={() => onTabChange('raw')}
        >
          Raw packet log
        </TabButton>
      </div>
    </div>
  );
}

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
      onClick={onClick}
      className={`px-4 py-1.5 text-sm rounded-t border-b-2 transition-colors ${
        active
          ? 'border-emerald-400 text-emerald-300 bg-zinc-950'
          : 'border-transparent text-zinc-400 hover:text-zinc-200'
      }`}
    >
      {children}
    </button>
  );
}
