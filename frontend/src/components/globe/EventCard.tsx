"use client";

import { AnimatePresence, motion } from "motion/react";
import { eventTypes, type EnvEvent } from "@/lib/events";
import { HazardIcon } from "./HazardIcon";

type EventCardProps = {
  event: EnvEvent | null;
  onPrev: () => void;
  onNext: () => void;
  onAsk: (question: string) => void;
};

export function EventCard({ event, onPrev, onNext, onAsk }: EventCardProps) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-line bg-surface/80 p-5 backdrop-blur sm:p-6">
      <AnimatePresence mode="wait" initial={false}>
        {event ? (
          <motion.div
            key={event.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.25 }}
            className="flex h-full flex-col gap-3"
          >
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2 text-xs font-medium" style={{ color: eventTypes[event.type].color }}>
                <span className="size-4">
                  <HazardIcon type={event.type} south={event.lat < 0} />
                </span>
                {eventTypes[event.type].singular}
              </span>
              <span className="text-xs text-ink-faint">{event.date}</span>
            </div>
            <div>
              <h3 className="text-xl font-semibold tracking-tight text-ink">{event.name}</h3>
              <p className="text-sm text-ink-muted">{event.place}</p>
            </div>
            <p className="font-mono text-sm text-ink">{event.stat}</p>
            <p className="text-sm leading-relaxed text-ink-muted">{event.summary}</p>
            <div className="mt-auto flex items-center justify-between gap-3 pt-2">
              <button
                onClick={() => onAsk(event.question)}
                className="group inline-flex items-center gap-1.5 text-left text-sm text-accent transition-colors hover:text-accent-soft"
              >
                Ask: “{event.question}”
                <span className="transition-transform group-hover:translate-x-0.5">→</span>
              </button>
              <div className="flex shrink-0 gap-1">
                <NavButton label="Previous event" onClick={onPrev} d="m15 18-6-6 6-6" />
                <NavButton label="Next event" onClick={onNext} d="m9 18 6-6-6-6" />
              </div>
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-start gap-3"
          >
            <p className="text-sm text-ink-muted">Drag to spin. Click a pulsing marker to see what happened there.</p>
            <button
              onClick={onNext}
              className="rounded-full border border-line-strong px-4 py-1.5 text-sm text-ink transition-colors hover:bg-surface-raised"
            >
              Browse events →
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function NavButton({ label, onClick, d }: { label: string; onClick: () => void; d: string }) {
  return (
    <button
      aria-label={label}
      onClick={onClick}
      className="grid size-8 place-items-center rounded-lg border border-line text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
    >
      <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d={d} />
      </svg>
    </button>
  );
}
