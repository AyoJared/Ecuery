"use client";

import { useInView } from "motion/react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { GlobeErrorBoundary } from "@/components/globe/GlobeErrorBoundary";
import type { EventMapPoint } from "@/lib/api/types";
import { eventTypeKind, eventTypeLabel } from "@/lib/event-types";
import type { EnvEvent } from "@/lib/events";

const EarthGlobe = dynamic(() => import("@/components/globe/EarthGlobe").then((m) => m.EarthGlobe), {
  ssr: false,
  loading: () => <div className="aspect-square w-full animate-pulse rounded-full bg-surface/60" />,
});

// Enough to show the pattern without hundreds of DOM markers (points arrive sorted by magnitude).
const MAX_MARKERS = 60;

/** Stable key shared by globe markers and list rows (map points carry no id). */
export const eventKey = (e: { name: string; date: string }) => `${e.name}|${e.date}`;

type EventGlobeProps = {
  points: EventMapPoint[];
  center: { lat: number; lon: number } | null;
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
};

// The landing page's globe, reused to plot an answer's events.
export function EventGlobe({ points, center, selectedKey, onSelect }: EventGlobeProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState(0);
  const onScreen = useInView(boxRef, { margin: "200px" });

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setSize(el.offsetWidth));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Memoized: the globe re-flies to the selection whenever this array's identity changes.
  const events: EnvEvent[] = useMemo(
    () =>
      points.slice(0, MAX_MARKERS).map((p) => ({
        id: eventKey(p),
        type: eventTypeKind(p.type),
        name: p.name,
        place: p.region ?? eventTypeLabel(p.type),
        date: p.date,
        lat: p.lat,
        lng: p.lon,
        stat: p.strength ?? "",
        summary: "",
        question: "",
      })),
    [points],
  );

  // Start over the searched place, or over the first (strongest) event for worldwide searches.
  const focus = center ?? (points[0] ? { lat: points[0].lat, lon: points[0].lon } : { lat: 20, lon: 0 });

  return (
    <div
      ref={boxRef}
      className="relative mx-auto aspect-square w-full max-w-[440px] cursor-grab active:cursor-grabbing"
    >
      {size > 0 && (
        <GlobeErrorBoundary>
          <EarthGlobe
            events={events}
            selectedId={selectedKey}
            onSelect={onSelect}
            size={size}
            paused={!onScreen}
            homeView={{ lat: focus.lat, lng: focus.lon, altitude: center ? 1.6 : 2.1 }}
          />
        </GlobeErrorBoundary>
      )}
    </div>
  );
}
