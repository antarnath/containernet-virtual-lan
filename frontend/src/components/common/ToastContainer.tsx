// Phase 6 toast notifications. Fixed-position stack at the top-right of the
// viewport. Subscribes to the toast store; each toast auto-dismisses.

import { useToastStore } from '../../store/toastStore';

const kindStyles: Record<string, { ring: string; bg: string; icon: string }> = {
  info:    { ring: 'border-accent',   bg: 'bg-panel',     icon: 'ℹ️' },
  success: { ring: 'border-online',   bg: 'bg-panel',     icon: '✓' },
  warning: { ring: 'border-unknown',  bg: 'bg-panel',     icon: '⚠' },
  error:   { ring: 'border-offline',  bg: 'bg-panel',     icon: '✕' },
};

export default function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 w-80 pointer-events-none">
      {toasts.map((t) => {
        const style = kindStyles[t.kind] ?? kindStyles.info;
        return (
          <div
            key={t.id}
            className={`pointer-events-auto bg-panel border ${style.ring} rounded-lg shadow-lg p-3 flex items-start gap-3 animate-slide-in`}
            role="status"
          >
            <div className="text-lg leading-none mt-0.5">{style.icon}</div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-text">{t.title}</div>
              {t.message && (
                <div className="text-xs text-muted mt-0.5 break-words">
                  {t.message}
                </div>
              )}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="text-muted hover:text-text text-sm leading-none"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}