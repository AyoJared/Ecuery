"use client";

import { useAssistant } from "./AssistantProvider";

// Header entry point to Research Assistant mode, on every page (phones get it in the menu instead).
export function AssistantButton() {
  const { openAssistant } = useAssistant();
  return (
    <button
      onClick={openAssistant}
      aria-label="Talk to the Research Assistant"
      className="hidden items-center gap-2 sm:inline-flex rounded-full border border-line-strong px-3 py-1.5 text-sm text-ink transition-colors hover:bg-surface-raised"
    >
      <svg className="size-4 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <rect x="9" y="3" width="6" height="11" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
      </svg>
      Research Assistant
    </button>
  );
}
