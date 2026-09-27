"use client";

import { motion } from "motion/react";
import { useRef, useState, type ReactNode } from "react";
import { insightFor, toneColor, type Insight } from "@/lib/answer-insights";
import { audioSrc } from "@/lib/api/client";
import {
  isEventsAnswer,
  isForecastAnswer,
  isLikelihoodAnswer,
  isWebAnswer,
  type AnsweredResponse,
  type ForecastAnswer,
  type LikelihoodAnswer,
  type WebAnswer,
} from "@/lib/api/types";
import { metricLabel, totalSeconds } from "@/lib/format";
import { AnswerChart, ChartTable } from "./AnswerChart";
import { EventsPanel } from "./EventsPanel";
import { SourceLinks } from "./SourceLinks";
import { SourcesButton } from "./SourcesDrawer";

const EASE = [0.22, 1, 0.36, 1] as const;

const rise = (delay: number) => ({
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.55, delay, ease: EASE },
});

/**
 * One answer. Leads with the headline number, then the sentence, the chart, and the details.
 * compact = the condensed version used for follow-ups in the chat.
 */
export function AnswerView({ answer, compact = false }: { answer: AnsweredResponse; compact?: boolean }) {
  const insight = insightFor(answer);
  const [view, setView] = useState<"chart" | "table">("chart");

  return (
    <div className={`flex flex-col ${compact ? "gap-5" : "gap-7"}`}>
      <motion.p {...rise(0)} className="text-sm text-ink-faint">
        {insight.context.filter(Boolean).join(" · ")}
      </motion.p>

      {insight.headline.value && (
        <motion.div {...rise(0.05)}>
          <Headline insight={insight} compact={compact} />
        </motion.div>
      )}

      {insight.stats.length > 0 && (
        <motion.dl
          {...rise(0.1)}
          className="grid grid-cols-2 gap-y-4 border-y border-line py-4 sm:flex sm:flex-wrap sm:gap-x-0"
        >
          {insight.stats.map((s) => (
            <div
              key={s.label}
              className="min-w-0 sm:border-l sm:border-line sm:px-6 sm:first:border-l-0 sm:first:pl-0"
            >
              <dt className="truncate text-xs text-ink-faint">{s.label}</dt>
              <dd className="mt-1 text-lg font-semibold tracking-tight text-ink tabular-nums">{s.value}</dd>
              {s.hint && <dd className="truncate text-xs text-ink-muted">{s.hint}</dd>}
            </div>
          ))}
        </motion.dl>
      )}

      <motion.p
        {...rise(0.15)}
        className={`max-w-3xl text-pretty leading-relaxed text-ink-muted ${compact ? "text-base" : "text-base sm:text-lg"}`}
      >
        {answer.answer_text}
      </motion.p>

      <motion.div {...rise(0.2)} className="flex flex-wrap items-center gap-2">
        <ListenButton url={answer.audio_url} />
        <GroundingBadge answer={answer} />
        <VerificationBadge answer={answer} />
        <SourcesButton answer={answer} />
        <span className="text-xs text-ink-faint">Answered in {totalSeconds(answer.timings)}s</span>
      </motion.div>

      {answer.source_links?.length ? (
        <motion.div {...rise(0.22)}>
          <SourceLinks links={answer.source_links} />
        </motion.div>
      ) : null}

      {answer.chart && (
        <motion.section {...rise(0.25)} aria-label="Chart">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink sm:text-base">
                {answer.chart.title}
                {isForecastAnswer(answer) && (
                  <span className="rounded-full border border-sun/35 bg-sun/10 px-2 py-0.5 text-[11px] font-medium text-sun">
                    Forecast
                  </span>
                )}
              </h2>
              <p className="text-xs text-ink-faint">{answer.chart.y_label}</p>
            </div>
            <div
              role="tablist"
              aria-label="Chart or table"
              className="flex rounded-full border border-line p-0.5 text-xs"
            >
              {(["chart", "table"] as const).map((v) => (
                <button
                  key={v}
                  role="tab"
                  aria-selected={view === v}
                  onClick={() => setView(v)}
                  className={`rounded-full px-3 py-1 capitalize transition-colors ${
                    view === v ? "bg-surface-raised text-ink" : "text-ink-faint hover:text-ink-muted"
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
          {view === "chart" ? (
            <AnswerChart chart={answer.chart} height={compact ? 220 : 320} references={insight.references} />
          ) : (
            <ChartTable chart={answer.chart} />
          )}
        </motion.section>
      )}

      {isWebAnswer(answer) && (
        <motion.div {...rise(0.25)}>
          <WebQuotes answer={answer} />
        </motion.div>
      )}

      {isEventsAnswer(answer) && (
        <motion.div {...rise(0.3)}>
          <EventsPanel answer={answer} compact={compact} />
        </motion.div>
      )}

      {isLikelihoodAnswer(answer) && (
        <motion.div {...rise(0.3)}>
          <LikelihoodPanel answer={answer} />
        </motion.div>
      )}

      {isForecastAnswer(answer) && !compact && (
        <motion.div {...rise(0.3)}>
          <ForecastMethods answer={answer} />
        </motion.div>
      )}

      {!compact && (answer.trends.length > 0 || answer.comparison) && (
        <motion.section {...rise(0.35)} aria-label="Trends" className="flex flex-col gap-4">
          {answer.comparison && (
            <p className="border-l-2 border-accent pl-4 text-base leading-relaxed text-ink">
              {answer.comparison}
            </p>
          )}
          {answer.trends.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-[0.14em] text-ink-faint">Trends</h3>
              <ul className="flex flex-col gap-2">
                {answer.trends.map((t) => (
                  <li key={t} className="flex gap-3 text-sm leading-relaxed text-ink-muted">
                    <span className="mt-2 size-1.5 shrink-0 rounded-full bg-accent" />
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </motion.section>
      )}
    </div>
  );
}

/** The big number: value + unit, with an optional colored badge (air-quality level, change vs usual). */
function Headline({ insight, compact }: { insight: Insight; compact: boolean }) {
  const { value, unit, label, badge } = insight.headline;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
        <p className="flex items-baseline gap-2 font-semibold tracking-[-0.04em] text-ink">
          <span className={`tabular-nums ${compact ? "text-4xl" : "text-6xl sm:text-7xl"}`}>{value}</span>
          {unit && (
            <span className={`text-accent ${compact ? "text-lg" : "text-2xl sm:text-3xl"}`}>{unit}</span>
          )}
        </p>
        {badge && (
          <span
            className="mb-2 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium"
            style={{
              color: toneColor[badge.tone],
              borderColor: `color-mix(in srgb, ${toneColor[badge.tone]} 40%, transparent)`,
              background: `color-mix(in srgb, ${toneColor[badge.tone]} 12%, transparent)`,
            }}
          >
            <span className="size-2 rounded-full" style={{ background: toneColor[badge.tone] }} />
            {badge.text}
          </span>
        )}
      </div>
      <p className="text-sm text-ink-muted">{label}</p>
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

/** Web answers: each fact next to the exact words from the page that support it. */
function WebQuotes({ answer }: { answer: WebAnswer }) {
  return (
    <Panel title="Quoted from the sources">
      <ul className="flex flex-col gap-4">
        {answer.web.quotes.map((q, i) => {
          const src = answer.web.sources[q.source];
          return (
            <li key={i} className="text-sm leading-relaxed">
              <blockquote className="border-l-2 border-accent/60 pl-3 text-ink">&ldquo;{q.quote}&rdquo;</blockquote>
              {src && (
                <a
                  href={src.url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-block pl-3 text-xs text-accent hover:text-accent-soft"
                >
                  {src.title} ↗
                </a>
              )}
            </li>
          );
        })}
      </ul>
      <p className="mt-4 text-xs leading-relaxed text-ink-faint">
        Every quote was checked word for word against the page text Ecuery downloaded, and every number in the answer
        appears in a quote. The pages&apos; fingerprints are anchored on Solana with the answer. The sources are cited,
        not measured data.
      </p>
    </Panel>
  );
}

/** "How this forecast was made": which method produced which part, and the range it gives. */
function ForecastMethods({ answer }: { answer: ForecastAnswer }) {
  return (
    <Panel title="How this forecast was made">
      <ul className="flex flex-col gap-3">
        {answer.data.map((s) => {
          const place = answer.plan.places[s.location]?.label ?? s.location;
          const range =
            s.summary?.range_lo != null && s.summary?.range_hi != null
              ? `${s.summary.range_lo}–${s.summary.range_hi} ${s.unit}`
              : null;
          return (
            <li key={`${s.metric}-${s.location}`} className="text-sm leading-relaxed">
              <span className="font-medium text-ink">
                {metricLabel(s.metric)} · {place}
              </span>
              {range && <span className="text-ink-faint"> · range {range}</span>}
              <ul className="mt-1 flex flex-wrap gap-1.5">
                {s.method_labels.map((m) => (
                  <li key={m} className="rounded-full border border-line px-2.5 py-0.5 text-xs text-ink-muted">
                    {m}
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs leading-relaxed text-ink-faint">
        Forecasts are saved with their Solana record and scored against what actually happens.
      </p>
    </Panel>
  );
}

function LikelihoodPanel({ answer }: { answer: LikelihoodAnswer }) {
  const l = answer.likelihood;
  return (
    <Panel title="Likelihood">
      <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
        <div>
          <p className="text-3xl font-semibold text-ink">{l.probability_text}</p>
          <p className="text-xs text-ink-faint">chance of at least one</p>
        </div>
        <div>
          <p className="text-xl font-semibold text-ink">{l.expected_count}</p>
          <p className="text-xs text-ink-faint">expected in the period</p>
        </div>
        <div>
          <p className="text-xl font-semibold text-ink">
            {l.windows_with_events} of {l.windows_total}
          </p>
          <p className="text-xs text-ink-faint">recent years had one</p>
        </div>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-ink-faint">
        Based on how often this happened in the same area and season in recent years. Not a prediction of a specific event.
      </p>
    </Panel>
  );
}

/** Did every figure in the answer match the data it came from? (backend/ask/factcheck.py) */
function GroundingBadge({ answer }: { answer: AnsweredResponse }) {
  const g = answer.grounding;
  if (!g) return null;
  return (
    <span
      title="Every number, date and rating in the answer is checked against the source data before it is shown"
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium ${
        g.ok ? "border-accent/35 bg-accent/10 text-accent" : "border-sun/35 bg-sun/10 text-sun"
      }`}
    >
      {g.ok ? "✓" : "!"} {g.label}
    </span>
  );
}

function VerificationBadge({ answer }: { answer: AnsweredResponse }) {
  const { badge, mode, explorer_url } = answer.verification;
  const onChain = badge.verified && mode === "rpc" && explorer_url;
  const classes = badge.verified ? "border-good/35 bg-good/10 text-good" : "border-sun/35 bg-sun/10 text-sun";
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
      className={`${className} transition-colors hover:bg-good/20`}
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
      title={src ? undefined : "No spoken version for this answer"}
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
