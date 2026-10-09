// AddInterfaceForm — the inline form for creating a new interface
// on a node. Lives in the side panel (HostPanel, RouterPanel) so the
// user can add a port without leaving the canvas.
//
// The user types a name (default eth0), an optional IP and mask. We
// do a lightweight IPv4 + mask format check on the client; the
// backend re-validates and returns 400 on bad input, which we
// surface inline.
//
// On success, the parent closes the form (the new interface shows
// up in the panel and on the canvas because the project store
// patches the node in place).

import { useState } from 'react';

import { Button } from './ui';

export interface AddInterfaceFormProps {
  /** "router" | "host" | "server" | "attacker" — affects the hint copy. */
  nodeKind: string;
  /** Called with the validated form body. Throw to surface an error. */
  onSubmit: (body: {
    name: string;
    ip_address: string | null;
    subnet_mask: string | null;
  }) => Promise<void>;
  /** Close the form. If `canClose` is false, the × button is hidden
   *  (used when the form is the only way to add a port — e.g. empty
   *  node). */
  canClose?: boolean;
}

const IPV4 = /^(\d{1,3}\.){3}\d{1,3}$/;
const MASK = /^\/\d{1,2}$/;

export function AddInterfaceForm({
  nodeKind,
  onSubmit,
  canClose = true,
}: AddInterfaceFormProps) {
  const [name, setName] = useState('eth0');
  const [ip, setIp] = useState('');
  const [mask, setMask] = useState('/24');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError('Name is required.');
      return;
    }
    const ipClean = ip.trim();
    const maskClean = mask.trim();
    if (ipClean && !IPV4.test(ipClean)) {
      setError('IP must be a dotted IPv4 (e.g. 10.0.0.1).');
      return;
    }
    if (maskClean && !MASK.test(maskClean)) {
      setError('Mask must be /N (e.g. /24).');
      return;
    }
    setBusy(true);
    try {
      await onSubmit({
        name: name.trim(),
        ip_address: ipClean || null,
        subnet_mask: maskClean || null,
      });
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : (err as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }

  const isRouter = nodeKind === 'router';

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-md border border-border bg-bg-surface-2 p-3 space-y-2"
      aria-label="Add interface"
    >
      <div className="text-2xs font-semibold uppercase tracking-wide text-text-muted">
        New interface
      </div>
      <div
        className={[
          'grid gap-2 items-end',
          canClose
            ? 'grid-cols-[80px_1fr_1fr_auto]'
            : 'grid-cols-[80px_1fr_1fr_auto]',
        ].join(' ')}
      >
        <Field label="Name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="eth0"
            className="w-full h-8 px-2 rounded-md bg-bg-base border border-border text-sm font-mono text-text-primary focus:outline-none focus:border-accent"
            disabled={busy}
            autoFocus
          />
        </Field>
        <Field label="IP address">
          <input
            value={ip}
            onChange={(e) => setIp(e.target.value)}
            placeholder="10.0.0.1"
            className="w-full h-8 px-2 rounded-md bg-bg-base border border-border text-sm font-mono text-text-primary focus:outline-none focus:border-accent"
            disabled={busy}
          />
        </Field>
        <Field label="Mask">
          <input
            value={mask}
            onChange={(e) => setMask(e.target.value)}
            placeholder="/24"
            className="w-full h-8 px-2 rounded-md bg-bg-base border border-border text-sm font-mono text-text-primary focus:outline-none focus:border-accent"
            disabled={busy}
          />
        </Field>
        <div className="flex gap-1">
          <Button
            type="submit"
            variant="primary"
            size="sm"
            loading={busy}
            disabled={busy}
          >
            Add
          </Button>
          {canClose && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                if (!busy) {
                  // Reset to a clean state on close; the parent's
                  // onCancel handler decides what to do next.
                  setName('eth0');
                  setIp('');
                  setMask('/24');
                  setError(null);
                }
              }}
              disabled={busy}
              aria-label="Close form"
            >
              ×
            </Button>
          )}
        </div>
      </div>
      {error && <div className="text-2xs text-danger">{error}</div>}
      <div className="text-2xs text-text-muted">
        {isRouter
          ? 'Routers typically need 2+ interfaces (one per network).'
          : 'Once added, drag from this node\u2019s handle on the canvas to another node\u2019s handle to draw a wire.'}
      </div>
    </form>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 min-w-0">
      <span className="text-2xs font-medium text-text-muted">{label}</span>
      {children}
    </label>
  );
}
