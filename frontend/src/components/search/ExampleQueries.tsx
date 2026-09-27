type ExampleQueriesProps = {
  queries: string[];
  onSelect: (query: string) => void;
  align?: "center" | "left";
};

export function ExampleQueries({ queries, onSelect, align = "center" }: ExampleQueriesProps) {
  return (
    <div className={`flex flex-wrap gap-2 ${align === "center" ? "justify-center" : "justify-start"}`}>
      {queries.map((query) => (
        <button
          key={query}
          type="button"
          onClick={() => onSelect(query)}
          className="rounded-full border border-line bg-surface/60 px-3.5 py-1.5 text-left text-[13px] text-ink-muted transition-colors hover:border-line-strong hover:bg-surface-raised hover:text-ink sm:text-sm"
        >
          {query}
        </button>
      ))}
    </div>
  );
}
