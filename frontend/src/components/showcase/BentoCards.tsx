"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { useRef, useState, type ReactNode } from "react";
import { useSearch } from "@/components/search/SearchContext";
import { showcaseExamples } from "@/lib/showcase";

const EASE = [0.22, 1, 0.36, 1] as const;

type BentoCardProps = {
  eyebrow: string;
  title: string;
  soon?: boolean;
  className?: string;
  children: ReactNode;
};

// Shared shell for the small cards in the showcase grid.
export function BentoCard({ eyebrow, title, soon, className = "", children }: BentoCardProps) {
  return (
    <div
      className={`flex flex-col gap-5 rounded-3xl border border-line bg-surface/60 p-6 transition-colors hover:border-line-strong ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-ink-faint">{eyebrow}</p>
          <h3 className="mt-1.5 text-lg font-semibold tracking-tight text-ink">{title}</h3>
        </div>
        {soon && (
          <span className="shrink-0 rounded-full border border-sun/30 bg-sun/10 px-2.5 py-0.5 text-[11px] text-sun">
            Coming soon
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

// ---------- Voice ----------

export function VoiceCard() {
  const reduceMotion = useReducedMotion();
  const [playing, setPlaying] = useState(true);
  const bars = Array.from(
    { length: 32 },
    (_, i) => 0.25 + 0.75 * Math.abs(Math.sin(i * 1.7) * Math.cos(i * 0.45)),
  );
  const animated = playing && !reduceMotion;

  return (
    <BentoCard eyebrow="Listen" title="Hear the answer" soon>
      <div className="flex items-center gap-4">
        <button
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? "Pause waveform preview" : "Play waveform preview"}
          className="grid size-11 shrink-0 place-items-center rounded-full bg-accent text-canvas transition-colors hover:bg-accent-soft"
        >
          {playing ? (
            <svg className="size-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <rect x="6" y="5" width="4" height="14" rx="1" />
              <rect x="14" y="5" width="4" height="14" rx="1" />
            </svg>
          ) : (
            <svg className="size-4 translate-x-px" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M7 5.5v13a1 1 0 0 0 1.5.86l11-6.5a1 1 0 0 0 0-1.72l-11-6.5A1 1 0 0 0 7 5.5Z" />
            </svg>
          )}
        </button>
        <div className="flex h-10 flex-1 items-center gap-[3px]" aria-hidden>
          {bars.map((h, i) => (
            <span
              key={i}
              className={`w-full rounded-full bg-accent/70 ${animated ? "animate-[wave_1.1s_ease-in-out_infinite_alternate]" : ""}`}
              style={{ height: `${(h * 100).toFixed(1)}%`, animationDelay: `${((i % 8) * -0.14).toFixed(2)}s` }}
            />
          ))}
        </div>
      </div>
      <p className="text-sm leading-relaxed text-ink-muted">
        Every answer can be read aloud in a natural voice, for when you&apos;re on the move.
      </p>
    </BentoCard>
  );
}

// ---------- Verified source ----------

export function VerifiedCard() {
  return (
    <BentoCard eyebrow="Trust" title="Verified source" soon>
      <div className="rounded-2xl border border-line bg-canvas/60 p-4 font-mono text-[11px] leading-relaxed text-ink-muted sm:text-xs">
        <div className="flex items-center justify-between gap-3">
          <span className="text-ink-faint">sha-256</span>
          <span className="truncate text-ink">9f2c7b…e41a</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-ink-faint">recorded on</span>
          <span className="text-ink">Solana</span>
        </div>
        <div className="mt-2 flex items-center gap-2 border-t border-line pt-2 text-accent">
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
            <path d="m5 12 5 5L20 7" />
          </svg>
          Data unchanged since query
        </div>
      </div>
      <p className="text-sm leading-relaxed text-ink-muted">
        Each answer&apos;s data is fingerprinted and logged on-chain, so anyone can check it wasn&apos;t
        altered.
      </p>
    </BentoCard>
  );
}

// ---------- Compare two years ----------

export function CompareCard() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const data = showcaseExamples[1].data;
  const pair = [data.find((d) => d.label === "2023")!, data.find((d) => d.label === "2024")!];
  const max = Math.max(...pair.map((d) => d.value));

  return (
    <BentoCard eyebrow="Compare" title="Any two years, side by side">
      <div ref={ref} className="flex h-32 items-end gap-5">
        {pair.map((d, i) => (
          <div key={d.label} className="flex h-full flex-1 flex-col justify-end gap-2">
            <span className="text-sm font-semibold text-ink">{d.value}M</span>
            <motion.span
              className={`block w-full origin-bottom rounded-t-lg ${i === 0 ? "bg-wildfire" : "bg-wildfire/40"}`}
              style={{ height: `${(d.value / max) * 100}%` }}
              initial={{ scaleY: 0 }}
              animate={{ scaleY: inView ? 1 : 0 }}
              transition={{ duration: 1, delay: i * 0.15, ease: EASE }}
            />
            <span className="text-xs text-ink-faint">{d.label}</span>
          </div>
        ))}
      </div>
      <p className="text-sm leading-relaxed text-ink-muted">Acres burned in Canada: 2023 vs 2024.</p>
    </BentoCard>
  );
}

// ---------- Trend ----------

export function TrendCard() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const data = showcaseExamples[2].data;
  const first = data[0].value;
  const last = data[data.length - 1].value;
  const change = Math.round(((last - first) / first) * 100);

  const w = 240;
  const h = 72;
  const min = Math.min(...data.map((d) => d.value));
  const max = Math.max(...data.map((d) => d.value));
  const line = data
    .map(
      (d, i) =>
        `${i ? "L" : "M"}${((i / (data.length - 1)) * w).toFixed(1)} ${(h - ((d.value - min) / (max - min)) * h).toFixed(1)}`,
    )
    .join(" ");

  return (
    <BentoCard eyebrow="Trends" title="Decades at a glance">
      <div ref={ref} className="flex flex-col gap-3">
        <p className="flex items-baseline gap-2">
          <span className="text-4xl font-semibold tracking-[-0.04em] text-ink">+{change}%</span>
          <span className="text-sm text-ink-muted">CO₂ since {data[0].label}</span>
        </p>
        <svg
          viewBox={`0 -4 ${w} ${h + 8}`}
          className="w-full"
          aria-label={`CO₂ at Mauna Loa up ${change}% since ${data[0].label}`}
        >
          <motion.path
            d={line}
            fill="none"
            stroke="var(--color-sun)"
            strokeWidth={2.5}
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: inView ? 1 : 0 }}
            transition={{ duration: 1.6, ease: EASE }}
          />
        </svg>
      </div>
      <p className="text-sm leading-relaxed text-ink-muted">
        Mauna Loa, {data[0].label}–{data[data.length - 1].label}.
      </p>
    </BentoCard>
  );
}

// ---------- Your turn ----------

export function AskCard() {
  const { ask } = useSearch();
  return (
    <div className="relative flex flex-col justify-between gap-6 overflow-hidden rounded-3xl border border-accent/30 bg-gradient-to-br from-accent/15 via-surface/60 to-sun/10 p-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-accent">Your turn</p>
        <h3 className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">What do you want to know?</h3>
      </div>
      <button
        onClick={() => ask()}
        className="w-fit rounded-full bg-sun px-5 py-2.5 text-sm font-medium text-canvas transition-colors hover:bg-sun-soft"
      >
        Ask a question
      </button>
    </div>
  );
}
