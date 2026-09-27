"use client";

import { animate, motion, useInView, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { useEffect, useRef } from "react";
import { Reveal } from "@/components/motion/Reveal";
import { useSearch } from "@/components/search/SearchContext";
import { SectionHeading } from "./SectionHeading";

type Stat = {
  value: number;
  decimals?: number;
  unit: string;
  label: string;
  source: string;
  question: string;
};

// Rounded, widely published figures. Keep these to real measurements, not product metrics.
const stats: Stat[] = [
  {
    value: 424,
    unit: "ppm",
    label: "CO₂ in the air in 2024, up from about 280 before the industrial era.",
    source: "NOAA",
    question: "How has CO₂ at Mauna Loa changed since 1960?",
  },
  {
    value: 1.5,
    decimals: 1,
    unit: "°C+",
    label: "2024 was the first calendar year more than 1.5 °C warmer than pre-industrial times.",
    source: "Copernicus",
    question: "How much has global temperature risen since 1850?",
  },
  {
    value: 10,
    unit: "cm",
    label: "Global sea-level rise since satellite records began in 1993.",
    source: "NASA",
    question: "How fast is global sea level rising?",
  },
  {
    value: 17,
    unit: "M ha",
    label: "Burned in Canada's record-breaking 2023 wildfire season.",
    source: "CIFFC",
    question: "Compare 2023 vs 2024 wildfire acreage in Canada",
  },
];

export function StatsBand() {
  const { ask } = useSearch();
  const reduceMotion = Boolean(useReducedMotion());

  return (
    <section id="numbers" className="relative scroll-mt-16 py-24 sm:py-32">
      <div className="mx-auto flex max-w-6xl flex-col gap-14 px-4 sm:px-6">
        <SectionHeading
          eyebrow="By the numbers"
          title="The planet is sending signals."
          description="A few of the measurements behind the questions people ask most."
        />

        <div className="grid grid-cols-1 border-t border-line sm:grid-cols-2 lg:grid-cols-4">
          {stats.map((stat, i) => (
            <Reveal
              key={stat.label}
              delay={i * 0.1}
              className="flex flex-col gap-4 border-b border-line py-8 sm:px-6 sm:[&:nth-child(odd)]:border-r lg:border-b-0 lg:border-r lg:first:pl-0 lg:last:border-r-0"
            >
              <p className="flex items-baseline gap-2 font-semibold tracking-[-0.05em] text-ink">
                <CountUp to={stat.value} decimals={stat.decimals ?? 0} instant={reduceMotion} />
                <span className="text-flow text-2xl tracking-[-0.02em] sm:text-3xl">{stat.unit}</span>
              </p>
              <p className="max-w-[16rem] text-pretty text-sm leading-relaxed text-ink-muted">{stat.label}</p>
              <div className="mt-auto flex items-center justify-between gap-3 pt-2 text-xs">
                <span className="text-ink-faint">Source: {stat.source}</span>
                <button
                  onClick={() => ask(stat.question)}
                  className="group text-accent transition-colors hover:text-accent-soft"
                  aria-label={`Ask: ${stat.question}`}
                >
                  Ask about this <span className="inline-block transition-transform group-hover:translate-x-0.5">→</span>
                </button>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

type CountUpProps = { to: number; decimals: number; instant: boolean };

// Counts from 0 to `to` the first time this number itself scrolls into view (so stacked cards
// on phones each count as they arrive). Tabular figures keep the width steady while counting.
function CountUp({ to, decimals, instant }: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.8 });
  const value = useMotionValue(instant ? to : 0);
  const text = useTransform(value, (v) => v.toFixed(decimals));

  useEffect(() => {
    if (!inView || instant) return;
    const controls = animate(value, to, { duration: 1.8, ease: [0.16, 1, 0.3, 1] });
    return () => controls.stop();
  }, [inView, instant, to, value]);

  return (
    <motion.span ref={ref} className="text-6xl tabular-nums sm:text-7xl">
      {text}
    </motion.span>
  );
}
