// Top header bar — M4 phase 01.
//
// Shows the app context on the left ("ContainerNet · virtual lab")
// and the system health on the right. Phase 01 has no live WS feed,
// so the right side just shows a static "Editor" mode badge; later
// phases (05+) will replace this with a real WebSocket status
// indicator and a per-project live event counter.

export default function Topbar() {
  return (
    <header className="h-12 bg-bg-surface border-b border-border flex items-center justify-between px-6 flex-shrink-0">
      <div className="text-2xs uppercase tracking-wider text-text-muted">
        Virtual network lab
      </div>
      <div className="flex items-center gap-2 text-2xs uppercase tracking-wider text-text-muted">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-success animate-pulse-dot" />
        <span>Editor mode</span>
      </div>
    </header>
  );
}
