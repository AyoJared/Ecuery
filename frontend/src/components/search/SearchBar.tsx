"use client";

import { type FormEvent, type RefObject } from "react";

type SearchBarProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (query: string) => void;
  inputRef?: RefObject<HTMLInputElement | null>;
};

export function SearchBar({ value, onChange, onSubmit, inputRef }: SearchBarProps) {
  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const query = value.trim();
    if (query) onSubmit(query);
  }

  return (
    <form onSubmit={handleSubmit} role="search" className="group relative w-full">
      {/* Glow that brightens on focus */}
      <div
        aria-hidden
        className="absolute -inset-px rounded-2xl bg-gradient-to-r from-accent/30 via-sun/20 to-accent/30 opacity-40 blur-md transition-opacity duration-300 group-focus-within:opacity-100"
      />
      <div className="relative flex items-center gap-3 rounded-2xl border border-line-strong bg-surface/90 pl-4 pr-2 shadow-2xl shadow-black/60 backdrop-blur transition-colors group-focus-within:border-accent/40 sm:pl-5">
        <SearchIcon />
        <label htmlFor="search" className="sr-only">
          Ask a question about environmental data
        </label>
        <input
          ref={inputRef}
          id="search"
          type="text"
          autoComplete="off"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Ask about sea levels, wildfires, air quality…"
          className="h-14 min-w-0 flex-1 bg-transparent text-base text-ink placeholder:text-ink-faint focus:outline-none sm:h-16 sm:text-lg"
        />
        <button
          type="submit"
          aria-label="Search"
          disabled={!value.trim()}
          className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-canvas transition-all hover:bg-accent-soft disabled:bg-surface-raised disabled:text-ink-faint sm:size-11"
        >
          <ArrowIcon />
        </button>
      </div>
    </form>
  );
}

function SearchIcon() {
  return (
    <svg className="size-5 shrink-0 text-ink-faint" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  );
}
