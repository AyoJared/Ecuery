// Response shapes of the backend's POST /ask (backend/ask/pipeline.py on the snowflake branch).
// Keep these in sync with that file; fields the UI doesn't read are left loosely typed.

export type ChartPoint = { time: string; value: number | null; source?: string | null };

export type ChartSeries = {
  name: string;
  unit: string;
  granularity: string;
  points: ChartPoint[];
};

export type ChartBar = { label: string; value: number; highlight?: boolean };

export type ChartSpec = {
  type: "line" | "bar";
  title: string;
  y_label: string;
  x_label?: string;
  series?: ChartSeries[];
  bars?: ChartBar[];
};

export type Understood = {
  intent?: string;
  metrics?: string[];
  locations?: string[];
  start_date?: string;
  end_date?: string;
  operation?: string;
};

export type PlanPlace = { label: string; kind: string; lat: number; lon: number };

export type Plan = {
  metrics: string[];
  locations: string[];
  start: string;
  end: string;
  operation: string;
  places: Record<string, PlanPlace>;
};

export type Provenance = {
  batch_id: string;
  source: string;
  dataset: string;
  quality: string;
  fetched_at: string;
  row_count: number;
  manifest_sha256: string;
  signature: string | null;
  explorer_url: string | null;
  anchored: boolean;
};

export type Verification = {
  hash: string;
  signature: string | null;
  explorer_url: string | null;
  /** "rpc" = a real Solana transaction; "mock" = simulated by the backend. */
  mode: "rpc" | "mock" | string;
  cluster: string;
  slot?: number;
  error?: string;
  badge: { verified: boolean; label: string };
  record: Record<string, unknown>;
};

type ConversationFields = {
  question: string;
  conversation_id: string;
  turn: number;
  understood: Understood;
  timings: Record<string, number>;
  /** Only present on /ask/voice responses. */
  transcript?: string;
};

/** Fields every answered response has, whichever kind of data it's about. */
type AnswerBase = ConversationFields & {
  status: "answered";
  answer_text: string;
  trends: string[];
  comparison: string | null;
  chart: ChartSpec;
  data_notes: string[];
  provenance: Provenance[];
  provenance_error?: string;
  verification: Verification;
  /** Relative to the backend, e.g. "/voice/speak?text=…&voice=rachel". */
  audio_url: string;
};

/** Measurements over time (PM2.5, temperature, CO₂…): backend/ask/pipeline.py. Has no `kind` field. */
export type ReadingsAnswer = AnswerBase & {
  kind?: "readings";
  plan: Plan;
  data: { metric: string; location: string; unit: string; warnings: string[]; summary: Record<string, number> | null }[];
};

/** Disasters and events (tornadoes, earthquakes…): backend/ask/events_answer.py. */
export type EventsPlan = {
  event_types: string[];
  start: string;
  end: string;
  operation: string;
  place: { key: string; label: string; lat: number; lon: number } | null;
  radius_km: number | null;
  min_magnitude: number | null;
  sources: string[];
  /** Set when the search is limited to a state/country's borders instead of a radius. */
  within: string | null;
};

export type EventView = {
  id: string;
  type: string;
  name: string;
  date: string;
  /** Human label: "EF2", "M7.4"… */
  strength: string | null;
  magnitude: number | null;
  region: string | null;
  distance_km: number | null;
  deaths: number | null;
  injuries: number | null;
  damage_usd: number | null;
  path_miles: number | null;
  lat: number | null;
  lon: number | null;
  source: string;
  batch_id: string | null;
};

export type EventMapPoint = Pick<EventView, "type" | "name" | "date" | "strength" | "region"> & { lat: number; lon: number };

export type EventsAnswer = AnswerBase & {
  kind: "events";
  plan: EventsPlan;
  events: {
    count: number;
    by_type: Record<string, number>;
    deaths: number;
    injuries: number;
    damage_usd: number;
    biggest: EventView[];
    /** The closest events just outside the search area, when few or none were inside it. */
    nearest: EventView[];
  };
  map: { center: { lat: number; lon: number } | null; radius_km: number | null; points: EventMapPoint[] };
};

export type AnsweredResponse = ReadingsAnswer | EventsAnswer;

export const isEventsAnswer = (a: AnsweredResponse): a is EventsAnswer => a.kind === "events";

export type ClarificationResponse = ConversationFields & {
  status: "needs_clarification";
  clarification: string;
};

export type AskResponse = AnsweredResponse | ClarificationResponse;
