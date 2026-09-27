"use client";

import { Component, type ReactNode } from "react";

// The globe's code (three.js) is downloaded only when the user scrolls near it. If that download
// fails (flaky network, or a dev server that stopped), show a small fallback instead of letting
// the error take out the whole section.
export class GlobeErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="grid size-full place-items-center rounded-full border border-dashed border-line-strong text-center">
        <div className="flex flex-col items-center gap-3 px-6">
          <p className="text-sm text-ink-muted">The globe couldn&apos;t load.</p>
          <button
            onClick={() => window.location.reload()}
            className="rounded-full border border-line-strong px-4 py-1.5 text-sm text-ink transition-colors hover:bg-surface-raised"
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
