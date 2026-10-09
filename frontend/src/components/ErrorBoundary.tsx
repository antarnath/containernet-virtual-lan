// ErrorBoundary — top-level React error boundary. When an unhandled
// render error occurs, the user sees a Card with the error + a reload
// button. The stack trace is shown in a `bg-surface-2` block (this is
// the only place a stack trace is visible to the user).

import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button, Card } from './ui';

interface State {
  error: Error | null;
  info: ErrorInfo | null;
}

export interface ErrorBoundaryProps {
  children: ReactNode;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, State> {
  state: State = { error: null, info: null };

  static getDerivedStateFromError(error: Error): State {
    return { error, info: null };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, info);
    this.setState({ error, info });
  }

  handleReload = () => {
    window.location.reload();
  };

  async handleCopy() {
    try {
      const text = [
        this.state.error?.message ?? '',
        this.state.info?.componentStack ?? '',
      ].join('\n');
      await navigator.clipboard.writeText(text);
    } catch {
      // ignore
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="h-full w-full flex items-center justify-center p-6 bg-bg-app">
          <Card className="w-[640px] max-w-[95vw] border-danger/40">
            <div className="text-base font-semibold text-danger mb-2">
              Something went wrong
            </div>
            <div className="text-sm text-text-secondary mb-4">
              The page hit an unhandled error. Reload to try again, or
              copy the error below to file a bug.
            </div>
            <pre className="text-2xs font-mono text-text-secondary bg-bg-app rounded border border-border p-3 overflow-x-auto max-h-64 mb-4">
              {this.state.error.message}
              {'\n\n'}
              {this.state.info?.componentStack ?? ''}
            </pre>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => void this.handleCopy()}>
                Copy error
              </Button>
              <Button variant="primary" onClick={this.handleReload}>
                Reload
              </Button>
            </div>
          </Card>
        </div>
      );
    }
    return this.props.children;
  }
}
