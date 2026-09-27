// Response shapes of the backend's POST /ask (backend/ask/pipeline.py on the snowflake branch).
// Keep these in sync with that file; fields the UI doesn't read are left loosely typed.

export type ChartPoint = {
  time: string;
  value: number | null;
  source?: string | null;
  /** Forecast answers: true for forecast days, false for the observed days drawn before them. */
  forecast?: boolean;
  /** Uncertainty band (ensemble / past-years 10th-90th percentile, or 80% interval). Null when the method has none. */
  lo?: number | null;
  hi?: number | null;
  /** ecmwf_ensemble | gfs_ensemble | cams | glofas | climatology | climate_projection | trend */
  method?: string;
};

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
/** A place people can open to review an answer's data (backend/shared/source_links.py). */
export type SourceLink = {
  name: string;
  /** The agency's public page for the dataset (or the cited web page). */
  url: string | null;
  /** What was pulled, e.g. "NSIDC Sea Ice Index v4 daily extent, 1978 ->". */
  detail: string | null;
  /** The exact request Ecuery made, credentials stripped. */
  data_url: string | null;
  /** True when the answer recorded no sources, so this is the metric's usual source. */
  usual: boolean;
};

type AnswerBase = ConversationFields & {
  status: "answered";
  /** Links to review the data behind the answer; added by /ask, /ask/voice and /voice/converse. */
  source_links?: SourceLink[];
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
  /** Grounding check: every number, date and rating in answer_text matched against the data Gemini was given. */
  fact_check?: { ok: boolean; checked: number; unsupported: string[]; retried?: boolean };
  grounding?: { ok: boolean; label: string };
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

/** The future: forecasts, outlooks and projections (backend/ask/forecast_answer.py). */
export type ForecastAnswer = AnswerBase & {
  kind: "forecast";
  plan: Plan;
  data: {
    metric: string;
    location: string;
    unit: string;
    granularity: string;
    summary: { avg: number; min: number; max: number; range_lo: number | null; range_hi: number | null } | null;
    methods: string[];
    method_labels: string[];
  }[];
  /** Fingerprints of the forecast-model responses (committed to by the answer's Solana record). */
  forecast_sources?: { source: string; dataset: string; url: string; sha256: string; fetched_at: string }[];
};

/** Chance of disaster events in an upcoming window, from recent history (backend/ask/events_answer.py). */
export type LikelihoodAnswer = AnswerBase & {
  kind: "likelihood";
  plan: EventsPlan;
  likelihood: {
    probability_pct: number;
    /** Human wording that never rounds to certainty: "more than 99%", "12%", "less than 1%". */
    probability_text: string;
    expected_count: number;
    windows_with_events: number;
    windows_total: number;
    history: { label: string; value: number; start: string }[];
  };
};

/** Topics with no dataset: a cited answer from web pages, every quote checked against the page text (backend/ask/web_answer.py). */
export type WebSource = { url: string; title: string; site: string; text_sha256: string; fetched_at: string };
export type WebAnswer = Omit<AnswerBase, "chart"> & {
  kind: "web";
  chart?: undefined;
  plan: { source: "web"; topic: string };
  web: {
    topic: string;
    sources: WebSource[];
    /** Each fact in the answer with the exact words from web.sources[source] that support it. */
    quotes: { statement: string; quote: string; source: number }[];
  };
};

export type AnsweredResponse = ReadingsAnswer | EventsAnswer | ForecastAnswer | LikelihoodAnswer | WebAnswer;

export const isEventsAnswer = (a: AnsweredResponse): a is EventsAnswer => a.kind === "events";
export const isForecastAnswer = (a: AnsweredResponse): a is ForecastAnswer => a.kind === "forecast";
export const isLikelihoodAnswer = (a: AnsweredResponse): a is LikelihoodAnswer => a.kind === "likelihood";
export const isWebAnswer = (a: AnsweredResponse): a is WebAnswer => a.kind === "web";
/** Answers whose plan is an event search (a place + radius), past or upcoming. */
export const hasEventsPlan = (a: AnsweredResponse): a is EventsAnswer | LikelihoodAnswer =>
  a.kind === "events" || a.kind === "likelihood";

export type ClarificationResponse = ConversationFields & {
  status: "needs_clarification";
  clarification: string;
};

export type AskResponse = AnsweredResponse | ClarificationResponse;

/** One Research Assistant turn: POST /voice/converse (backend/voice/assistant.py). */
export type ConverseResponse = {
  status: "answered" | "needs_clarification";
  conversation_id: string;
  /** What the backend heard. Empty when there was no intelligible speech. */
  transcript: string;
  /** Short conversational reply, written to be spoken. */
  reply: string;
  /** Relative to the backend, e.g. "/voice/speak?text=…&voice=rachel". */
  speech_url: string;
  /** The full answer card, when the question was answered. */
  answer: AnsweredResponse | null;
};

export type VoiceOption = { key: string; name: string; description: string };
export type VoicesResponse = { mode: "elevenlabs" | "mock" | string; default: string; voices: VoiceOption[] };
