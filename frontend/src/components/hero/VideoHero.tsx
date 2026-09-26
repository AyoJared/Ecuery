"use client";

import {
  AnimatePresence,
  motion,
  useInView,
  useMotionValue,
  useReducedMotion,
  useScroll,
  useTransform,
  type MotionValue,
} from "motion/react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { HazardIcon } from "@/components/globe/HazardIcon";
import { useSearch } from "@/components/search/SearchContext";
import { hazardColors } from "@/lib/hazard-icons";
import { HERO_CLIP_DURATION_MS, heroClips } from "@/lib/hero-clips";
import { ClipLayer } from "./ClipLayer";

const EASE = [0.22, 1, 0.36, 1] as const;

export function VideoHero() {
  const { ask } = useSearch();
  const ref = useRef<HTMLElement>(null);
  const reduceMotion = useReducedMotion() ?? false;
  const inView = useInView(ref, { amount: 0.25 });
  const pageVisible = usePageVisible();
  const isMobile = useIsMobile();

  const [index, setIndex] = useState(0);
  const clip = heroClips[index];
  const durationMs = clip.durationMs ?? HERO_CLIP_DURATION_MS;
  const playing = inView && pageVisible && !reduceMotion;

  // Clip timer: pauses when the hero is off screen or the tab is hidden.
  const progress = useMotionValue(0);
  const elapsed = useRef(0);
  useEffect(() => {
    elapsed.current = 0;
    progress.set(0);
  }, [index, progress]);
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      elapsed.current += now - last;
      last = now;
      progress.set(Math.min(elapsed.current / durationMs, 1));
      if (elapsed.current >= durationMs) {
        setIndex((i) => (i + 1) % heroClips.length);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, index, durationMs, progress]);

  // Content fades and lifts as the hero scrolls away.
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const contentOpacity = useTransform(scrollYProgress, [0, 0.6], [1, 0]);
  const contentY = useTransform(scrollYProgress, [0, 1], [0, -100]);

  return (
    <section ref={ref} className="relative isolate -mt-16 flex h-[88svh] min-h-[560px] flex-col overflow-hidden">
      {/* Background clips */}
      <div className="absolute inset-0 -z-10">
        {heroClips.map((c, i) => (
          <ClipLayer
            key={c.id}
            clip={c}
            durationMs={c.durationMs ?? HERO_CLIP_DURATION_MS}
            active={i === index}
            load={i === index || i === (index + 1) % heroClips.length}
            playing={playing}
            isMobile={isMobile}
            staticOnly={reduceMotion}
            priority={i === 0}
          />
        ))}
        {/* Grade every clip to the palette and keep text readable */}
        <div className="absolute inset-0 bg-[#0b2a1c]/35 mix-blend-multiply" />
        <div className="absolute inset-0 bg-gradient-to-b from-canvas/70 via-canvas/25 to-canvas" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_35%,rgb(8_18_14/0.55)_100%)]" />
      </div>

      {/* Headline */}
      <motion.div
        style={{ opacity: contentOpacity, y: contentY }}
        className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center px-4 pt-16 text-center sm:px-6"
      >
        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: EASE }}
          className="text-balance text-5xl font-semibold tracking-[-0.04em] text-ink sm:text-7xl"
        >
          Ask the planet{" "}
          <span className="bg-gradient-to-r from-accent-soft via-accent to-sun bg-clip-text text-transparent">
            anything.
          </span>
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.1, ease: EASE }}
          className="mt-5 max-w-xl text-pretty text-base leading-relaxed text-ink/80 sm:text-lg"
        >
          Storms, fires, floods, ice and air. Ask a question in plain English and get an answer
          with a chart, backed by decades of real measurements.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.2, ease: EASE }}
          className="mt-9 flex flex-wrap items-center justify-center gap-3"
        >
          <button
            onClick={() => ask()}
            className="rounded-full bg-sun px-6 py-3 text-sm font-medium text-canvas transition-colors hover:bg-sun-soft"
          >
            Start asking
          </button>
          <a
            href="#showcase"
            className="rounded-full border border-line-strong bg-canvas/40 px-6 py-3 text-sm text-ink backdrop-blur transition-colors hover:bg-canvas/70"
          >
            See it in action
          </a>
        </motion.div>
      </motion.div>

      {/* Caption for the current clip + clip progress */}
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 pb-7 sm:flex-row sm:items-end sm:justify-between sm:px-6">
        <div className="min-h-[3.25rem]" aria-live="polite">
          <AnimatePresence mode="wait">
            <motion.div
              key={clip.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.4, ease: EASE }}
              className="flex flex-col gap-1.5"
            >
              <span className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.14em]" style={{ color: hazardColors[clip.kind] }}>
                <span className="size-4">
                  <HazardIcon type={clip.kind} />
                </span>
                {clip.label}
                {clip.detail && <span className="normal-case tracking-normal text-ink-muted">· {clip.detail}</span>}
              </span>
              <button
                onClick={() => ask(clip.question)}
                className="group text-left text-sm text-ink/90 transition-colors hover:text-ink sm:text-base"
              >
                Ask: “{clip.question}”{" "}
                <span className="inline-block text-accent transition-transform group-hover:translate-x-0.5">→</span>
              </button>
            </motion.div>
          </AnimatePresence>
        </div>

        <div className="flex gap-1.5" role="tablist" aria-label="Background clips">
          {heroClips.map((c, i) => (
            <button
              key={c.id}
              role="tab"
              aria-selected={i === index}
              aria-label={c.label}
              onClick={() => setIndex(i)}
              className="group py-2"
            >
              <span className="block h-0.5 w-10 overflow-hidden rounded-full bg-ink/20 transition-colors group-hover:bg-ink/35 sm:w-12">
                <ProgressFill state={i < index ? "done" : i === index ? "active" : "todo"} progress={progress} />
              </span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function ProgressFill({ state, progress }: { state: "done" | "active" | "todo"; progress: MotionValue<number> }) {
  if (state === "active") {
    return <motion.span className="block h-full origin-left bg-ink" style={{ scaleX: progress }} />;
  }
  return <span className="block h-full origin-left bg-ink" style={{ transform: `scaleX(${state === "done" ? 1 : 0})` }} />;
}

function usePageVisible() {
  return useSyncExternalStore(
    (onChange) => {
      document.addEventListener("visibilitychange", onChange);
      return () => document.removeEventListener("visibilitychange", onChange);
    },
    () => document.visibilityState === "visible",
    () => true,
  );
}

function useIsMobile() {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia("(max-width: 640px)");
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    () => window.matchMedia("(max-width: 640px)").matches,
    () => false,
  );
}
