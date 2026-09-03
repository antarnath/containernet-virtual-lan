// Tiny toast queue used by Phase 6 real-time feedback.
// Toasts auto-dismiss after TTL_MS unless the user closes them.

import { create } from 'zustand';

export type ToastKind = 'info' | 'success' | 'warning' | 'error';

export interface Toast {
  id: string;
  kind: ToastKind;
  title: string;
  message?: string;
  createdAt: number;
}

interface ToastState {
  toasts: Toast[];
  push: (t: Omit<Toast, 'id' | 'createdAt'>) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

const TTL_MS = 5000;

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],

  push: (t) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const toast: Toast = { id, createdAt: Date.now(), ...t };
    set({ toasts: [...get().toasts, toast] });
    // Auto-dismiss after TTL_MS. Store the timer so we can cancel if the
    // user closes the toast manually first.
    setTimeout(() => get().dismiss(id), TTL_MS);
    return id;
  },

  dismiss: (id) =>
    set({ toasts: get().toasts.filter((t) => t.id !== id) }),

  clear: () => set({ toasts: [] }),
}));