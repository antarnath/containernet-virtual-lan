// Tiny reusable colored dot: green / red / yellow based on host status.

import type { HostStatus } from '../../types';

const colorMap: Record<HostStatus, string> = {
  online: 'bg-online shadow-[0_0_8px_rgba(34,197,94,0.7)]',
  offline: 'bg-offline shadow-[0_0_8px_rgba(239,68,68,0.7)]',
  unknown: 'bg-unknown shadow-[0_0_8px_rgba(234,179,8,0.7)]',
};

interface Props {
  status: HostStatus;
  size?: 'sm' | 'md';
}

export default function StatusLED({ status, size = 'md' }: Props) {
  const dim = size === 'sm' ? 'h-2 w-2' : 'h-3 w-3';
  return (
    <span
      className={`inline-block rounded-full ${dim} ${colorMap[status]}`}
      title={status}
    />
  );
}
