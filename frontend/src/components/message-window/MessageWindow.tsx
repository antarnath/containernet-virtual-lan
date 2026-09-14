// One console per host inside a project's Messages page.
//
// Behavior:
//   * On mount, calls messageStore.fetchHostHistory(projectId, hostId) so a
//     refresh repopulates the last 100 messages.
//   * Subscribes to the message store's per-host bucket.
//   * Auto-scrolls to the bottom on every new message — but pauses if the
//     user has scrolled up (so reading older history isn't a moving target).
//   * Header shows the hostname and a count badge.
//   * "Clear" button empties just this console (optimistic; no backend call).

import { useEffect, useLayoutEffect, useRef, useState } from 'react';

import MessageBubble from './MessageBubble';
import { useMessageStore, useHostMessages } from '../../store/messageStore';
import type { ProjectHost } from '../../types';

const STICK_TO_BOTTOM_PX = 24; // within 24px of the bottom => consider "at bottom"

export default function MessageWindow({
  projectId,
  host,
}: {
  projectId: string;
  host: ProjectHost;
}) {
  const messages = useHostMessages(projectId, host.host_id);
  const fetchHostHistory = useMessageStore((s) => s.fetchHostHistory);
  const clearHostMessages = useMessageStore((s) => s.clearHostMessages);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [stickToBottom, setStickToBottom] = useState(true);
  const [newSinceScroll, setNewSinceScroll] = useState(0);

  // Initial history load (and on project/host change).
  useEffect(() => {
    void fetchHostHistory(projectId, host.host_id);
    // Reset local state so a fresh console starts auto-scrolling.
    setStickToBottom(true);
    setNewSinceScroll(0);
  }, [projectId, host.host_id, fetchHostHistory]);

  // Track whether the user has scrolled away from the bottom.
  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distance <= STICK_TO_BOTTOM_PX) {
      setStickToBottom(true);
      setNewSinceScroll(0);
    } else {
      setStickToBottom(false);
    }
  };

  // Auto-scroll on new message when stickToBottom is on.
  // useLayoutEffect so we paint in the scrolled position, not the
  // intermediate scrolled-up position.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || !stickToBottom) {
      if (!stickToBottom) setNewSinceScroll((n) => n + 1);
      return;
    }
    el.scrollTop = el.scrollHeight;
  }, [messages.length, stickToBottom]);

  return (
    <div className="flex flex-col h-[420px] bg-panel/60 border border-border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border bg-panel flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm text-text truncate">
            {host.hostname}
          </span>
          <span className="text-[10px] font-mono text-muted">
            {host.host_id}
          </span>
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              host.status === 'online'
                ? 'bg-online'
                : host.status === 'offline'
                  ? 'bg-offline'
                  : 'bg-yellow-500'
            }`}
            title={host.status}
          />
        </div>
        <div className="flex items-center gap-2">
          <span
            className="text-[10px] text-muted"
            title="messages in view"
          >
            {messages.length} msg
          </span>
          {!stickToBottom && newSinceScroll > 0 && (
            <button
              onClick={() => {
                const node = scrollRef.current;
                if (node) node.scrollTop = node.scrollHeight;
                setStickToBottom(true);
                setNewSinceScroll(0);
              }}
              className="text-[10px] px-2 py-0.5 rounded bg-accent text-white hover:bg-accent/80"
            >
              ↓ {newSinceScroll} new
            </button>
          )}
          <button
            onClick={() => {
              if (
                confirm(
                  `Clear all in-memory messages for ${host.hostname}? (Backend history is kept.)`,
                )
              ) {
                clearHostMessages(projectId, host.host_id);
              }
            }}
            className="text-[10px] px-2 py-0.5 rounded bg-bg border border-border text-muted hover:text-text hover:border-accent"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Console */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="flex-1 overflow-y-auto py-2 bg-bg/50"
      >
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-muted">
            No messages yet.
            <br />
            Trigger one from the Trigger Panel.
          </div>
        ) : (
          messages.map((m) => <MessageBubble key={m.id} msg={m} />)
        )}
      </div>
    </div>
  );
}