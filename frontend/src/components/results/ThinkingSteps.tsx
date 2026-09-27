"use client";

import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";

// Mirrors the backend pipeline (backend/ask/pipeline.py), so the wait reads as real work.
const STEPS = [
  "Understanding your question",
  "Finding the right datasets",
  "Querying recent and historical data",
  "Analyzing trends",
  "Fingerprinting and verifying on Solana",
];

const STEP_MS = 850;
const FINISH_MS = 160;

type ThinkingStepsProps = {
  /** Flip to true when the answer has arrived: remaining steps complete quickly, then onFinished fires. */
  done: boolean;
  onFinished: () => void;
  compact?: boolean;
};

export function ThinkingSteps({ done, onFinished, compact = false }: ThinkingStepsProps) {
  // Number of completed steps. The last step stays "in progress" until the answer arrives.
  const [completed, setCompleted] = useState(0);
  // Held in a ref so a parent re-render (new callback identity) doesn't restart the step timer.
  const finished = useRef(onFinished);
  useEffect(() => {
    finished.current = onFinished;
  });

  useEffect(() => {
    if (completed >= STEPS.length) {
      const t = setTimeout(() => finished.current(), compact ? 150 : 350);
      return () => clearTimeout(t);
    }
    if (!done && completed >= STEPS.length - 1) return;
    const t = setTimeout(() => setCompleted((c) => c + 1), done ? FINISH_MS : STEP_MS);
    return () => clearTimeout(t);
  }, [completed, done, compact]);

  const current = Math.min(completed, STEPS.length - 1);

  if (compact) {
    return (
      <div className="flex items-center gap-3 text-sm text-ink-muted" role="status" aria-live="polite">
        <Spinner />
        <motion.span key={current} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}>
          {STEPS[current]}…
        </motion.span>
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-line bg-surface/60 p-6 sm:p-8" role="status" aria-live="polite">
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Working on it</p>
      <ol className="mt-5 flex flex-col gap-3.5">
        {STEPS.map((step, i) => {
          const state = i < completed ? "done" : i === completed ? "active" : "todo";
          return (
            <motion.li
              key={step}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: state === "todo" ? 0.35 : 1, x: 0 }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
              className="flex items-center gap-3 text-sm sm:text-base"
            >
              <span className="grid size-5 shrink-0 place-items-center">
                {state === "done" ? (
                  <svg className="size-4 text-good" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                    <path d="m5 12 5 5L20 7" />
                  </svg>
                ) : state === "active" ? (
                  <Spinner />
                ) : (
                  <span className="size-1.5 rounded-full bg-ink-faint" />
                )}
              </span>
              <span className={state === "done" ? "text-ink-muted" : state === "active" ? "text-ink" : "text-ink-faint"}>
                {step}
              </span>
            </motion.li>
          );
        })}
      </ol>
      {/* Shimmer preview of where the answer and chart will land */}
      <div className="mt-8 flex flex-col gap-3" aria-hidden>
        <span className="h-4 w-11/12 animate-pulse rounded bg-surface-raised" />
        <span className="h-4 w-4/5 animate-pulse rounded bg-surface-raised" />
        <span className="mt-3 h-40 w-full animate-pulse rounded-2xl bg-surface-raised/70" />
      </div>
    </div>
  );
}

function Spinner() {
  return <span className="size-4 shrink-0 animate-spin rounded-full border-2 border-accent/25 border-t-accent" />;
}
