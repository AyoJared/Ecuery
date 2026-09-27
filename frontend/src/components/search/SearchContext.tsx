"use client";

import { createContext, useContext, useRef, useState, type ReactNode, type RefObject } from "react";

type SearchContextValue = {
  query: string;
  setQuery: (query: string) => void;
  inputRef: RefObject<HTMLInputElement | null>;
  /** Put a question in the search bar, scroll to it and focus it. */
  ask: (question?: string) => void;
};

const SearchContext = createContext<SearchContextValue | null>(null);

// Shared so any section (globe, showcase, CTA) can hand a question to the hero search.
export function SearchProvider({ children }: { children: ReactNode }) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function ask(question?: string) {
    if (question !== undefined) setQuery(question);
    const input = inputRef.current;
    if (!input) return;
    input.scrollIntoView({ behavior: "smooth", block: "center" });
    input.focus({ preventScroll: true });
  }

  return (
    <SearchContext.Provider value={{ query, setQuery, inputRef, ask }}>
      {children}
    </SearchContext.Provider>
  );
}

export function useSearch() {
  const ctx = useContext(SearchContext);
  if (!ctx) throw new Error("useSearch must be used inside <SearchProvider>");
  return ctx;
}
