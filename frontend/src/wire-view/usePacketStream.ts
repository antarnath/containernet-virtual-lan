// usePacketStream — opens an EventSource to the per-link SSE
// endpoint and buffers the most recent N events in memory.
//
// Behaviour:
//   * Auto-reconnects on disconnect (3s backoff).
//   * Buffers up to 500 events; older ones are evicted FIFO.
//   * `paused` is a UI hint only — events keep arriving, the
//     viewport just stops auto-scrolling.
//   * `clear()` empties the buffer.
//
// The wire view calls this hook once per page; the EventSource
// itself is tied to the hook's lifetime.

import { useEffect, useRef, useState, useCallback } from 'react';
import type { PacketEvent } from './types';

const BUFFER_SIZE = 500;
const RECONNECT_DELAY_MS = 3000;

export interface PacketStreamState {
  packets: PacketEvent[];
  paused: boolean;
  /** Connection state (mirrors the EventSource readyState). */
  status: 'connecting' | 'open' | 'closed' | 'error';
  pause: () => void;
  resume: () => void;
  clear: () => void;
}

export function usePacketStream(
  projectId: string | null,
  linkId: string | null,
): PacketStreamState {
  const [packets, setPackets] = useState<PacketEvent[]>([]);
  const [paused, setPaused] = useState(false);
  const [status, setStatus] = useState<PacketStreamState['status']>('closed');
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  // Keep a stable ref to clear() so callers don't trigger reconnect.
  const clearRef = useRef<() => void>(() => setPackets([]));

  useEffect(() => {
    if (!projectId || !linkId) {
      setStatus('closed');
      return;
    }
    let es: EventSource | null = null;
    let reconnectTimer: number | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      setStatus('connecting');
      const url = `/api/projects/${encodeURIComponent(projectId)}/links/${encodeURIComponent(linkId)}/packets/stream`;
      es = new EventSource(url);
      es.onopen = () => {
        if (cancelled) return;
        setStatus('open');
      };
      es.onmessage = (ev) => {
        if (cancelled) return;
        try {
          const pkt = JSON.parse(ev.data) as PacketEvent;
          setPackets((prev) => {
            const next = prev.length >= BUFFER_SIZE ? prev.slice(1) : prev.slice();
            next.push(pkt);
            return next;
          });
        } catch {
          // ignore malformed frames
        }
      };
      es.onerror = () => {
        if (cancelled) return;
        setStatus('error');
        try { es?.close(); } catch { /* noop */ }
        es = null;
        if (!cancelled) {
          reconnectTimer = window.setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };
    };
    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      try { es?.close(); } catch { /* noop */ }
      es = null;
    };
  }, [projectId, linkId]);

  const pause = useCallback(() => setPaused(true), []);
  const resume = useCallback(() => setPaused(false), []);
  const clear = useCallback(() => clearRef.current(), []);

  return { packets, paused, status, pause, resume, clear };
}
