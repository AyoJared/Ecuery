"use client";

import { useRef, useState } from "react";
import { HazardIcon } from "@/components/globe/HazardIcon";
import type { EventView, EventsAnswer } from "@/lib/api/types";
import { eventTypeKind, eventTypeLabel } from "@/lib/event-types";
import { formatDate } from "@/lib/format";
import { hazardColors } from "@/lib/hazard-icons";
import { EventGlobe, eventKey } from "./EventGlobe";

const compactUsd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
});
const whole = new Intl.NumberFormat("en-US");

/** Counts, a globe of where things happened, and the biggest events. Compact = no globe, top 3 only. */
export function EventsPanel({ answer, compact = false }: { answer: EventsAnswer; compact?: boolean }) {
  const { events, map } = answer;
  const [selected, setSelected] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const rowRefs = useRef(new Map<string, HTMLElement>());

  function selectFromGlobe(key: string | null) {
    setSelected(key);
    if (key) rowRefs.current.get(key)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  const stats = [
    { label: events.count === 1 ? "Event" : "Events", value: whole.format(events.count), always: true },
    { label: "Deaths", value: whole.format(events.deaths), always: false, show: events.deaths > 0 },
    { label: "Injuries", value: whole.format(events.injuries), always: false, show: events.injuries > 0 },
    {
      label: "Damage",
      value: compactUsd.format(events.damage_usd),
      always: false,
      show: events.damage_usd > 0,
    },
    {
      label: "Strongest",
      value: events.biggest[0]?.strength ?? "",
      always: false,
      show: !!events.biggest[0]?.strength,
    },
  ]
    .filter((s) => s.always || s.show)
    .slice(0, 4);

  const listed = compact ? events.biggest.slice(0, 3) : showAll ? events.biggest : events.biggest.slice(0, 6);
  const types = Object.entries(events.by_type).sort((a, b) => b[1] - a[1]);

  return (
    <section className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="rounded-2xl border border-line bg-surface/40 px-4 py-3">
            <p className="text-2xl font-semibold tracking-tight text-ink tabular-nums">{s.value}</p>
            <p className="text-xs text-ink-faint">{s.label}</p>
          </div>
        ))}
      </div>

      {types.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {types.map(([type, n]) => (
            <span
              key={type}
              className="flex items-center gap-2 rounded-full border border-line-strong bg-surface-raised px-3 py-1.5 text-sm"
            >
              <span className="size-4" style={{ color: hazardColors[eventTypeKind(type)] }}>
                <HazardIcon type={eventTypeKind(type)} />
              </span>
              <span className="text-ink">{eventTypeLabel(type)}</span>
              <span className="text-ink-faint tabular-nums">{whole.format(n)}</span>
            </span>
          ))}
        </div>
      )}

      <div className={compact ? "" : "grid items-start gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]"}>
        {!compact && map.points.length > 0 && (
          <div className="rounded-3xl border border-line bg-surface/40 p-4">
            <EventGlobe
              points={map.points}
              center={map.center}
              selectedKey={selected}
              onSelect={selectFromGlobe}
            />
            <p className="mt-2 text-center text-xs text-ink-faint">
              {map.radius_km
                ? `Search area: ${Math.round(map.radius_km)} km around ${answer.plan.place?.label}`
                : "Worldwide"}{" "}
              · click a marker
            </p>
          </div>
        )}

        {listed.length > 0 && (
          <div className="rounded-3xl border border-line bg-surface/40 p-2">
            <h3 className="px-3 pb-1 pt-3 text-xs font-medium uppercase tracking-[0.14em] text-ink-faint">
              {compact ? "Top events" : "Biggest events"}
            </h3>
            <ul>
              {listed.map((e) => (
                <EventRow
                  key={e.id}
                  event={e}
                  selected={selected === eventKey(e)}
                  onSelect={compact ? undefined : () => setSelected(eventKey(e))}
                  rowRef={(el) => {
                    if (el) rowRefs.current.set(eventKey(e), el);
                    else rowRefs.current.delete(eventKey(e));
                  }}
                />
              ))}
            </ul>
            {!compact && events.biggest.length > 6 && (
              <button
                onClick={() => setShowAll((s) => !s)}
                className="w-full rounded-xl px-3 py-2.5 text-left text-sm text-accent transition-colors hover:bg-surface-raised/50 hover:text-accent-soft"
              >
                {showAll ? "Show fewer" : `Show all ${events.biggest.length}`}
              </button>
            )}
          </div>
        )}
      </div>

      {events.nearest.length > 0 && (
        <div className="rounded-3xl border border-line bg-surface/40 p-2">
          <h3 className="px-3 pb-1 pt-3 text-xs font-medium uppercase tracking-[0.14em] text-ink-faint">
            Closest outside the search area
          </h3>
          <ul>
            {events.nearest.map((e) => (
              <EventRow key={e.id} event={e} selected={false} />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

type EventRowProps = {
  event: EventView;
  selected: boolean;
  onSelect?: () => void;
  rowRef?: (el: HTMLElement | null) => void;
};

function EventRow({ event: e, selected, onSelect, rowRef }: EventRowProps) {
  const kind = eventTypeKind(e.type);
  const details = [
    formatDate(e.date),
    e.region,
    e.distance_km != null ? `${Math.round(e.distance_km)} km away` : null,
    e.path_miles ? `${e.path_miles} mi path` : null,
    e.deaths ? `${e.deaths} deaths` : null,
  ].filter(Boolean);

  const body = (
    <>
      <span className="mt-0.5 size-5 shrink-0" style={{ color: hazardColors[kind] }}>
        <HazardIcon type={kind} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-ink">{e.name}</span>
        <span className="block truncate text-xs text-ink-faint">{details.join(" · ")}</span>
      </span>
      {e.strength && (
        <span className="shrink-0 rounded-full border border-line-strong px-2 py-0.5 font-mono text-xs text-ink">
          {e.strength}
        </span>
      )}
    </>
  );

  const className = `flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
    selected ? "bg-accent/10 ring-1 ring-accent/40" : onSelect ? "hover:bg-surface-raised/50" : ""
  }`;

  return (
    <li ref={rowRef}>
      {onSelect ? (
        <button onClick={onSelect} aria-pressed={selected} className={className}>
          {body}
        </button>
      ) : (
        <div className={className}>{body}</div>
      )}
    </li>
  );
}
