// LogsView — the per-project Logs page (route
// /projects/:projectId/logs). Two filter modes:
//
//   * Live timeline — subscribes to the realtime store's events,
//     which the WS pushes as ``type: "event"`` payloads. Newest
//     first; auto-scrolls to the top.
//
//   * "Load more" — paginates via cursor (oldest-first walking) so
//     a user can scroll back into history.
//
// Filter chips (EventFilter) narrow by kind. A pause button
// freezes the auto-scroll (matching the wire view's behaviour).

import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Button, Card } from '../components/ui';
import { ProjectsAPI, type ProjectEventRow } from '../api/client';
import { useRealtimeStore } from '../store/realtimeStore';
import { useProjectStore } from '../store/projectStore';
import { EventRow } from './EventRow';
import { EventFilter, type EventKindFilter } from './EventFilter';

const BACKFILL_PAGE = 100;
const SCROLL_TOP_THRESHOLD_PX = 80;

export function LogsView() {
  const { projectId } = useParams<{ projectId: string }>();
  const current = useProjectStore((s) => s.current);
  const fetchProject = useProjectStore((s) => s.fetchProject);

  // Live events from the WS-fed store. These arrive newest first
  // (the store prepends each new event).
  const liveEvents = useRealtimeStore((s) => s.events);
  // Connect (idempotent) so the WS is up while the user is on this
  // page. The store also pulls the initial 100 events on connect.
  const connect = useRealtimeStore((s) => s.connect);
  useEffect(() => {
    if (projectId) connect(projectId);
  }, [projectId, connect]);

  // Filter chips — empty = "All".
  const [activeFilters, setActiveFilters] = useState<Set<EventKindFilter>>(
    () => new Set(['all']),
  );
  // Older history (cursor-paginated).
  const [olderEvents, setOlderEvents] = useState<ProjectEventRow[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  // Pause auto-scroll: when true, new events don't bump the
  // scroll position. User can resume.
  const [paused, setPaused] = useState(false);
  const [wasPausedBeforeScroll, setWasPausedBeforeScroll] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  const lastTopIdRef = useRef<string | null>(null);

  // Hydrate project (for node-name lookup).
  useEffect(() => {
    if (!current || current.id !== projectId) {
      if (projectId) void fetchProject(projectId);
    }
  }, [current, projectId, fetchProject]);

  // Compute node-name lookup once.
  const nodeNamesById = useMemo(() => {
    const m: Record<string, string> = {};
    for (const n of current?.nodes ?? []) m[n.id] = n.name;
    return m;
  }, [current]);

  // Apply filter to live + older.
  const filtered = useMemo(() => {
    const isAll = activeFilters.has('all');
    const kinds = new Set<string>(
      Array.from(activeFilters).filter((k) => k !== 'all') as string[],
    );
    function keep(e: ProjectEventRow): boolean {
      if (isAll) return true;
      return kinds.has(e.kind);
    }
    // Live events are newest first. Older history is the same
    // (loaded newest first, prepended below).
    return [...liveEvents, ...olderEvents].filter(keep);
  }, [liveEvents, olderEvents, activeFilters]);

  // Per-kind counts (across the whole loaded set).
  const counts = useMemo(() => {
    const out: Partial<Record<EventKindFilter, number>> = { all: 0 };
    const all = [...liveEvents, ...olderEvents];
    out.all = all.length;
    for (const e of all) {
      out[e.kind] = (out[e.kind] ?? 0) + 1;
    }
    return out;
  }, [liveEvents, olderEvents]);

  function toggleFilter(k: EventKindFilter) {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (k === 'all') {
        return new Set(['all']);
      }
      next.delete('all');
      if (next.has(k)) {
        next.delete(k);
      } else {
        next.add(k);
      }
      if (next.size === 0) next.add('all');
      return next;
    });
  }

  async function loadOlder() {
    if (!projectId || loadingMore) return;
    setLoadingMore(true);
    try {
      const res = await ProjectsAPI.events.list(projectId, {
        limit: BACKFILL_PAGE,
        cursor: nextCursor ?? undefined,
      });
      setOlderEvents((prev) => [...prev, ...(res.events || [])]);
      setNextCursor(res.next_cursor);
    } catch {
      // ignore — toast would be noisy here
    } finally {
      setLoadingMore(false);
    }
  }

  // Auto-scroll: when not paused, keep the list scrolled to the top
  // (since newest events are at the top).
  useEffect(() => {
    if (paused) return;
    const list = listRef.current;
    if (!list) return;
    list.scrollTop = 0;
  }, [filtered, paused]);

  // Detect user scroll-up → auto-pause. Detect user scroll to top
  // (within threshold) → auto-resume.
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const onScroll = () => {
      if (list.scrollTop > SCROLL_TOP_THRESHOLD_PX) {
        if (!paused) {
          setWasPausedBeforeScroll(true);
          setPaused(true);
        }
      } else if (
        paused &&
        wasPausedBeforeScroll &&
        list.scrollTop <= SCROLL_TOP_THRESHOLD_PX
      ) {
        setPaused(false);
        setWasPausedBeforeScroll(false);
      }
    };
    list.addEventListener('scroll', onScroll, { passive: true });
    return () => list.removeEventListener('scroll', onScroll);
  }, [paused, wasPausedBeforeScroll]);

  if (!projectId) {
    return <div className="p-8 text-text-muted">Project not found.</div>;
  }

  return (
    <div className="flex flex-col h-full bg-bg-app">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border bg-bg-surface flex items-center gap-4 flex-shrink-0">
        <div className="flex-1 min-w-0">
          <div className="text-lg font-semibold text-text-primary">Logs</div>
          <div className="text-2xs text-text-muted font-mono">
            {current?.name ?? projectId} — {filtered.length} event
            {filtered.length === 1 ? '' : 's'} loaded
          </div>
        </div>
        <Button
          variant={paused ? 'primary' : 'ghost'}
          size="sm"
          onClick={() => {
            setPaused((p) => !p);
            setWasPausedBeforeScroll(false);
          }}
        >
          {paused ? '▶ Resume' : '⏸ Pause'}
        </Button>
        <Link to={`/projects/${projectId}`}>
          <Button variant="ghost" size="sm">← Back to canvas</Button>
        </Link>
      </div>

      {/* Filter chips */}
      <div className="px-6 py-3 border-b border-border bg-bg-app flex-shrink-0">
        <EventFilter
          active={activeFilters}
          onToggle={toggleFilter}
          counts={counts}
        />
      </div>

      {/* Timeline list */}
      <div
        ref={listRef}
        className="flex-1 min-h-0 overflow-y-auto"
      >
        <div className="max-w-4xl mx-auto p-4 space-y-2">
          {filtered.length === 0 ? (
            <Card>
              <div className="text-2xs text-text-muted text-center py-6">
                No events yet. Start the project to see lifecycle events.
              </div>
            </Card>
          ) : (
            filtered.map((e) => (
              <EventRow
                key={e.id}
                event={e}
                projectId={projectId}
                nodeName={
                  e.node_id ? nodeNamesById[e.node_id] ?? undefined : undefined
                }
              />
            ))
          )}

          {/* Load more (older) */}
          {nextCursor && (
            <div className="pt-2 pb-4 text-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={loadOlder}
                disabled={loadingMore}
              >
                {loadingMore ? 'Loading…' : 'Load older events'}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
