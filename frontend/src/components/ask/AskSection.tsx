"use client";

import { motion, useInView, useScroll } from "motion/react";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { EventCard } from "@/components/globe/EventCard";
import { GlobeErrorBoundary } from "@/components/globe/GlobeErrorBoundary";
import { HazardIcon } from "@/components/globe/HazardIcon";
import { SectionHeading } from "@/components/landing/SectionHeading";
import { Reveal } from "@/components/motion/Reveal";
import { useSearch } from "@/components/search/SearchContext";
import { SearchPanel } from "@/components/search/SearchPanel";
import { envEvents, eventTypes, type EventType } from "@/lib/events";
import { useClampedTransform } from "@/lib/use-clamped-transform";

const EarthGlobe = dynamic(() => import("@/components/globe/EarthGlobe").then((m) => m.EarthGlobe), {
  ssr: false,
  loading: () => <div className="aspect-square w-full animate-pulse rounded-full bg-surface/60" />,
});

const allTypes = Object.keys(eventTypes) as EventType[];

// Search on the left, the event globe on the right. Picking an event offers its question to the search bar.
export function AskSection() {
  const { ask } = useSearch();
  const [activeTypes, setActiveTypes] = useState<EventType[]>(allTypes);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const sectionRef = useRef<HTMLElement>(null);
  const globeBoxRef = useRef<HTMLDivElement>(null);
  const size = useElementWidth(globeBoxRef);
  const onScreen = useInView(sectionRef, { margin: "200px" });
  // Build the globe (WebGL shaders + hex-dot continents) only once the user scrolls toward it,
  // so its one-off setup cost doesn't stutter the hero. The section peeks in at load, hence the
  // negative bottom margin: it must reach the upper 75% of the viewport first.
  const nearby = useInView(sectionRef, { once: true, margin: "0px 0px -25% 0px" });

  // Globe grows into place as the section scrolls into view.
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ["start end", "start start"] });
  const globeScale = useClampedTransform(scrollYProgress, [0, 1], [0.85, 1]);
  const globeOpacity = useClampedTransform(scrollYProgress, [0, 0.5], [0, 1]);

  const visibleEvents = envEvents.filter((e) => activeTypes.includes(e.type));
  const selected = visibleEvents.find((e) => e.id === selectedId) ?? null;

  function toggleType(type: EventType) {
    const next = activeTypes.includes(type) ? activeTypes.filter((t) => t !== type) : [...activeTypes, type];
    if (next.length === 0) return;
    setActiveTypes(next);
    if (selected && !next.includes(selected.type)) setSelectedId(null);
  }

  function step(delta: number) {
    const index = visibleEvents.findIndex((e) => e.id === selectedId);
    const nextIndex = index === -1 ? 0 : (index + delta + visibleEvents.length) % visibleEvents.length;
    setSelectedId(visibleEvents[nextIndex].id);
  }

  return (
    <section id="ask" ref={sectionRef} className="relative isolate scroll-mt-16 py-20 sm:py-28">
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 sm:px-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-16">
        <div className="flex flex-col gap-8">
          <SectionHeading
            align="left"
            eyebrow="Ask"
            title="What do you want to know?"
            description="Type a question in plain English, or pick an event on the globe to start from."
          />
          <Reveal delay={0.1}>
            <SearchPanel align="left" />
          </Reveal>
        </div>

        <div className="flex flex-col gap-5">
          {/* Ambient ocean/leaf glow behind the globe; the section's isolate keeps -z-10 local */}
          <div className="relative">
            <div
              aria-hidden
              className="pointer-events-none absolute left-1/2 top-1/2 -z-10 aspect-square w-[120%] max-w-[700px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(closest-side,rgb(124_196_245/0.26),rgb(61_155_224/0.12)_55%,transparent)] blur-2xl animate-[breathe_7s_ease-in-out_infinite_alternate] motion-reduce:animate-none"
            />
            <motion.div
              ref={globeBoxRef}
              style={{ scale: globeScale, opacity: globeOpacity }}
              className="relative mx-auto aspect-square w-full max-w-[560px] cursor-grab active:cursor-grabbing"
            >
              <GlobeErrorBoundary>
                {size > 0 && nearby && (
                  <EarthGlobe
                    events={visibleEvents}
                    selectedId={selected?.id ?? null}
                    onSelect={setSelectedId}
                    size={size}
                    paused={!onScreen}
                  />
                )}
              </GlobeErrorBoundary>
            </motion.div>
          </div>

          <div className="flex flex-wrap justify-center gap-2">
            {allTypes.map((type) => {
              const active = activeTypes.includes(type);
              return (
                <button
                  key={type}
                  onClick={() => toggleType(type)}
                  aria-pressed={active}
                  className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors ${
                    active
                      ? "border-line-strong bg-surface-raised text-ink"
                      : "border-line text-ink-faint hover:text-ink-muted"
                  }`}
                >
                  <span
                    className="size-4 transition-opacity"
                    style={{ color: eventTypes[type].color, opacity: active ? 1 : 0.35 }}
                  >
                    <HazardIcon type={type} paused={!active} />
                  </span>
                  {eventTypes[type].label}
                </button>
              );
            })}
          </div>

          <EventCard event={selected} onPrev={() => step(-1)} onNext={() => step(1)} onAsk={ask} />
          <p className="text-center text-xs text-ink-faint">Historical events · figures approximate</p>
        </div>
      </div>
    </section>
  );
}

function useElementWidth(ref: React.RefObject<HTMLElement | null>) {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // offsetWidth ignores the CSS scale transform applied during the scroll-in.
    const observer = new ResizeObserver(() => setWidth(el.offsetWidth));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}
