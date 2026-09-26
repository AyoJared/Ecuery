import { dataSources } from "@/lib/example-queries";

export function SourcesStrip() {
  return (
    <div className="flex flex-col items-center gap-4">
      <p className="text-xs text-ink-faint">Built on public data from</p>
      <ul className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
        {dataSources.map((source) => (
          <li key={source} className="font-mono text-sm tracking-wider text-ink-faint/80">
            {source}
          </li>
        ))}
      </ul>
    </div>
  );
}
