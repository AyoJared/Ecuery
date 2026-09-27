"use client";

import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";

type FollowUpInputProps = {
  onSubmit: (question: string) => void;
  disabled: boolean;
  suggestions: string[];
};

// Chat box under the answer. Enter sends, Shift+Enter adds a new line. Sticks to the bottom of the
// screen while you scroll through the thread, so it's always within reach.
export function FollowUpInput({ onSubmit, disabled, suggestions }: FollowUpInputProps) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  function send(q: string) {
    const question = q.trim();
    if (!question || disabled) return;
    onSubmit(question);
    setValue("");
    ref.current?.focus();
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    send(value);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(value);
    }
  }

  return (
    <div className="sticky bottom-4 z-10 flex flex-col gap-3">
      {suggestions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              disabled={disabled}
              onClick={() => send(s)}
              className="rounded-full border border-line bg-surface/80 px-3.5 py-1.5 text-sm text-ink-muted backdrop-blur transition-colors hover:border-line-strong hover:text-ink disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-2 rounded-2xl border border-line-strong bg-surface/95 p-2 pl-4 shadow-2xl shadow-black/50 backdrop-blur transition-colors focus-within:border-accent/40"
      >
        <label htmlFor="follow-up" className="sr-only">
          Ask a follow-up question
        </label>
        <textarea
          id="follow-up"
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? "Working on your answer…" : "Ask a follow-up about this…"}
          className="max-h-40 min-h-10 flex-1 resize-none bg-transparent py-2 text-base text-ink [field-sizing:content] placeholder:text-ink-faint focus:outline-none"
        />
        <button
          type="submit"
          aria-label="Send"
          disabled={disabled || !value.trim()}
          className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-canvas transition-colors hover:bg-accent-soft disabled:bg-surface-raised disabled:text-ink-faint"
        >
          <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M12 19V5" />
            <path d="m6 11 6-6 6 6" />
          </svg>
        </button>
      </form>
    </div>
  );
}
