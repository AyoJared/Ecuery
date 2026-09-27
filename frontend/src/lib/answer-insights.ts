// Turns a backend answer into what the results page leads with: one headline number, a few
// supporting stats, a context line, and reference lines for the chart. Pure functions, no React.

import {
  isEventsAnswer,
  isForecastAnswer,
  isLikelihoodAnswer,
  isWebAnswer,
  type AnsweredResponse,
  type EventsAnswer,
  type ForecastAnswer,
  type LikelihoodAnswer,
  type ReadingsAnswer,
  type WebAnswer,
} from "./api/types";
import { eventTypeLabel } from "./event-types";
import { formatDate, formatRange, metricLabel } from "./format";
import { palette } from "./palette";

export type Tone = "good" | "moderate" | "warn" | "bad" | "severe" | "hazard" | "warm" | "cool" | "neutral";

export const toneColor: Record<Tone, string> = {
  good: palette.good,
  moderate: "#facc15",
  warn: "#fb923c",
  bad: "#f87171",
  severe: "#c084fc",
  hazard: "#e11d48",
  warm: palette.sun,
  cool: palette.ocean,
  neutral: palette.inkMuted,
};

export type Stat = { label: string; value: string; hint?: string };

export type Insight = {
  /** "PM2.5 · New York, NY · Jun 1 – 14, 2023" */
  context: string[];
  headline: {
    value: string;
    unit?: string;
    label: string;
    badge?: { text: string; tone: Tone };
  };
  stats: Stat[];
  /** Horizontal reference lines for the chart (thresholds, usual level). */
  references: {
    y: number;
    label: string;
    color: string;
    /** Stretch the axis so the line is always visible. */ extend?: boolean;
  }[];
};

const num = (v: number, digits = 1) =>
  Math.abs(v) >= 1000
    ? new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(v)
    : Number.isInteger(v)
      ? String(v)
      : v.toFixed(digits);

const whole = new Intl.NumberFormat("en-US");
const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact" });

// EPA PM2.5 AQI categories (24-hour average, µg/m³; breakpoints revised in 2024).
const PM25_LEVELS: { max: number; text: string; tone: Tone }[] = [
  { max: 9.0, text: "Good", tone: "good" },
  { max: 35.4, text: "Moderate", tone: "moderate" },
  { max: 55.4, text: "Unhealthy for sensitive groups", tone: "warn" },
  { max: 125.4, text: "Unhealthy", tone: "bad" },
  { max: 225.4, text: "Very unhealthy", tone: "severe" },
  { max: Infinity, text: "Hazardous", tone: "hazard" },
];
export const pm25Level = (v: number) => PM25_LEVELS.find((l) => v <= l.max)!;

/** Metrics where a relative change (%) means something; for these a rise is bad news. */
const POLLUTANTS = new Set(["pm25", "o3", "no2", "co2"]);

export function insightFor(answer: AnsweredResponse): Insight {
  if (isEventsAnswer(answer)) return eventsInsight(answer);
  if (isForecastAnswer(answer)) return forecastInsight(answer);
  if (isLikelihoodAnswer(answer)) return likelihoodInsight(answer);
  if (isWebAnswer(answer)) return webInsight(answer);
  return readingsInsight(answer);
}

function forecastInsight(answer: ForecastAnswer): Insight {
  const { plan, data } = answer;
  const first = data.find((d) => d.summary);
  const place = first ? (plan.places[first.location]?.label ?? first.location) : "";
  const stats: Stat[] = [];
  if (first?.summary) {
    const { min, max, range_lo, range_hi } = first.summary;
    stats.push({ label: "Lowest", value: `${num(min)} ${first.unit}` }, { label: "Highest", value: `${num(max)} ${first.unit}` });
    if (range_lo != null && range_hi != null)
      stats.push({ label: "Likely range", value: `${num(range_lo)}–${num(range_hi)} ${first.unit}` });
  }
  return {
    context: [plan.metrics.map(metricLabel).join(", "), place, formatRange(plan.start, plan.end)],
    headline: first?.summary
      ? { value: num(first.summary.avg), unit: first.unit, label: `Forecast average · ${metricLabel(first.metric)} · ${place}` }
      : { value: "", label: "" },
    stats,
    references: [],
  };
}

function likelihoodInsight(answer: LikelihoodAnswer): Insight {
  const { plan, likelihood } = answer;
  const types = plan.event_types.map(eventTypeLabel);
  const where = plan.within ?? plan.place?.label ?? "Worldwide";
  return {
    context: [types.join(", "), where, formatRange(plan.start, plan.end)],
    headline: { value: likelihood.probability_text, label: `Chance of at least one · ${where}` },
    stats: [
      { label: "Expected count", value: num(likelihood.expected_count, 2) },
      { label: "Past windows with events", value: `${likelihood.windows_with_events} of ${likelihood.windows_total}` },
    ],
    references: [],
  };
}

function webInsight(answer: WebAnswer): Insight {
  const n = answer.web.sources.length;
  return {
    context: [answer.plan.topic, "Cited web sources"],
    headline: { value: "", label: "" },
    stats: [
      { label: "Sources", value: String(n) },
      { label: "Quotes checked", value: String(answer.web.quotes.length) },
    ],
    references: [],
  };
}

function readingsInsight(answer: ReadingsAnswer): Insight {
  const { plan, data, chart } = answer;
  const places = plan.locations.map((l) => plan.places[l]?.label ?? l);
  const context = [
    plan.metrics.map(metricLabel).join(", "),
    places.join(", "),
    formatRange(plan.start, plan.end),
  ];
  const series = data.filter((d) => d.summary);
  const first = series[0];
  const metric = first?.metric ?? plan.metrics[0];
  const unit = first?.unit ?? "";
  const references: Insight["references"] = [];
  if (metric === "pm25") {
    references.push({ y: 35.4, label: "Unhealthy for sensitive groups", color: toneColor.warn });
    references.push({ y: 55.4, label: "Unhealthy", color: toneColor.bad });
  }

  // "Compared with past years": selected period vs the same period in earlier years. Prefer the
  // backend's historical_baselines (sent whatever chart the AI picked); fall back to highlighted bars.
  const hist = answer.historical_baselines?.[0];
  const bars = chart.bars ?? [];
  const selectedBar = bars.find((b) => b.highlight);
  const past: { label: string; value: number }[] = hist
    ? hist.by_year.map((y) => ({ label: String(y.year), value: y.avg }))
    : bars.filter((b) => !b.highlight);
  const selectedValue = first?.summary?.avg ?? selectedBar?.value;
  if (plan.operation === "compare_history" && selectedValue != null && past.length) {
    const baseline = hist?.baseline_avg ?? past.reduce((a, b) => a + b.value, 0) / past.length;
    const diff = selectedValue - baseline;
    const relative = POLLUTANTS.has(metric) && baseline !== 0;
    const delta = relative
      ? `${diff >= 0 ? "+" : ""}${num((diff / baseline) * 100)}%`
      : `${diff >= 0 ? "+" : ""}${num(diff)} ${unit}`;
    const tone: Tone = POLLUTANTS.has(metric) ? (diff > 0 ? "bad" : "good") : diff > 0 ? "warm" : "cool";
    const highest = past.reduce((a, b) => (b.value > a.value ? b : a));
    const lowest = past.reduce((a, b) => (b.value < a.value ? b : a));
    // Always show the usual level, even if it's outside the chart's own range.
    references.push({
      y: baseline,
      label: `${past.length}-year average`,
      color: palette.inkMuted,
      extend: true,
    });
    return {
      context,
      headline: {
        value: num(selectedValue),
        unit,
        label: `Average ${metricLabel(metric).toLowerCase()} · ${places[0] ?? ""}`,
        badge: { text: `${delta} vs usual`, tone },
      },
      stats: [
        { label: `Usual (${past.length}-year average)`, value: `${num(baseline)} ${unit}` },
        {
          label: metric === "temperature" ? "Warmest year" : "Highest year",
          value: `${num(highest.value)} ${unit}`,
          hint: highest.label,
        },
        {
          label: metric === "temperature" ? "Coolest year" : "Lowest year",
          value: `${num(lowest.value)} ${unit}`,
          hint: lowest.label,
        },
      ],
      references,
    };
  }

  if (!first?.summary) {
    return { context, headline: { value: "–", label: "No data for this period" }, stats: [], references };
  }

  // Several places or metrics: headline the first, list each series' average.
  if (series.length > 1) {
    return {
      context,
      headline: {
        value: num(first.summary.avg),
        unit,
        label: `Average ${metricLabel(first.metric)} · ${plan.places[first.location]?.label ?? first.location}`,
      },
      stats: series.map((s) => ({
        label: `${metricLabel(s.metric)} · ${plan.places[s.location]?.label ?? s.location}`,
        value: `${num(s.summary!.avg)} ${s.unit}`,
      })),
      references,
    };
  }

  const s = first.summary;
  const level = metric === "pm25" ? pm25Level(s.avg) : null;
  return {
    context,
    headline: {
      value: num(s.avg),
      unit,
      label: `Average ${metricLabel(metric)}${places[0] ? ` · ${places[0]}` : ""}`,
      badge: level ? { text: level.text, tone: level.tone } : undefined,
    },
    stats: [
      {
        label: "Highest reading",
        value: `${num(s.max)} ${unit}`,
        hint: metric === "pm25" ? pm25Level(s.max).text : undefined,
      },
      { label: "Lowest reading", value: `${num(s.min)} ${unit}` },
      ...(s.latest != null
        ? [
            {
              label: "Latest",
              value: `${num(s.latest)} ${unit}`,
              hint: s.latest_time ? formatDate(String(s.latest_time)) : undefined,
            },
          ]
        : []),
    ],
    references,
  };
}

function eventsInsight(answer: EventsAnswer): Insight {
  const { plan, events } = answer;
  const types = plan.event_types.map(eventTypeLabel);
  const where = plan.within ?? plan.place?.label ?? "Worldwide";
  const noun = types.length === 1 ? types[0].toLowerCase() : "events";
  const plural = events.count === 1 ? noun : noun.endsWith("s") ? noun : `${noun}s`;
  const strongest = events.biggest[0];
  const stats: Stat[] = [];
  if (events.deaths > 0) stats.push({ label: "Deaths", value: whole.format(events.deaths) });
  if (events.injuries > 0) stats.push({ label: "Injuries", value: whole.format(events.injuries) });
  if (events.damage_usd > 0) stats.push({ label: "Damage", value: usd.format(events.damage_usd) });
  if (strongest?.strength)
    stats.push({ label: "Strongest", value: strongest.strength, hint: formatDate(strongest.date) });
  return {
    context: [types.join(", "), where, formatRange(plan.start, plan.end)],
    headline: {
      value: whole.format(events.count),
      label: `${plural}${plan.min_magnitude ? ` of M${plan.min_magnitude}+` : ""} · ${where}`,
    },
    stats: stats.slice(0, 4),
    references: [],
  };
}
