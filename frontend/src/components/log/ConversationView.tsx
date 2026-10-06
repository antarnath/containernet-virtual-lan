// ConversationView — default tab of the M2-07 dashboard.
// Shows one card per detected TCP/IP conversation, newest first.
// Empty state when there are no conversations yet.

import { Link } from 'react-router-dom';
import { useMemo, useState } from 'react';
import type { PacketEvent } from '../../types';
import { groupConversations } from '../../utils/tcpClassifier';
import { ConversationCard } from './ConversationCard';
import { EnvelopeModal } from './EnvelopeModal';

interface Props {
  events: PacketEvent[];
  projectId: string;
}

export function ConversationView({ events, projectId }: Props) {
  const conversations = useMemo(() => groupConversations(events), [events]);
  const [selectedPacket, setSelectedPacket] = useState<PacketEvent | null>(
    null,
  );

  if (conversations.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-12">
        <div className="max-w-xl text-center">
          <div className="text-6xl mb-4">📡</div>
          <h2 className="text-xl font-semibold text-zinc-100 mb-2">
            No conversations yet
          </h2>
          <p className="text-zinc-400 mb-6 leading-relaxed">
            The capture container is watching your project's bridge, but no
            host has talked to another yet. Trigger a communication from
            the topology page to see its full TCP/IP journey here — ARP,
            handshake, HTTP request, response, close — all in one view.
          </p>
          <Link
            to={`/projects/${projectId}/topology`}
            className="inline-block px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-md text-sm font-medium"
          >
            Go to topology page →
          </Link>
          <div className="mt-8 text-xs text-zinc-600 leading-relaxed">
            Background noise (mDNS, UPnP, gratuitous ARP) is intentionally
            hidden in this view — it would otherwise drown out the
            conversation. Switch to <em>Raw packet log</em> to see it.
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="flex-1 overflow-auto bg-zinc-950 p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {conversations.map((c) => (
            <ConversationCard
              key={c.id}
              conversation={c}
              onSelectPacket={setSelectedPacket}
            />
          ))}
        </div>
      </div>
      <EnvelopeModal
        event={selectedPacket}
        onClose={() => setSelectedPacket(null)}
      />
    </>
  );
}
