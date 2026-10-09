// usePacketStream — opens an EventSource to the per-link SSE
// endpoint and buffers the most recent N events in memory.
//
// Behaviour:
//   * Auto-reconnects on disconnect (3s backoff).
//   * Buffers up to 500 events; older ones are evicted FIFO.
//   * `paused` is a UI hint only — events keep arriving, the
//     viewport just stops auto-scrolling.
//   * `clear()` empties the buffer.
//   * On connect, pulls a one-shot snapshot from
//     /api/projects/{pid}/packets/recent?link_id=… so the wire
//     view isn't empty while waiting for the first SSE frame.
//     Without this backfill, a link that isn't producing traffic
//     right now looks dead even though its NDJSON file has 700 KB
//     of history.
//
// The wire view calls this hook once per page; the EventSource
// itself is tied to the hook's lifetime.

import { useEffect, useRef, useState, useCallback } from 'react';
import type { PacketEvent } from './types';

const BUFFER_SIZE = 500;
const RECONNECT_DELAY_MS = 3000;
const INITIAL_BACKFILL_LIMIT = 100;

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
  // Track IDs we've already buffered so the initial REST snapshot
  // doesn't double up with the first SSE frames.
  const seenIdsRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!projectId || !linkId) {
      setStatus('closed');
      return;
    }
    let es: EventSource | null = null;
    let reconnectTimer: number | null = null;
    let cancelled = false;
    // Reset the dedup set for each new project/link pair.
    seenIdsRef.current = new Set();
    setPackets([]);

    const ingest = (pkt: PacketEvent) => {
      if (pkt && pkt.id != null && seenIdsRef.current.has(pkt.id)) return;
      if (pkt?.id != null) seenIdsRef.current.add(pkt.id);
      setPackets((prev) => {
        const next = prev.length >= BUFFER_SIZE ? prev.slice(1) : prev.slice();
        next.push(pkt);
        return next;
      });
    };

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
          ingest(JSON.parse(ev.data) as PacketEvent);
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

    // Initial backfill — pull the last N packets from the REST
    // endpoint so the user sees history immediately. The endpoint
    // already returns packets with the full `raw` L2/L3/L4/L7
    // decode so the click-to-expand panel works for backfilled
    // frames too.
    const backfillUrl =
      `/api/projects/${encodeURIComponent(projectId)}/packets/recent` +
      `?limit=${INITIAL_BACKFILL_LIMIT}` +
      `&link_id=${encodeURIComponent(linkId)}`;
    fetch(backfillUrl)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data) return;
        const list = (data.packets || []) as PacketEvent[];
        // The recent endpoint may return a broader set; keep only
        // frames for this link (defensive — the API should already
        // scope by link_id).
        for (const pkt of list) {
          if (pkt.link_id && pkt.link_id !== linkId) continue;
          ingest(pkt);
        }
      })
      .catch(() => {
        // best-effort — SSE will fill in eventually
      });

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
