"use client";

import { motion } from "motion/react";
import { useRef, useState, type ReactNode } from "react";
import { audioSrc } from "@/lib/api/client";
import { isEventsAnswer, type AnsweredResponse } from "@/lib/api/types";
import { eventTypeLabel } from "@/lib/event-types";
import { formatDate, formatRange, metricLabel, operationLabel, totalSeconds } from "@/lib/format";
import { AnswerChart } from "./AnswerChart";
import { EventsPanel } from "./EventsPanel";

const EASE = [0.22, 1, 0.36, 1] as const;

const rise = (delay: number) => ({
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.55, delay, ease: EASE },
});

/** Full answer (compact=false) or the condensed card used for follow-ups in the chat. */
export function AnswerView({ answer, compact = false }: { answer: AnsweredResponse; compact?: boolean }) {
  const [showDetails, setShowDetails] = useState(!compact);

  return (
    <div className="flex flex-col gap-5">
      <motion.p
        {...rise(0)}
        className={`text-pretty leading-relaxed text-ink ${compact ? "text-base" : "text-lg sm:text-xl"}`}
      >
        {answer.answer_text}
      </motion.p>

      <motion.div {...rise(0.08)} className="flex flex-wrap items-center gap-2">
        <ListenButton url={answer.audio_url} />
        <VerificationBadge answer={answer} />
        <span className="text-xs text-ink-faint">Answered in {totalSeconds(answer.timings)}s</span>
      </motion.div>

      <motion.section {...rise(0.16)} className="rounded-3xl border border-line bg-surface/60 p-4 sm:p-6">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2 px-1">
          <h2 className="text-sm font-semibold text-ink sm:text-base">{answer.chart.title}</h2>
          <span className="text-xs text-ink-faint">{answer.chart.y_label}</span>
        </div>
        <AnswerChart chart={answer.chart} height={compact ? 220 : 300} />
      </motion.section>

      {isEventsAnswer(answer) && (
        <motion.div {...rise(0.2)}>
          <EventsPanel answer={answer} compact={compact} />
        </motion.div>
      )}

      {compact && (
        <button
          onClick={() => setShowDetails((s) => !s)}
          aria-expanded={showDetails}
          className="w-fit text-sm text-accent transition-colors hover:text-accent-soft"
        >
          {showDetails ? "Hide details" : "Show trends and sources"}
        </button>
      )}

      {showDetails && (
        <>
          {(answer.trends.length > 0 || answer.comparison) && (
            <motion.div
              {...rise(compact ? 0 : 0.24)}
              className={`grid gap-4 ${answer.trends.length > 0 && answer.comparison ? "md:grid-cols-2" : ""}`}
            >
              {answer.trends.length > 0 && (
                <Panel title="Trends">
                  <ul className="flex flex-col gap-2.5">
                    {answer.trends.map((t) => (
                      <li key={t} className="flex gap-3 text-sm leading-relaxed text-ink-muted">
                        <span className="mt-2 size-1.5 shrink-0 rounded-full bg-accent" />
                        {t}
                      </li>
                    ))}
                  </ul>
                </Panel>
              )}
              {answer.comparison && (
                <Panel title="Compared with">
                  <p className="text-sm leading-relaxed text-ink-muted">{answer.comparison}</p>
                </Panel>
              )}
            </motion.div>
          )}

          <motion.div {...rise(compact ? 0.05 : 0.3)}>
            <Understood answer={answer} />
          </motion.div>

          <motion.div {...rise(compact ? 0.1 : 0.36)}>
            <Sources answer={answer} />
          </motion.div>
        </>
      )}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-surface/40 p-5">
      <h3 className="mb-3 text-xs font-medium uppercase tracking-[0.14em] text-ink-faint">{title}</h3>
      {children}
    </section>
  );
}

/** "How we read your question": the plan the backend actually ran. */
function Understood({ answer }: { answer: AnsweredResponse }) {
  // Readings and event answers carry different plans (see lib/api/types.ts).
  const chips: [string, string][] = isEventsAnswer(answer)
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
    <Panel title="How we read your question">
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
    </Panel>
  );
}

function Sources({ answer }: { answer: AnsweredResponse }) {
  const v = answer.verification;
  return (
    <Panel title="Sources and verification">
      {answer.data_notes.length > 0 && (
        <ul className="mb-4 flex flex-col gap-1.5">
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
            <li
              key={p.batch_id}
              className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 text-sm"
            >
              <span>
                <span className="font-medium text-ink">{p.source}</span>
                <span className="text-ink-muted"> · {p.dataset}</span>
                {p.quality === "preliminary" && <span className="ml-2 text-xs text-sun">preliminary</span>}
              </span>
              <span className="flex items-center gap-3 text-xs text-ink-faint">
                {p.row_count} rows · fetched {formatDate(p.fetched_at)}
                {p.explorer_url && (
                  <a
                    href={p.explorer_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-accent hover:text-accent-soft"
                  >
                    Anchor ↗
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

      <dl className="mt-4 grid gap-x-6 gap-y-2 font-mono text-xs sm:grid-cols-[auto_1fr]">
        <dt className="text-ink-faint">answer sha-256</dt>
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
    </Panel>
  );
}

function VerificationBadge({ answer }: { answer: AnsweredResponse }) {
  const { badge, mode, explorer_url } = answer.verification;
  const onChain = badge.verified && mode === "rpc" && explorer_url;
  const classes = badge.verified
    ? "border-accent/35 bg-accent/10 text-accent"
    : "border-sun/35 bg-sun/10 text-sun";
  const content = (
    <>
      <svg
        className="size-3.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        {badge.verified ? <path d="m5 12 5 5L20 7" /> : <path d="M12 8v5M12 16.5v.5" />}
      </svg>
      {badge.label}
      {onChain && <span aria-hidden>↗</span>}
    </>
  );
  const className = `inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium ${classes}`;
  return onChain ? (
    <a
      href={explorer_url}
      target="_blank"
      rel="noreferrer"
      className={`${className} transition-colors hover:bg-accent/20`}
    >
      {content}
    </a>
  ) : (
    <span
      className={className}
      title={mode === "mock" ? "Simulated: no Solana wallet is configured" : answer.verification.error}
    >
      {content}
    </span>
  );
}

function ListenButton({ url }: { url: string }) {
  const src = audioSrc(url);
  const audio = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");

  function toggle() {
    if (!src) return;
    if (!audio.current) {
      audio.current = new Audio(src);
      audio.current.addEventListener("playing", () => setState("playing"));
      audio.current.addEventListener("pause", () => setState("idle"));
      audio.current.addEventListener("ended", () => setState("idle"));
      audio.current.addEventListener("error", () => setState("idle"));
    }
    if (state === "playing") {
      audio.current.pause();
    } else {
      setState("loading");
      audio.current.play().catch(() => setState("idle"));
    }
  }

  return (
    <button
      onClick={toggle}
      disabled={!src}
      title={src ? undefined : "Voice needs the backend (NEXT_PUBLIC_API_MODE=live)"}
      className="inline-flex items-center gap-2 rounded-full border border-line-strong px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:bg-surface-raised disabled:cursor-not-allowed disabled:opacity-45"
    >
      {state === "playing" ? (
        <svg className="size-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <rect x="6" y="5" width="4" height="14" rx="1" />
          <rect x="14" y="5" width="4" height="14" rx="1" />
        </svg>
      ) : state === "loading" ? (
        <span className="size-3.5 animate-spin rounded-full border-2 border-ink/25 border-t-ink" />
      ) : (
        <svg className="size-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M7 5.5v13a1 1 0 0 0 1.5.86l11-6.5a1 1 0 0 0 0-1.72l-11-6.5A1 1 0 0 0 7 5.5Z" />
        </svg>
      )}
      {state === "playing" ? "Pause" : "Listen"}
    </button>
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
