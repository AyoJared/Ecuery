"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { ShowcaseExample } from "@/lib/showcase";
import { ShowcaseChart } from "./ShowcaseChart";

// Plays once when scrolled into view: type the question → "querying" state → answer + chart.
export function AnswerCard({ example, className = "" }: { example: ShowcaseExample; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-20% 0px" });
  const reduceMotion = useReducedMotion() ?? false;
  const typed = useTypewriter(example.question, inView, reduceMotion);
  const typedDone = typed.length === example.question.length;
  const loaded = useDelayedFlag(typedDone, reduceMotion ? 0 : 1400);
  const loading = typedDone && !loaded;

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      className={`flex flex-col overflow-hidden rounded-3xl border border-line bg-surface/70 backdrop-blur ${className}`}
    >
      <div className="flex items-center gap-3 border-b border-line px-5 py-4 sm:px-7 sm:py-5">
        <svg className="size-4 shrink-0 text-ink-faint" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" aria-hidden>
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <p className="min-h-[1.5em] flex-1 text-base text-ink sm:text-lg">
          {typed}
          {!typedDone && <span className="ml-0.5 inline-block h-[1.1em] w-px translate-y-[0.15em] animate-pulse bg-accent" />}
        </p>
        <span
          className={`hidden shrink-0 items-center gap-2 text-xs text-ink-muted transition-opacity sm:flex ${loading ? "opacity-100" : "opacity-0"}`}
          aria-hidden={!loading}
        >
          <span className="size-3 animate-spin rounded-full border border-accent/30 border-t-accent" />
          Querying {example.source.split(" ")[0]}…
        </span>
      </div>

      {/* Skeleton and result share one grid cell per column, so nothing jumps when the answer lands. */}
      <div className="grid flex-1 gap-6 p-5 sm:p-7 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] md:gap-10">
        <div className="grid">
          <div
            className={`flex flex-col gap-3 pt-1.5 transition-opacity duration-300 [grid-area:1/1] ${loading ? "opacity-100" : "opacity-0"}`}
            aria-hidden
          >
            {["w-full", "w-11/12", "w-4/5", "w-2/3"].map((w) => (
              <span key={w} className={`h-4 animate-pulse rounded bg-surface-raised ${w}`} />
            ))}
          </div>
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={loaded ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className="flex flex-col justify-between gap-5 [grid-area:1/1]"
          >
            <p className="text-pretty text-lg leading-relaxed text-ink sm:text-xl">{example.answer}</p>
            <span className="inline-flex w-fit items-center gap-2 rounded-full border border-line px-3 py-1 text-xs text-ink-muted">
              <span className="size-1.5 rounded-full bg-accent" />
              Source: {example.source}
            </span>
          </motion.div>
        </div>

        <div className="relative h-56 sm:h-64 lg:h-auto lg:min-h-64">
          <div
            className={`absolute inset-0 flex items-end gap-2 px-2 pb-6 transition-opacity duration-300 ${loading ? "opacity-100" : "opacity-0"}`}
            aria-hidden
          >
            {[40, 55, 35, 70, 50, 85, 60].map((h, i) => (
              <span key={i} className="flex-1 animate-pulse rounded-t bg-surface-raised" style={{ height: `${h}%` }} />
            ))}
          </div>
          <motion.div
            initial={{ opacity: 0 }}
            animate={loaded ? { opacity: 1 } : {}}
            transition={{ duration: 0.4, delay: 0.15 }}
            className="absolute inset-0"
          >
            {loaded && <ShowcaseChart example={example} />}
          </motion.div>
        </div>
      </div>
    </motion.div>
  );
}

/** Becomes true `delayMs` after `start` does, and stays true. */
function useDelayedFlag(start: boolean, delayMs: number) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!start || on) return;
    const t = setTimeout(() => setOn(true), delayMs);
    return () => clearTimeout(t);
  }, [start, on, delayMs]);
  return on;
}

function useTypewriter(text: string, start: boolean, instant: boolean) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!start || instant) return;
    const id = setInterval(() => {
      setCount((c) => {
        if (c >= text.length) {
          clearInterval(id);
          return c;
        }
        return c + 1;
      });
    }, 28);
    return () => clearInterval(id);
  }, [start, instant, text]);
  if (start && instant) return text;
  return text.slice(0, count);
}
