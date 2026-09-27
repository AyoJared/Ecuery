import type { SourceLink } from "@/lib/api/types";

/** The data sources behind an answer, as links people can open to check it themselves. */
export function SourceLinks({ links }: { links: SourceLink[] | undefined }) {
  if (!links?.length) return null;
  const usual = links.every((l) => l.usual);

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-ink-muted">
        {usual ? "Usual sources for this measurement" : links.length === 1 ? "Source" : "Sources"}
      </p>
      <ul className="flex flex-wrap gap-2">
        {links.map((l) => {
          // The backend only sends links that have at least one of the two URLs.
          const href = l.url ?? l.data_url ?? "";
          return (
            <li key={href} className="flex items-center overflow-hidden rounded-full border border-line-strong text-sm">
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                title={l.detail ?? undefined}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-ink transition-colors hover:bg-surface-raised"
              >
                {l.name}
                <ExternalIcon />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
              {l.url && l.data_url && (
                <a
                  href={l.data_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="The exact data request Ecuery made"
                  className="border-l border-line-strong px-3 py-1.5 text-ink-muted transition-colors hover:bg-surface-raised hover:text-ink"
                >
                  Raw data
                  <span className="sr-only"> from {l.name} (opens in a new tab)</span>
                </a>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ExternalIcon() {
  return (
    <svg className="size-3.5 text-ink-faint" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </svg>
  );
}
