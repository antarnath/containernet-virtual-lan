// DuplicateIPBanner — the sticky red banner shown at the top of the
// project canvas when two or more interfaces in the project share an
// IP address.
//
// Why it's sticky rather than a toast: a duplicate IP is a property
// of the *topology*, not of one action. It stays wrong until the
// user fixes the address on whichever interface is wrong, so the
// banner re-polls and stays visible until the conflict is gone. The
// user can also dismiss it manually — the next poll that still finds
// a conflict brings it back, which is the behaviour we want for a
// destructive misconfiguration.
//
// Design system: same shape as AnomalyBanner (danger-soft background,
// 2px left border, danger title) so the two read as one family.

import { useCallback, useEffect, useState } from 'react';

import { ProjectsAPI } from '../api/client';
import { Button, StatusPill } from './ui';
import type { DuplicateIPConflict } from '../types';

const POLL_MS = 8000;

export interface DuplicateIPBannerProps {
  projectId: string;
  /** Re-run the check immediately — pass the project version or a
   *  counter that changes whenever an interface is edited. */
  refreshKey?: string | number;
}

export function DuplicateIPBanner({
  projectId,
  refreshKey,
}: DuplicateIPBannerProps) {
  const [conflicts, setConflicts] = useState<DuplicateIPConflict[]>([]);
  const [dismissed, setDismissed] = useState(false);

  const check = useCallback(async () => {
    try {
      const res = await ProjectsAPI.duplicateIPs(projectId);
      setConflicts(res.conflicts);
      // A conflict that clears un-dismisses the banner, so the user
      // sees it again if the same mistake is made later.
      if (res.conflicts.length === 0) setDismissed(false);
    } catch {
      // A failed check is not itself an anomaly — stay quiet rather
      // than flashing a banner on a transient network blip.
    }
  }, [projectId]);

  useEffect(() => {
    void check();
  }, [check, refreshKey]);

  useEffect(() => {
    const t = setInterval(() => void check(), POLL_MS);
    return () => clearInterval(t);
  }, [check]);

  if (conflicts.length === 0 || dismissed) return null;

  return (
    <div
      role="alert"
      className="rounded-md bg-danger-soft border-l-2 border-l-danger px-3 py-2 flex items-start gap-3"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-danger">
            Duplicate IP address
          </span>
          <StatusPill tone="danger">conflict</StatusPill>
        </div>
        <div className="text-xs text-text-primary mt-0.5">
          {conflicts.length === 1
            ? 'Two interfaces share the same address. Change one of them before starting the project.'
            : `${conflicts.length} addresses are used by more than one interface. Change them before starting the project.`}
        </div>
        <ul className="mt-1.5 space-y-0.5">
          {conflicts.map((c) => (
            <li
              key={c.ip}
              className="text-2xs font-mono text-text-secondary truncate"
            >
              {c.ip} — {describeConflict(c)}
            </li>
          ))}
        </ul>
      </div>
      <Button variant="ghost" size="sm" onClick={() => setDismissed(true)}>
        Dismiss
      </Button>
    </div>
  );
}

/** Render one conflict as "Host-1 eth0 ↔ Router-1 eth1".
 *  `interface_ids` and `node_names` are parallel arrays — index i
 *  of each describes the same interface. */
function describeConflict(c: DuplicateIPConflict): string {
  const names = c.node_names.length ? c.node_names : c.interface_ids;
  if (names.length <= 1) return names.join(', ') || 'unknown interface';
  return names.join(' ↔ ');
}