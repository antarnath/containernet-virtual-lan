// usePacketStream — REST fill + SSE subscription for the dashboard
// packet log (M2-07 §5.2).
//
// State machine:
//   loading    → initial mount, REST fill in flight
//   streaming  → live log, SSE open
//   paused     → user clicked ⏸; SSE temporarily closed
//   closed     → SSE `reset` event fired (capture container restarted)

import { useCallback, useEffect, useRef, useState } from 'react';
import type { PacketEvent } from '../types';
import { PacketsAPI } from '../api/packets';

export type StreamState = 'loading' | 'streaming' | 'paused' | 'closed';

const MAX_EVENTS = 10_000; // M2-07 §5.2 — frontend cap.

export interface UsePacketStream {
  events: PacketEvent[];
  state: StreamState;
  pause: () => void;
  resume: () => void;
  reset: () => void;
  save: () => void;
  selected: PacketEvent | null;
  select: (e: PacketEvent | null) => void;
}

export function usePacketStream(projectId: string): UsePacketStream {
  const [events, setEvents] = useState<PacketEvent[]>([]);
  const [state, setState] = useState<StreamState>('loading');
  const [selected, setSelected] = useState<PacketEvent | null>(null);
  const cursorRef = useRef<number>(0);
  const sourceRef = useRef<EventSource | null>(null);

  // Cleanup helper — closes the SSE without changing state.
  const closeStream = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
  }, []);

  // Open a fresh SSE connection starting from the given cursor.
  const openStream = useCallback(
    (from: number) => {
      closeStream();
      const src = PacketsAPI.openStream(projectId, from);
      sourceRef.current = src;
      src.onmessage = (msg: MessageEvent<string>) => {
        try {
          const ev = JSON.parse(msg.data) as PacketEvent;
          cursorRef.current = Math.max(cursorRef.current, ev.id);
          setEvents((prev) => {
            const next = prev.length >= MAX_EVENTS
              ? prev.slice(prev.length - MAX_EVENTS + 1)
              : prev.slice();
            next.push(ev);
            return next;
          });
        } catch {
          // Ignore parse errors; show malformed frames in the log.
        }
      };
      src.addEventListener('reset', () => {
        // M2-07 §4.2 — capture container restarted.
        closeStream();
        setState('closed');
      });
      src.onerror = () => {
        // Browser will auto-reconnect; we don't need to do anything here
        // unless the server emitted `reset`.
      };
    },
    [projectId, closeStream],
  );

  // Initial fill + open stream on mount or project change.
  useEffect(() => {
    let cancelled = false;
    setEvents([]);
    setSelected(null);
    cursorRef.current = 0;
    setState('loading');

    (async () => {
      try {
        const { events: initial } = await PacketsAPI.get(projectId, 0, MAX_EVENTS);
        if (cancelled) return;
        setEvents(initial);
        if (initial.length) {
          cursorRef.current = Math.max(
            cursorRef.current,
            initial[initial.length - 1].id,
          );
        }
        openStream(cursorRef.current);
        setState('streaming');
      } catch (err) {
        if (cancelled) return;
        // eslint-disable-next-line no-console
        console.error('usePacketStream initial fill failed:', err);
        setState('closed');
      }
    })();

    return () => {
      cancelled = true;
      closeStream();
    };
  }, [projectId, openStream, closeStream]);

  const pause = useCallback(() => {
    closeStream();
    setState('paused');
  }, [closeStream]);

  const resume = useCallback(() => {
    openStream(cursorRef.current);
    setState('streaming');
  }, [openStream]);

  const reset = useCallback(() => {
    closeStream();
    cursorRef.current = 0;
    setEvents([]);
    setSelected(null);
    openStream(0);
    setState('streaming');
  }, [closeStream, openStream]);

  const save = useCallback(() => {
    // M2-07 §1.2 — "💾 save" download as NDJSON.
    const blob = new Blob(
      [events.map((e) => JSON.stringify(e)).join('\n') + '\n'],
      { type: 'application/x-ndjson' },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `project-${projectId}-packets.ndjson`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [events, projectId]);

  const select = useCallback((e: PacketEvent | null) => setSelected(e), []);

  return { events, state, pause, resume, reset, save, selected, select };
}
