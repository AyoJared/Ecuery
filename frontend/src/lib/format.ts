// Display helpers for backend values (metric keys, ISO times, operations).

const METRIC_LABELS: Record<string, string> = {
  pm25: "PM2.5",
  o3: "Ozone",
  no2: "NO₂",
  co2: "CO₂",
  temperature: "Temperature",
  humidity: "Humidity",
  streamflow: "River flow",
  water_temperature: "Water temperature",
  precipitation: "Rainfall",
  dust: "Saharan dust",
  burned_area: "Burned area",
  global_temperature: "Global temperature anomaly",
  arctic_sea_ice: "Arctic sea ice extent",
  antarctic_sea_ice: "Antarctic sea ice extent",
  sea_level: "Global sea level",
};

export const metricLabel = (key: string) =>
  METRIC_LABELS[key] ?? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

const OPERATION_LABELS: Record<string, string> = {
  summary: "Summary",
  latest: "Latest reading",
  compare_history: "Compared with past years",
  compare: "Comparison",
  compare_locations: "Comparison between places",
  trend: "Trend",
  peak: "Peak",
  count: "Count",
  list: "List",
  forecast: "Forecast",
};

export const operationLabel = (op: string) => OPERATION_LABELS[op] ?? op.replace(/_/g, " ");

const dateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

/** "Jun 1 – Jun 14, 2023" style range from two ISO strings (end is exclusive in the backend's plan). */
export function formatRange(startIso: string, endIso: string) {
  const start = new Date(startIso);
  const end = new Date(new Date(endIso).getTime() - 1);
  return `${dateFmt.format(start)} – ${dateFmt.format(end)}`;
}

export const formatDate = (iso: string) => dateFmt.format(new Date(iso));

/** Axis tick for a point time, at the series' granularity. */
export function formatTick(iso: string, granularity: string) {
  const d = new Date(iso);
  if (granularity === "hourly") {
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", timeZone: "UTC" }).format(d);
  }
  if (granularity === "monthly") {
    return new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric", timeZone: "UTC" }).format(d);
  }
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(d);
}

/** Total seconds the backend spent, from its per-step timings. */
export const totalSeconds = (timings: Record<string, number>) =>
  Math.round(Object.values(timings).reduce((a, b) => a + b, 0) * 10) / 10;
