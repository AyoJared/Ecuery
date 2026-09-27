"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { hasEventsPlan, isWebAnswer, type AnsweredResponse } from "@/lib/api/types";
import { eventTypeLabel } from "@/lib/event-types";
import { formatDate, formatRange, metricLabel, operationLabel, sourceName } from "@/lib/format";

// Technical detail (how the question was read, datasets, fingerprint, Solana tx) lives in a side
// panel so the answer itself stays uncluttered. Opened from the "Sources" button in the toolbar.
export function SourcesButton({ answer }: { answer: AnsweredResponse }) {
  const [open, setOpen] = useState(false);
  const names = [...new Set(answer.provenance.map((p) => sourceName(p.source)))];
  const label = names.length
    ? `${names.slice(0, 2).join(" · ")}${names.length > 2 ? ` +${names.length - 2}` : ""}`
    : "Sources";

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        className="inline-flex items-center gap-2 rounded-full border border-line-strong px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:bg-surface-raised"
      >
        <svg
          className="size-3.5 text-accent"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <ellipse cx="12" cy="5.5" rx="7" ry="2.5" />
          <path d="M5 5.5v6c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-6M5 11.5v6c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-6" />
        </svg>
        {label}
        <span className="text-ink-faint">· Details</span>
      </button>
      <SourcesDrawer answer={answer} open={open} onClose={() => setOpen(false)} />
    </>
  );
}

function SourcesDrawer({
  answer,
  open,
  onClose,
}: {
  answer: AnsweredResponse;
  open: boolean;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="backdrop"
            className="fixed inset-0 z-50 bg-canvas/60 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            key="panel"
            role="dialog"
            aria-modal="true"
            aria-label="Sources and verification"
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-line-strong bg-surface shadow-2xl shadow-black/60"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 38 }}
          >
            <div className="flex items-center justify-between border-b border-line px-5 py-4">
              <h2 className="text-sm font-semibold text-ink">Sources and verification</h2>
              <button
                ref={closeRef}
                onClick={onClose}
                aria-label="Close"
                className="grid size-8 place-items-center rounded-full text-ink-muted transition-colors hover:bg-surface-raised hover:text-ink"
              >
                <svg
                  className="size-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  strokeLinecap="round"
                  aria-hidden
                >
                  <path d="M6 6l12 12M18 6 6 18" />
                </svg>
              </button>
            </div>
            <div className="flex-1 space-y-7 overflow-y-auto px-5 py-6">
              <Understood answer={answer} />
              <DataSources answer={answer} />
              <Verification answer={answer} />
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-3 text-xs font-medium uppercase tracking-[0.14em] text-ink-faint">{title}</h3>
      {children}
    </section>
  );
}

/** How the backend understood the question: the plan it actually ran. */
function Understood({ answer }: { answer: AnsweredResponse }) {
  const chips: [string, string][] = isWebAnswer(answer)
    ? [
        ["Topic", answer.plan.topic],
        ["Source", "Cited web pages"],
      ]
    : hasEventsPlan(answer)
      ? [
        ...answer.plan.event_types.map((t): [string, string] => ["Event", eventTypeLabel(t)]),
        ["Place", answer.plan.place?.label ?? "Worldwide"],
        ...(answer.plan.within
          ? [["Within", answer.plan.within] as [string, string]]
          : answer.plan.radius_km
            ? [["Radius", `${Math.round(answer.plan.radius_km)} km`] as [string, string]]
            : []),
        ...(answer.plan.min_magnitude
          ? [["Min. magnitude", `M${answer.plan.min_magnitude}`] as [string, string]]
          : []),
        ["Period", formatRange(answer.plan.start, answer.plan.end)],
      ]
    : [
        ...answer.plan.metrics.map((m): [string, string] => ["Measure", metricLabel(m)]),
        ...answer.plan.locations.map((l): [string, string] => ["Place", answer.plan.places[l]?.label ?? l]),
        ["Period", formatRange(answer.plan.start, answer.plan.end)],
        ["Type", operationLabel(answer.plan.operation)],
      ];
  return (
    <Section title="How we read your question">
      <div className="flex flex-wrap gap-2">
        {chips.map(([k, v]) => (
          <span
            key={`${k}-${v}`}
            className="rounded-full border border-line-strong bg-surface-raised px-3 py-1.5 text-sm"
          >
            <span className="text-ink-faint">{k}: </span>
            <span className="text-ink">{v}</span>
          </span>
        ))}
      </div>
    </Section>
  );
}

function DataSources({ answer }: { answer: AnsweredResponse }) {
  return (
    <Section title="Where the data comes from">
      {answer.data_notes.length > 0 && (
        <ul className="mb-4 flex flex-col gap-2">
          {answer.data_notes.map((n) => (
            <li key={n} className="text-sm leading-relaxed text-ink-muted">
              {n}
            </li>
          ))}
        </ul>
      )}
      {answer.provenance.length > 0 && (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {answer.provenance.map((p) => (
            <li key={p.batch_id} className="flex flex-col gap-1 px-4 py-3 text-sm">
              <span>
                <span className="font-medium text-ink">{sourceName(p.source)}</span>
                <span className="text-ink-muted"> · {p.dataset}</span>
                {p.quality === "preliminary" && <span className="ml-2 text-xs text-sun">preliminary</span>}
              </span>
              <span className="flex flex-wrap items-center gap-x-3 text-xs text-ink-faint">
                {p.row_count} rows · fetched {formatDate(p.fetched_at)}
                {p.explorer_url && (
                  <a
                    href={p.explorer_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-accent hover:text-accent-soft"
                  >
                    Source anchor on Solana ↗
                  </a>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {answer.provenance_error && (
        <p className="mt-2 text-xs text-ink-faint">Source registry unavailable for this answer.</p>
      )}
    </Section>
  );
}

function Verification({ answer }: { answer: AnsweredResponse }) {
  const v = answer.verification;
  return (
    <Section title="Verification">
      <p className="mb-3 text-sm leading-relaxed text-ink-muted">
        This answer&apos;s question, result, sources and timestamp were fingerprinted (SHA-256)
        {v.mode === "rpc" ? " and recorded on the Solana blockchain" : ""}, so anyone can check it hasn&apos;t
        been changed since.
      </p>
      <dl className="grid gap-x-4 gap-y-2 font-mono text-xs sm:grid-cols-[auto_1fr]">
        <dt className="text-ink-faint">sha-256</dt>
        <dd className="flex min-w-0 items-center gap-2 text-ink-muted">
          <span className="truncate">{v.hash}</span>
          <CopyButton text={v.hash} />
        </dd>
        {v.signature && (
          <>
            <dt className="text-ink-faint">solana tx</dt>
            <dd className="truncate text-ink-muted">{v.signature}</dd>
          </>
        )}
        {v.error && (
          <>
            <dt className="text-ink-faint">note</dt>
            <dd className="text-sun">{v.error}</dd>
          </>
        )}
      </dl>
      {v.explorer_url && v.mode === "rpc" && (
        <a
          href={v.explorer_url}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex items-center gap-2 rounded-full border border-good/35 bg-good/10 px-3 py-1.5 text-xs font-medium text-good transition-colors hover:bg-good/20"
        >
          View on Solana Explorer ↗
        </a>
      )}
    </Section>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() =>
        navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        })
      }
      className="shrink-0 rounded border border-line px-1.5 py-0.5 font-sans text-[11px] text-ink-faint transition-colors hover:text-ink"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}
