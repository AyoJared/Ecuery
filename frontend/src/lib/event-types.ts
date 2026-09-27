import type { EventType } from "./events";

// Backend event types (backend/ingest/events.py EVENT_TYPES) → display label and the closest of our
// six globe/icon categories. The label always shows the real type; the category only picks the icon.
const BACKEND_EVENT_TYPES: Record<string, { label: string; kind: EventType }> = {
  tornado: { label: "Tornado", kind: "tornado" },
  hurricane: { label: "Hurricane / tropical storm", kind: "cyclone" },
  severe_storm: { label: "Severe storm", kind: "cyclone" },
  thunderstorm_wind: { label: "Damaging thunderstorm wind", kind: "cyclone" },
  hail: { label: "Hail", kind: "cyclone" },
  winter_storm: { label: "Winter storm", kind: "cyclone" },
  flood: { label: "Flood", kind: "flood" },
  landslide: { label: "Landslide", kind: "flood" },
  earthquake: { label: "Earthquake", kind: "earthquake" },
  volcano: { label: "Volcanic eruption", kind: "earthquake" },
  wildfire: { label: "Wildfire", kind: "wildfire" },
  heat: { label: "Extreme heat", kind: "wildfire" },
  drought: { label: "Drought", kind: "wildfire" },
};

export const eventTypeLabel = (type: string) =>
  BACKEND_EVENT_TYPES[type]?.label ?? type.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const eventTypeKind = (type: string): EventType => BACKEND_EVENT_TYPES[type]?.kind ?? "cyclone";
