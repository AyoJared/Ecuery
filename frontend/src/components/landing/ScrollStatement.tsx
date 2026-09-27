"use client";

import { motion, useReducedMotion, useScroll, type MotionValue } from "motion/react";
import { useRef } from "react";
import { useClampedTransform } from "@/lib/use-clamped-transform";

type Tone = "sun" | "leaf";
type Segment = { text: string; tone?: Tone };

// The sentence, split into runs; toned runs light up in color instead of white.
const statement: Segment[] = [
  { text: "The planet is" },
  { text: "changing faster", tone: "sun" },
  { text: "than any dashboard can explain. Ecuery turns the world's environmental data into" },
  { text: "answers anyone can understand.", tone: "leaf" },
];

const toneClass: Record<Tone | "base", string> = {
  base: "text-ink",
  sun: "text-sun",
  leaf: "text-accent",
};

const words = statement.flatMap((segment) =>
  segment.text.split(" ").map((word) => ({ word, tone: segment.tone })),
);

// A sentence that pins in place and lights up word by word as you scroll through it.
export function ScrollStatement() {
  const ref = useRef<HTMLElement>(null);
  const reduceMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });

  return (
    <section id="why" ref={ref} className="relative h-[220vh]" aria-label="Why Ecuery">
      <div className="sticky top-0 flex h-[100svh] items-center">
        <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
          <p className="mb-8 text-xs font-medium uppercase tracking-[0.16em] text-accent">Why Ecuery</p>
          <p className="text-balance text-3xl font-semibold leading-[1.15] tracking-[-0.03em] sm:text-5xl lg:text-6xl">
            {words.map(({ word, tone }, i) => (
              <Word
                key={i}
                word={word}
                className={toneClass[tone ?? "base"]}
                progress={scrollYProgress}
                // Leave the last 15% of the scroll fully lit before the section releases.
                range={[(i / words.length) * 0.85, ((i + 1) / words.length) * 0.85]}
                lit={Boolean(reduceMotion)}
              />
            ))}
          </p>
        </div>
      </div>
    </section>
  );
}

type WordProps = {
  word: string;
  className: string;
  progress: MotionValue<number>;
  range: [number, number];
  lit: boolean;
};

function Word({ word, className, progress, range, lit }: WordProps) {
  const opacity = useClampedTransform(progress, range, [0.14, 1]);
  return (
    <>
      <motion.span className={className} style={{ opacity: lit ? 1 : opacity }}>
        {word}
      </motion.span>{" "}
    </>
  );
}
