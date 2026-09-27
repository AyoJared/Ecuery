"use client";

import {
  AnimatePresence,
  motion,
  useInView,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  type MotionValue,
} from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useClampedTransform } from "@/lib/use-clamped-transform";
import { usePageVisible } from "@/lib/use-page-visible";

const QUESTION = "How fast is global sea level rising?";
const SUGGESTIONS = [
  QUESTION,
  "How fast is global temperature rising?",
  "How fast is Arctic sea ice shrinking?",
  "How fast is CO₂ rising?",
];

// Each step's animation plays in the first ~65% of its time; the rest holds the result.
const steps = [
  {
    title: "Ask in plain English",
    body: "Type or speak a question about any place and any time range. No dashboards, no SQL.",
    durationMs: 4860,
  },
  {
    title: "We find the right data",
    body: "Your question becomes a precise query: the metric, the place and the years, routed to the right dataset.",
    durationMs: 4860,
  },
  {
    title: "Get an answer you can check",
    body: "A direct answer and a chart, with the source cited on every result.",
    durationMs: 6075,
  },
];

// Where in a step's timer its animation runs (the rest of the time holds the result).
const PLAY_RANGE: [number, number] = [0.05, 0.6];
const played = (v: number) => Math.min(Math.max((v - PLAY_RANGE[0]) / (PLAY_RANGE[1] - PLAY_RANGE[0]), 0), 1);

// Approximate global mean sea level change vs. 1993 (cm), NASA satellite altimetry.
const seaLevel = [0, 1.5, 3.2, 4.6, 6.2, 8.3, 10.1];
const seaLevelYears = ["1993", "1998", "2003", "2008", "2013", "2018", "2023"];

// "How it works": an autoplaying three-step demo. Click a step to jump to it (or replay it).
export function HowItWorks() {
  const ref = useRef<HTMLElement>(null);
  const reduceMotion = Boolean(useReducedMotion());
  const inView = useInView(ref, { amount: 0.4 });
  const pageVisible = usePageVisible();
  const playing = inView && pageVisible && !reduceMotion;

  const [step, setStep] = useState(0);
  // Bumped on every click so re-selecting the current step replays it.
  const [run, setRun] = useState(0);

  // 0 → 1 over the current step's duration; drives the stage animations and the step's timer bar.
  const progress = useMotionValue(0);
  const elapsed = useRef(0);
  useEffect(() => {
    elapsed.current = 0;
    progress.set(reduceMotion ? 1 : 0);
  }, [step, run, progress, reduceMotion]);
  useEffect(() => {
    if (!playing) return;
    const duration = steps[step].durationMs;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      elapsed.current += now - last;
      last = now;
      progress.set(Math.min(elapsed.current / duration, 1));
      if (elapsed.current >= duration) {
        setStep((s) => (s + 1) % steps.length);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, step, run, progress]);

  const drawn = useClampedTransform(progress, [0.1, 0.62], [0, 1]);

  function select(i: number) {
    setStep(i);
    setRun((r) => r + 1);
  }

  return (
    <section
      ref={ref}
      id="how-it-works"
      className="relative scroll-mt-16 border-y border-line bg-surface/30 py-24 sm:py-32"
    >
      <div className="mx-auto grid w-full max-w-6xl items-center gap-10 px-4 sm:px-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-16">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">How it works</p>
          <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.03em] text-ink sm:text-5xl">
            From question to evidence.
          </h2>

          <div role="tablist" aria-label="How it works steps" className="mt-8 flex flex-col gap-1 sm:mt-10">
            {steps.map((s, i) => {
              const active = i === step;
              return (
                <button
                  key={s.title}
                  role="tab"
                  aria-selected={active}
                  aria-controls="how-it-works-stage"
                  onClick={() => select(i)}
                  className={`group relative rounded-xl py-3 pl-6 pr-3 text-left transition-colors ${
                    active ? "bg-surface-raised/60" : "hover:bg-surface-raised/30"
                  }`}
                >
                  {/* Timer rail: fills over the step's duration while it plays */}
                  <span aria-hidden className="absolute bottom-3 left-2.5 top-3 w-px bg-line-strong" />
                  {active && (
                    <motion.span
                      aria-hidden
                      className="absolute bottom-3 left-2.5 top-3 w-px origin-top bg-accent"
                      style={{ scaleY: reduceMotion ? 1 : progress }}
                    />
                  )}
                  <span className="font-mono text-xs text-accent">0{i + 1}</span>
                  <span
                    className={`mt-0.5 block text-lg font-semibold tracking-tight transition-colors sm:text-xl ${
                      active ? "text-ink" : "text-ink-faint group-hover:text-ink-muted"
                    }`}
                  >
                    {s.title}
                  </span>
                  <span
                    className={`block overflow-hidden text-sm leading-relaxed text-ink-muted transition-all duration-500 ${
                      active ? "mt-1.5 max-h-24 min-h-[4.25rem] opacity-100 lg:min-h-0" : "max-h-0 opacity-0"
                    }`}
                  >
                    {s.body}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div
          id="how-it-works-stage"
          // Tall enough for the answer + chart step, so the page doesn't shift as steps change.
          role="tabpanel"
          className="flex min-h-[440px] flex-col rounded-3xl border border-line bg-canvas/70 p-5 shadow-2xl shadow-black/40 sm:min-h-[520px] sm:p-7"
        >
          <FakeSearch key={`search-${step}-${run}`} progress={progress} full={step > 0 || reduceMotion} />
          <AnimatePresence mode="wait">
            {step === 1 && <QueryStage key={`query-${run}`} progress={progress} />}
            {step === 2 && <AnswerStage key={`answer-${run}`} progress={drawn} still={reduceMotion} />}
          </AnimatePresence>
          <p className="mt-auto pt-4 text-right text-[11px] text-ink-faint">Example · approximate figures</p>
        </div>
      </div>
    </section>
  );
}

// Subscribes to the step's base timer (set only in effects/rAF), never to a derived transform:
// transforms recompute during the parent's render and would setState mid-render.
function FakeSearch({ progress, full }: { progress: MotionValue<number>; full: boolean }) {
  const [text, setText] = useState(full ? QUESTION : "");
  useMotionValueEvent(progress, "change", (v) => {
    if (!full) setText(QUESTION.slice(0, Math.round(played(v) * QUESTION.length)));
  });
  const shown = full ? QUESTION : text;
  // Autocomplete-style list that narrows as the question is typed.
  const matches =
    !full && shown.length >= 4
      ? SUGGESTIONS.filter((q) => q.toLowerCase().startsWith(shown.toLowerCase()))
      : [];
  return (
    <div>
      <div className="flex items-center gap-3 rounded-2xl border border-line-strong bg-surface px-4 py-3.5">
        <svg
          className="size-4 shrink-0 text-ink-faint"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          aria-hidden
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <p className="min-h-[1.5em] text-sm text-ink sm:text-base">
          {shown || <span className="text-ink-faint">Ask anything about the planet…</span>}
          {!full && shown.length < QUESTION.length && (
            <span className="ml-0.5 inline-block h-[1.1em] w-px translate-y-[0.15em] animate-pulse bg-accent" />
          )}
        </p>
      </div>
      {matches.length > 0 && (
        <ul className="mt-2 overflow-hidden rounded-2xl border border-line bg-surface/80 py-1.5">
          {matches.map((q) => (
            <li key={q} className="flex items-center gap-3 px-4 py-2 text-sm text-ink-muted">
              <svg
                className="size-3.5 shrink-0 text-ink-faint"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                aria-hidden
              >
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-3.5-3.5" />
              </svg>
              <span>
                <span className="text-ink">{q.slice(0, shown.length)}</span>
                {q.slice(shown.length)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const fade = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as const },
};

function QueryStage({ progress }: { progress: MotionValue<number> }) {
  const chips = [
    ["Metric", "Global mean sea level"],
    ["Place", "Worldwide"],
    ["Time", "1993 – today"],
    ["Source", "NASA satellite altimetry"],
  ];
  const [shown, setShown] = useState(0);
  useMotionValueEvent(progress, "change", (v) => setShown(Math.ceil(played(v) * (chips.length + 1))));

  return (
    <motion.div {...fade} className="mt-6 flex flex-col gap-4">
      <p className="text-xs uppercase tracking-[0.14em] text-ink-faint">Understood as</p>
      <div className="flex flex-wrap gap-2">
        {chips.map(([k, v], i) => (
          <motion.span
            key={k}
            initial={false}
            animate={{ opacity: i < shown ? 1 : 0.15, y: i < shown ? 0 : 6 }}
            transition={{ duration: 0.3 }}
            className="rounded-full border border-line-strong bg-surface-raised px-3 py-1.5 text-sm"
          >
            <span className="text-ink-faint">{k}: </span>
            <span className="text-ink">{v}</span>
          </motion.span>
        ))}
      </div>
      <motion.pre
        initial={false}
        animate={{ opacity: shown > chips.length ? 1 : 0.15 }}
        transition={{ duration: 0.3 }}
        className="overflow-x-auto rounded-xl border border-line bg-surface px-4 py-3 font-mono text-[11px] leading-relaxed text-ink-muted sm:text-xs"
      >
        <span className="text-accent">SELECT</span> year, avg(gmsl_cm){"\n"}
        <span className="text-accent">FROM</span> nasa_sea_level{"\n"}
        <span className="text-accent">WHERE</span> year &gt;= 1993{" "}
        <span className="text-accent">GROUP BY</span> year;
      </motion.pre>
    </motion.div>
  );
}

function AnswerStage({ progress, still }: { progress: MotionValue<number>; still: boolean }) {
  const w = 320;
  const h = 120;
  const max = 11;
  const points = seaLevel.map((v, i) => [(i / (seaLevel.length - 1)) * w, h - (v / max) * h] as const);
  const line = points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L${w} ${h} L0 ${h} Z`;
  const areaOpacity = useClampedTransform(progress, [0.5, 1], [0, 1]);

  return (
    <motion.div {...fade} className="mt-6 flex flex-col gap-4">
      <p className="text-pretty text-base leading-relaxed text-ink sm:text-lg">
        Global sea level has risen about <span className="text-accent">10 cm</span> since satellite records
        began in 1993, and the yearly rate has more than doubled.
      </p>
      <svg
        viewBox={`0 -6 ${w} ${h + 26}`}
        className="w-full"
        aria-label="Sea level rise since 1993, approximately 10 centimeters"
      >
        <defs>
          <linearGradient id="hiw-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#7cc4f5" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#7cc4f5" stopOpacity={0} />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={0} x2={w} y1={h * f} y2={h * f} stroke="rgb(214 235 222 / 0.06)" />
        ))}
        <motion.path d={area} fill="url(#hiw-area)" style={{ opacity: still ? 1 : areaOpacity }} />
        <motion.path
          d={line}
          fill="none"
          stroke="#7cc4f5"
          strokeWidth={2.5}
          strokeLinecap="round"
          style={{ pathLength: still ? 1 : progress }}
        />
        {seaLevelYears.map((year, i) =>
          i % 2 === 0 ? (
            <text
              key={year}
              x={(i / (seaLevelYears.length - 1)) * w}
              y={h + 18}
              textAnchor={i === 0 ? "start" : i === seaLevelYears.length - 1 ? "end" : "middle"}
              className="fill-ink-faint text-[10px]"
            >
              {year}
            </text>
          ) : null,
        )}
      </svg>
      <span className="inline-flex w-fit items-center gap-2 rounded-full border border-line px-3 py-1 text-xs text-ink-muted">
        <svg
          className="size-3.5 text-accent"
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
        Source: NASA satellite altimetry
      </span>
    </motion.div>
  );
}
