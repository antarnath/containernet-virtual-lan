// Toast — a non-blocking notification. The existing ToastContainer
// (in components/common) reads from `useToastStore`. This file
// re-exports a thin `<Toaster />` plus a programmatic `toast` helper
// so feature code can call `toast.success('Saved')` instead of
// poking the store directly.
//
// The M4 design system tone → style mapping lives here, replacing
// the legacy Tailwind tokens (border-online / border-offline / …)
// from the M3 era with the new semantic tokens (accent / danger / …).

import { create } from 'zustand';
import { useEffect } from 'react';

export type ToastKind = 'info' | 'success' | 'warning' | 'error';

export interface ToastItem {
  id: string;
  kind: ToastKind;
  title: string;
  message?: string;
  /** Auto-dismiss after this many ms. 0 = sticky. Default 4000. */
  duration?: number;
  /** Optional CTA rendered on the right of the toast body. */
  action?: { label: string; onClick: () => void };
}

interface ToastStore {
  toasts: ToastItem[];
  push: (t: Omit<ToastItem, 'id'>) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  push: (t) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    set((s) => ({ toasts: [...s.toasts, { ...t, id }] }));
    return id;
  },
  dismiss: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  clear: () => set({ toasts: [] }),
}));

export { useToastStore };

// ─── Programmatic API ────────────────────────────────────────────────────

const DEFAULTS: Record<ToastKind, Pick<ToastItem, 'duration'>> = {
  info: { duration: 3500 },
  success: { duration: 3000 },
  warning: { duration: 5000 },
  error: { duration: 6000 },
};

export const toast = {
  info: (
    title: string,
    message?: string,
    opts?: { action?: { label: string; onClick: () => void }; durationMs?: number },
  ) =>
    useToastStore.getState().push({
      kind: 'info',
      title,
      message,
      ...DEFAULTS.info,
      ...(opts?.action ? { action: opts.action } : {}),
      ...(opts?.durationMs ? { duration: opts.durationMs } : {}),
    }),
  success: (title: string, message?: string) =>
    useToastStore.getState().push({ kind: 'success', title, message, ...DEFAULTS.success }),
  warning: (title: string, message?: string) =>
    useToastStore.getState().push({ kind: 'warning', title, message, ...DEFAULTS.warning }),
  error: (title: string, message?: string) =>
    useToastStore.getState().push({ kind: 'error', title, message, ...DEFAULTS.error }),
  dismiss: (id: string) => useToastStore.getState().dismiss(id),
  clear: () => useToastStore.getState().clear(),
};

// ─── Renderer ────────────────────────────────────────────────────────────

const KIND_STYLES: Record<ToastKind, { ring: string; icon: string; iconColor: string }> = {
  info:    { ring: 'border-accent', icon: 'ℹ', iconColor: 'text-accent' },
  success: { ring: 'border-success', icon: '✓', iconColor: 'text-success' },
  warning: { ring: 'border-warn',    icon: '⚠', iconColor: 'text-warn' },
  error:   { ring: 'border-danger',  icon: '✕', iconColor: 'text-danger' },
};

function ToastRow({ item, onDismiss }: { item: ToastItem; onDismiss: (id: string) => void }) {
  const s = KIND_STYLES[item.kind];
  const duration = item.duration ?? DEFAULTS[item.kind].duration ?? 4000;

  useEffect(() => {
    if (duration <= 0) return;
    const id = setTimeout(() => onDismiss(item.id), duration);
    return () => clearTimeout(id);
  }, [item.id, duration, onDismiss]);

  return (
    <div
      role="status"
      className={[
        'pointer-events-auto bg-bg-surface border',
        s.ring,
        'rounded-lg shadow-md p-3 flex items-start gap-3',
        'animate-slide-in min-w-[260px] max-w-sm',
      ].join(' ')}
    >
      <div className={['text-base leading-none mt-0.5', s.iconColor].join(' ')} aria-hidden>
        {s.icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-text-primary">{item.title}</div>
        {item.message && (
          <div className="text-xs text-text-secondary mt-0.5 break-words">
            {item.message}
          </div>
        )}
        {item.action && (
          <button
            type="button"
            onClick={() => {
              item.action!.onClick();
              onDismiss(item.id);
            }}
            className="text-2xs font-mono uppercase tracking-wider text-accent hover:text-text-primary mt-1.5"
          >
            {item.action.label}
          </button>
        )}
      </div>
      <button
        onClick={() => onDismiss(item.id)}
        className="text-text-muted hover:text-text-primary text-sm leading-none"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  );
}

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <ToastRow key={t.id} item={t} onDismiss={dismiss} />
      ))}
    </div>
  );
}
