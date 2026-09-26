"use client";

import { exampleQueries } from "@/lib/example-queries";
import { ExampleQueries } from "./ExampleQueries";
import { SearchBar } from "./SearchBar";
import { useSearch } from "./SearchContext";

// Next pass: replace handleSubmit with a call to the backend and render the answer + chart.
export function SearchPanel({ align = "center" }: { align?: "center" | "left" }) {
  const { query, setQuery, inputRef } = useSearch();

  function handleSubmit(q: string) {
    console.info("[search] not wired up yet:", q);
  }

  function handleSelectExample(q: string) {
    setQuery(q);
    inputRef.current?.focus();
  }

  return (
    <div className={`flex w-full flex-col gap-6 ${align === "center" ? "items-center" : "items-start"}`}>
      <SearchBar value={query} onChange={setQuery} onSubmit={handleSubmit} inputRef={inputRef} />
      <ExampleQueries queries={exampleQueries} onSelect={handleSelectExample} align={align} />
    </div>
  );
}
