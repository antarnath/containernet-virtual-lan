// ShortcutsModal — the "?" overlay. Lists every keyboard shortcut
// available in the app. Reached via the ? key on the canvas or via
// the help icon in the AppHeader.

import { useEffect } from 'react';

import { Button, Card, CardHeader } from './ui';

interface Shortcut {
  keys: string[];
  description: string;
}

const SHORTCUTS: Shortcut[] = [
  { keys: ['Cmd', 'S'], description: 'Save the canvas (no-op — auto-saves)' },
  { keys: ['Cmd', 'Z'], description: 'Undo (planned — M5+)' },
  { keys: ['Cmd', 'Shift', 'Z'], description: 'Redo (planned — M5+)' },
  { keys: ['Delete'], description: 'Delete the selected node or wire' },
  { keys: ['Backspace'], description: 'Delete the selected node or wire' },
  { keys: ['Escape'], description: 'Close the side panel or modal' },
  { keys: ['?'], description: 'Show this keyboard shortcuts modal' },
];

export interface ShortcutsModalProps {
  onClose: () => void;
}

export function ShortcutsModal({ onClose }: ShortcutsModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg-base/70 backdrop-blur-sm animate-slide-in-up"
      onClick={onClose}
    >
      <Card
        elevation="raised"
        className="w-[480px] max-w-[90vw]"
        onClick={(e) => e.stopPropagation()}
      >
        <CardHeader
          title="Keyboard shortcuts"
          subtitle="Quick reference for the canvas and project pages."
        />
        <div className="space-y-2">
          {SHORTCUTS.map((s, i) => (
            <div
              key={i}
              className="flex items-center justify-between gap-3 text-sm"
            >
              <div className="text-text-secondary">{s.description}</div>
              <div className="flex gap-1 flex-shrink-0">
                {s.keys.map((k) => (
                  <kbd
                    key={k}
                    className="text-2xs font-mono text-text-secondary bg-bg-app border border-border rounded px-1.5 py-0.5"
                  >
                    {k}
                  </kbd>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="primary" onClick={onClose}>
            Close
          </Button>
        </div>
      </Card>
    </div>
  );
}
