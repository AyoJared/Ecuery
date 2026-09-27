// Demo-mode answers in the exact shape of the backend's POST /ask, used until the backend is
// connected (NEXT_PUBLIC_API_MODE=live). Values are rounded sample figures, and the UI labels them
// as sample answers: they are NOT answers to the user's actual question.

import type { AnsweredResponse, AskResponse, ClarificationResponse, EventView, EventsAnswer, ReadingsAnswer } from "./types";

const conversations = new Map<string, number>();

function sleep(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });
}

const fakeHash = (seed: string) =>
  Array.from({ length: 64 }, (_, i) => "0123456789abcdef"[(seed.charCodeAt(i % seed.length) * (i + 7)) % 16]).join("");

function verification(question: string): AnsweredResponse["verification"] {
  return {
    hash: fakeHash(question),
    signature: null,
    explorer_url: null,
    mode: "mock",
    cluster: "devnet",
    badge: { verified: true, label: "Verified (simulated)" },
    record: {},
  };
}

type Generated = "question" | "conversation_id" | "turn" | "verification" | "audio_url" | "timings";
type Fixture = Omit<ReadingsAnswer, Generated> | Omit<EventsAnswer, Generated>;

const nycSmoke: Fixture = {
  status: "answered",
  understood: { intent: "lookup", metrics: ["pm25"], locations: ["New York"], start_date: "2023-06-01", end_date: "2023-06-14", operation: "summary" },
  plan: {
    metrics: ["pm25"],
    locations: ["new_york"],
    start: "2023-06-01T00:00:00+00:00",
    end: "2023-06-15T00:00:00+00:00",
    operation: "summary",
    places: { new_york: { label: "New York, NY", kind: "measured", lat: 40.71, lon: -74.01 } },
  },
  answer_text:
    "PM2.5 in New York spiked during the Canadian wildfire smoke, reaching a daily average of about 118 µg/m³ on June 7, 2023, far above the 55 µg/m³ level that is unhealthy for everyone. Levels fell back under 15 µg/m³ by June 10.",
  trends: [
    "Air was clean (under 12 µg/m³) until June 5, then rose sharply as smoke arrived.",
    "The spike lasted about three days before rain and shifting winds cleared it.",
  ],
  comparison: "The June 7 peak was roughly ten times the city's typical June average.",
  chart: {
    type: "line",
    title: "Daily PM2.5 in New York, June 1–14, 2023",
    y_label: "PM2.5 (µg/m³)",
    x_label: "Time",
    series: [
      {
        name: "PM2.5 · New York",
        unit: "µg/m³",
        granularity: "daily",
        points: [8, 9, 7, 10, 18, 62, 118, 71, 24, 12, 9, 8, 10, 9].map((value, i) => ({
          time: `2023-06-${String(i + 1).padStart(2, "0")}T00:00:00+00:00`,
          value,
          source: "EPA AirNow",
        })),
      },
    ],
  },
  data: [{ metric: "pm25", location: "new_york", unit: "µg/m³", warnings: [], summary: { avg: 26.7, max: 118, min: 7 } }],
  data_notes: ["New York air quality averages the city's EPA monitors (EPA)."],
  provenance: [
    {
      batch_id: "epa-airnow-2023-06",
      source: "EPA",
      dataset: "AirNow daily PM2.5",
      quality: "final",
      fetched_at: "2026-09-20T12:00:00+00:00",
      row_count: 14,
      manifest_sha256: fakeHash("epa-airnow-2023-06"),
      signature: null,
      explorer_url: null,
      anchored: true,
    },
  ],
};

const phoenixHeat: Fixture = {
  status: "answered",
  understood: { intent: "compare", metrics: ["temperature"], locations: ["Phoenix"], operation: "compare_history" },
  plan: {
    metrics: ["temperature"],
    locations: ["phoenix"],
    start: "2026-09-19T00:00:00+00:00",
    end: "2026-09-26T00:00:00+00:00",
    operation: "compare_history",
    places: { phoenix: { label: "Phoenix, AZ", kind: "measured", lat: 33.45, lon: -112.07 } },
  },
  answer_text:
    "Last week in Phoenix averaged 37.0 °C, about 2.2 °C warmer than the same week over the previous five years (34.8 °C). It was the warmest version of that week in the record shown here.",
  trends: ["The same week has warmed on average since 2021.", "2023 was the previous warmest at 36.2 °C."],
  comparison: "2.2 °C warmer than the 2021–2025 average for the same week.",
  chart: {
    type: "bar",
    title: "Average temperature for the same week, Phoenix",
    y_label: "Temperature (°C)",
    x_label: "Year",
    bars: [
      { label: "2021", value: 33.4 },
      { label: "2022", value: 34.1 },
      { label: "2023", value: 36.2 },
      { label: "2024", value: 35.3 },
      { label: "2025", value: 34.9 },
      { label: "2026 (selected period)", value: 37, highlight: true },
    ],
  },
  data: [{ metric: "temperature", location: "phoenix", unit: "°C", warnings: [], summary: { avg: 37, max: 43.1, min: 29.8 } }],
  data_notes: ["Phoenix weather is from the Phoenix Sky Harbor station (NOAA)."],
  provenance: [
    {
      batch_id: "noaa-ghcnd-phx",
      source: "NOAA",
      dataset: "GHCN-Daily, Phoenix Sky Harbor",
      quality: "preliminary",
      fetched_at: "2026-09-26T06:00:00+00:00",
      row_count: 42,
      manifest_sha256: fakeHash("noaa-ghcnd-phx"),
      signature: null,
      explorer_url: null,
      anchored: true,
    },
  ],
};

const co2: Fixture = {
  status: "answered",
  understood: { intent: "trend", metrics: ["co2"], locations: ["global"], start_date: "2024-01-01", end_date: "2024-12-31", operation: "summary" },
  plan: {
    metrics: ["co2"],
    locations: ["global"],
    start: "2024-01-01T00:00:00+00:00",
    end: "2025-01-01T00:00:00+00:00",
    operation: "summary",
    places: { global: { label: "Global (Mauna Loa)", kind: "global", lat: 19.54, lon: -155.58 } },
  },
  answer_text:
    "Atmospheric CO₂ averaged about 424.6 ppm in 2024, peaking near 427 ppm in May and dipping to about 421.5 ppm in September as Northern Hemisphere plants took up carbon. This is the global background level measured at Mauna Loa, Hawaii.",
  trends: ["CO₂ follows a yearly cycle: highest in late spring, lowest in early autumn.", "Each year's cycle sits higher than the last."],
  comparison: null,
  chart: {
    type: "line",
    title: "Monthly CO₂ at Mauna Loa, 2024",
    y_label: "CO₂ (ppm)",
    x_label: "Time",
    series: [
      {
        name: "CO₂ · Global",
        unit: "ppm",
        granularity: "monthly",
        points: [422.8, 424.6, 425.4, 426.6, 426.9, 426.9, 425.6, 422.9, 421.5, 422.0, 423.5, 425.4].map((value, i) => ({
          time: `2024-${String(i + 1).padStart(2, "0")}-01T00:00:00+00:00`,
          value,
          source: "NOAA GML",
        })),
      },
    ],
  },
  data: [{ metric: "co2", location: "global", unit: "ppm", warnings: [], summary: { avg: 424.6, max: 426.9, min: 421.5 } }],
  data_notes: ["CO₂ is the global background level measured at Mauna Loa, Hawaii (NOAA GML); it is not city-specific."],
  provenance: [
    {
      batch_id: "noaa-gml-mlo-2024",
      source: "NOAA",
      dataset: "GML Mauna Loa monthly CO₂",
      quality: "final",
      fetched_at: "2026-09-18T09:30:00+00:00",
      row_count: 12,
      manifest_sha256: fakeHash("noaa-gml-mlo-2024"),
      signature: null,
      explorer_url: null,
      anchored: true,
    },
  ],
};

// Events answer (backend/ask/events_answer.py shape): M7+ earthquakes worldwide in 2024, rounded sample data.
const quake = (id: string, name: string, date: string, magnitude: number, lat: number, lon: number, region: string): EventView => ({
  id: `usgs-earthquakes:${id}`,
  type: "earthquake",
  name,
  date,
  strength: `M${magnitude.toFixed(1)}`,
  magnitude,
  region,
  distance_km: null,
  deaths: null,
  injuries: null,
  damage_usd: null,
  path_miles: null,
  lat,
  lon,
  source: "usgs-earthquakes",
  batch_id: "usgs-comcat-2024",
});

const quakes2024 = [
  quake("noto", "M 7.5 - Noto Peninsula, Japan", "2024-01-01", 7.5, 37.5, 137.2, "Japan"),
  quake("hualien", "M 7.4 - Hualien, Taiwan", "2024-04-02", 7.4, 23.8, 121.6, "Taiwan"),
  quake("antofagasta", "M 7.4 - Antofagasta, Chile", "2024-07-19", 7.4, -23.0, -67.9, "Chile"),
  quake("vanuatu", "M 7.3 - Port Vila, Vanuatu", "2024-12-17", 7.3, -17.7, 168.0, "Vanuatu"),
  quake("xinjiang", "M 7.0 - Southern Xinjiang, China", "2024-01-22", 7.0, 41.3, 78.6, "China"),
  quake("kamchatka", "M 7.0 - Kamchatka, Russia", "2024-08-17", 7.0, 52.9, 160.1, "Russia"),
  quake("mendocino", "M 7.0 - Cape Mendocino, California", "2024-12-05", 7.0, 40.3, -125.0, "United States"),
];

const bigQuakes: Omit<EventsAnswer, Generated> = {
  status: "answered",
  kind: "events",
  understood: { intent: "events", locations: [], start_date: "2024-01-01", end_date: "2024-12-31", operation: "summary" },
  plan: {
    event_types: ["earthquake"],
    start: "2024-01-01T00:00:00+00:00",
    end: "2025-01-01T00:00:00+00:00",
    operation: "summary",
    place: null,
    radius_km: null,
    min_magnitude: 7,
    sources: ["usgs-earthquakes"],
    within: null,
  },
  answer_text:
    "There were 10 earthquakes of magnitude 7.0 or stronger worldwide in 2024. The strongest was the M7.5 Noto Peninsula earthquake in Japan on January 1, followed by M7.4 quakes near Hualien, Taiwan on April 2 and Antofagasta, Chile on July 19.",
  trends: ["January and December were the busiest months, with two M7+ quakes each.", "Most were along the Pacific Ring of Fire."],
  comparison: null,
  chart: {
    type: "bar",
    title: "M7+ earthquakes per month, 2024",
    y_label: "Events",
    x_label: "",
    bars: [2, 0, 1, 1, 0, 1, 1, 1, 0, 0, 1, 2].map((value, i) => ({
      label: `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][i]} 2024`,
      value,
    })),
  },
  events: { count: 10, by_type: { earthquake: 10 }, deaths: 0, injuries: 0, damage_usd: 0, biggest: quakes2024, nearest: [] },
  map: {
    center: null,
    radius_km: null,
    points: quakes2024.map(({ lat, lon, type, name, date, strength, region }) => ({ lat: lat!, lon: lon!, type, name, date, strength, region })),
  },
  data_notes: ["Earthquakes are from the USGS ComCat catalog (worldwide, M2.5+)."],
  provenance: [
    {
      batch_id: "usgs-comcat-2024",
      source: "USGS",
      dataset: "ComCat earthquakes M2.5+ worldwide 2024",
      quality: "official",
      fetched_at: "2026-09-25T08:00:00+00:00",
      row_count: 10,
      manifest_sha256: fakeHash("usgs-comcat-2024"),
      signature: null,
      explorer_url: null,
      anchored: true,
    },
  ],
};

function pickFixture(question: string, turn: number): Fixture {
  const q = question.toLowerCase();
  if (/earthquake|quake|tornado|hurricane|disaster|storms?\b|events?\b|volcan/.test(q)) return bigQuakes;
  if (/co2|co₂|carbon|mauna/.test(q)) return co2;
  if (/hot|heat|warm|temperature|usual|normal|compare|past years|history/.test(q)) return phoenixHeat;
  if (/air|aqi|pm|smoke|pollut|wildfire/.test(q)) return nycSmoke;
  return [nycSmoke, phoenixHeat, co2][turn % 3];
}

export async function mockAsk(question: string, conversationId: string | null, signal?: AbortSignal): Promise<AskResponse> {
  const id = conversationId ?? `demo-${Math.random().toString(36).slice(2, 10)}`;
  const turn = (conversations.get(id) ?? 0) + 1;
  conversations.set(id, turn);
  const followUp = turn > 1;
  await sleep(followUp ? 1400 + Math.random() * 600 : 2600 + Math.random() * 900, signal);

  const base = { question, conversation_id: id, turn, timings: { understand: 0.6, fetch: 0.9, analyze: 1.1, verify: 0.4 } };

  if (question.trim().split(/\s+/).length < 3) {
    const reply: ClarificationResponse = {
      ...base,
      status: "needs_clarification",
      understood: {},
      clarification: "Which measurement and place do you mean? For example: “PM2.5 in Chicago last week”.",
    };
    return reply;
  }

  const fixture = pickFixture(question, turn);
  return {
    ...fixture,
    ...base,
    verification: verification(question + turn),
    audio_url: `/voice/speak?text=${encodeURIComponent(fixture.answer_text)}&voice=rachel`,
  } as AnsweredResponse;
}
