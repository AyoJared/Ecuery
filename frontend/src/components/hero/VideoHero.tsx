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
import { useClampedTransform } from "@/lib/use-clamped-transform";
import { usePageVisible } from "@/lib/use-page-visible";
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
  // Video clips are timed off their own playback (so buffering doesn't cut them short)
  // and end at min(video length, durationMs). Stills/placeholders use the wall clock.
  const videos = useRef(new Map<string, HTMLVideoElement>());
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
      const video = videos.current.get(clip.id);
      let total = durationMs;
      if (video) {
        elapsed.current = video.currentTime * 1000;
        if (video.duration) total = Math.min(durationMs, video.duration * 1000);
      } else {
        elapsed.current += now - last;
      }
      last = now;
      progress.set(Math.min(elapsed.current / total, 1));
      if (elapsed.current >= total || video?.ended) {
        setIndex((i) => (i + 1) % heroClips.length);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, clip.id, durationMs, progress]);

  // Content fades and lifts as the hero scrolls away.
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const contentOpacity = useClampedTransform(scrollYProgress, [0, 0.6], [1, 0]);
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
            registerVideo={(el) => {
              if (el) videos.current.set(c.id, el);
              else videos.current.delete(c.id);
            }}
          />
        ))}
        {/* Grade every clip to the palette and keep text readable */}
        <div className="absolute inset-0 bg-[#0b2a1c]/25 mix-blend-multiply" />
        <div className="absolute inset-0 bg-gradient-to-b from-canvas/45 via-transparent via-45% to-canvas" />
        {/* Soft scrim just behind the headline, so the rest of the footage can stay bright */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_50%_32%_at_50%_46%,rgb(8_18_14/0.5),transparent)]" />
      </div>

      {/* Headline */}
      <motion.div
        style={{ opacity: contentOpacity, y: contentY }}
        className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center px-4 pt-16 text-center [text-shadow:0_1px_18px_rgb(8_18_14/0.55)] sm:px-6"
      >
        <h1 className="flex flex-col items-center text-ink">
          <motion.span
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, ease: EASE }}
            className="text-balance text-3xl font-medium tracking-[-0.03em] text-ink/90 sm:text-5xl"
          >
            Curious about{" "}
            <span className="font-serif text-[1.18em] font-normal italic tracking-normal text-sun-soft">
              your planet?
            </span>
          </motion.span>
          <motion.span
            initial={{ opacity: 0, y: 24, filter: "blur(10px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 1.1, delay: 0.25, ease: EASE }}
            // The gradient text can't take a text-shadow, so it gets a drop-shadow filter instead.
            className="text-flow mt-1 pb-2 text-7xl font-semibold leading-none tracking-[-0.055em] [text-shadow:none] drop-shadow-[0_2px_18px_rgb(8_18_14/0.55)] sm:text-8xl lg:text-9xl"
          >
            Just ask.
          </motion.span>
        </h1>
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.45, ease: EASE }}
          className="mt-5 max-w-xl text-pretty text-base leading-relaxed text-ink/80 sm:text-lg"
        >
          Storms, fires, floods, quakes, ice and air. Ask a question in plain English and get an answer
          with a chart, backed by decades of real measurements.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.55, ease: EASE }}
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
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 pb-7 [text-shadow:0_1px_12px_rgb(8_18_14/0.7)] sm:flex-row sm:items-end sm:justify-between sm:px-6">
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
