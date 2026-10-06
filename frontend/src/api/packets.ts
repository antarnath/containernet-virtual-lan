// Typed client for the per-project packet-log API (M2-07 §4).
//
// Two surfaces:
//   * getPackets()  — REST replay. Returns the full log slice.
//   * openPacketStream() — SSE. Returns an `EventSource` so the caller
//                           can attach `message`/`reset` listeners.

import type { PacketEvent, PacketListResponse } from '../types';

const BASE = '/api/projects';

export const PacketsAPI = {
  /** REST replay: every PacketEvent with id > since, oldest first. */
  get: async (
    projectId: string,
    since = 0,
    limit = 1000,
  ): Promise<PacketListResponse> => {
    const url = `${BASE}/${projectId}/packets?since=${since}&limit=${limit}`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error(`packets: ${res.status} ${res.statusText}`);
    }
    return res.json();
  },

  /**
   * Open a SSE stream of new PacketEvents.
   *
   * Listens for:
   *   `data: {...}`     — packet event JSON in `message.data`
   *   `event: reset`    — capture container restarted; consumer should
   *                       close, refetch via REST, reopen.
   *
   * Returns the EventSource so the caller can call `.close()` on unmount.
   */
  openStream: (projectId: string, since = 0): EventSource => {
    const url = `${BASE}/${projectId}/packets/stream?since=${since}`;
    return new EventSource(url);
  },
};
