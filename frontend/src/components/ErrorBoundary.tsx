import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <main
          className="flex min-h-screen flex-col items-center justify-center gap-4 bg-surface-0"
          style={{ color: 'rgb(var(--fg-1))' }}
        >
          <p className="text-lg font-semibold">Something went wrong.</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            Reload
          </button>
        </main>
      );
    }
    return this.props.children;
  }
}
