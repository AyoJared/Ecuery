// Which ways of drawing an answer's chart make sense, and how to re-shape the data for them.
//
// People can switch chart type and time resolution, but only among views that are honest for the
// data: nothing finer than what was measured, no bars for hundreds of points, no areas stacked on
// top of each other, no line through separate comparison periods. Options that don't fit stay
// visible but disabled, with the reason (shown as a tooltip).

import type { ChartPoint, ChartSpec } from "./api/types";

export type ChartKind = "line" | "area" | "bar";
export type Resolution = "native" | "daily" | "weekly" | "monthly" | "yearly";

export type ChartView = { kind: ChartKind; resolution: Resolution; band: boolean; log: boolean };

export type Option<T> = { value: T; label: string; disabled?: string };

export type ViewOptions = {
  kinds: Option<ChartKind>[];
  resolutions: Option<Resolution>[];
  /** Uncertainty band toggle: only when points carry lo/hi. */
  band: Option<boolean> | null;
  /** Log scale: only when every value is positive and they span orders of magnitude (e.g. river flow). */
  log: Option<boolean> | null;
  initial: ChartView;
};

const MAX_BARS = 60;
const RES_ORDER: Resolution[] = ["daily", "weekly", "monthly", "yearly"];
const RES_LABEL: Record<Resolution, string> = {
  native: "As measured",
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  yearly: "Yearly",
};
const NATIVE_RANK: Record<string, number> = { raw: -1, hourly: -1, daily: 0, weekly: 1, monthly: 2, yearly: 3 };

// ------------------------------------------------------------------ time series (line specs)

function bucketKey(iso: string, res: Resolution) {
  const d = new Date(iso);
  if (res === "daily") return iso.slice(0, 10);
  if (res === "monthly") return iso.slice(0, 7) + "-01";
  if (res === "yearly") return iso.slice(0, 4) + "-01-01";
  // weekly: the Monday that starts the week (UTC)
  const monday = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - ((d.getUTCDay() + 6) % 7)));
  return monday.toISOString().slice(0, 10);
}

const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
const round2 = (x: number) => Math.round(x * 100) / 100;

/** Average points into coarser buckets. Readings are levels (not counts), so buckets use the mean. */
export function resample(points: ChartPoint[], res: Resolution): ChartPoint[] {
  if (res === "native") return points;
  const groups = new Map<string, ChartPoint[]>();
  for (const p of points) {
    const k = bucketKey(p.time, res);
    groups.set(k, [...(groups.get(k) ?? []), p]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, ps]) => {
      const vals = ps.map((p) => p.value).filter((v): v is number => v != null);
      const los = ps.map((p) => p.lo).filter((v): v is number => v != null);
      const his = ps.map((p) => p.hi).filter((v): v is number => v != null);
      return {
        time: `${k}T00:00:00+00:00`,
        value: vals.length ? round2(mean(vals)) : null,
        lo: los.length === ps.length ? round2(mean(los)) : null,
        hi: his.length === ps.length ? round2(mean(his)) : null,
        forecast: ps.every((p) => p.forecast) ? true : ps.some((p) => p.forecast) ? undefined : false,
        method: ps[0]?.method,
      };
    });
}

function seriesOptions(chart: ChartSpec, resolution: Resolution): ViewOptions {
  const series = (chart.series ?? []).filter((s) => s.points.length);
  const native = series[0]?.granularity ?? "daily";
  const nativeRank = NATIVE_RANK[native] ?? 0;
  const isForecast = series.some((s) => s.points.some((p) => p.forecast));
  const hasBand = series.some((s) => s.points.some((p) => p.lo != null && p.hi != null));
  const values = series.flatMap((s) => s.points.flatMap((p) => [p.value, p.lo, p.hi])).filter((v): v is number => v != null);

  const pointsAt = (res: Resolution) => Math.max(...series.map((s) => resample(s.points, res).length), 0);

  const resolutions: Option<Resolution>[] = [{ value: "native", label: RES_LABEL.native }];
  for (const res of RES_ORDER) {
    const rank = RES_ORDER.indexOf(res);
    let disabled: string | undefined;
    if (rank < nativeRank || (rank === nativeRank && native !== "raw" && native !== "hourly")) {
      disabled = rank < nativeRank
        ? `This data is ${native}; it can't be shown at a finer ${res} resolution.`
        : `Already ${native}.`;
    } else if (isForecast) {
      disabled = "Forecast days are shown as issued, so each day's uncertainty stays accurate.";
    } else if (pointsAt(res) < 3) {
      disabled = `Too little time covered: ${res} would leave fewer than 3 points.`;
    }
    resolutions.push({ value: res, label: RES_LABEL[res], disabled });
  }

  const kinds: Option<ChartKind>[] = [
    { value: "line", label: "Line" },
    {
      value: "area",
      label: "Area",
      disabled: series.length > 1 ? "Filled areas would hide each other with more than one series." : undefined,
    },
    {
      value: "bar",
      label: "Bars",
      disabled: isForecast
        ? "Bars can't show a forecast's uncertainty range."
        : pointsAt(resolution) > MAX_BARS
          ? `Too many points (${pointsAt(resolution)}) to read as bars. Choose a coarser resolution first.`
          : undefined,
    },
  ];

  const positive = values.length > 0 && values.every((v) => v > 0);
  const spread = positive ? Math.max(...values) / Math.min(...values) : 0;
  const log: Option<boolean> | null =
    values.length === 0
      ? null
      : {
          value: true,
          label: "Log scale",
          disabled: !positive
            ? "Log scale needs every value above zero."
            : spread < 20
              ? "Values don't span enough range for a log scale to help."
              : undefined,
        };

  return {
    kinds,
    resolutions,
    band: hasBand ? { value: true, label: "Uncertainty range" } : null,
    log,
    initial: { kind: series.length === 1 && !isForecast ? "area" : "line", resolution: "native", band: hasBand, log: false },
  };
}

// ------------------------------------------------------------------ categories / counts (bar specs)

const MONTH_LABEL = /^([A-Z][a-z]{2}) (\d{4})$/;

function barOptions(chart: ChartSpec): ViewOptions {
  const bars = chart.bars ?? [];
  const comparison = bars.some((b) => b.highlight || /selected period/.test(b.label));
  const monthly = bars.length > 0 && bars.every((b) => MONTH_LABEL.test(b.label));
  const yearly = bars.length > 0 && bars.every((b) => /^\d{4}$/.test(b.label));
  const overTime = monthly || yearly;
  const years = new Set(bars.map((b) => b.label.match(MONTH_LABEL)?.[2]));

  const kinds: Option<ChartKind>[] = [
    { value: "bar", label: "Bars" },
    {
      value: "line",
      label: "Line",
      disabled: comparison
        ? "These bars compare separate periods; a line would suggest a trend between them."
        : !overTime
          ? "A line only makes sense for values over time."
          : bars.length < 4
            ? "Too few periods for a line."
            : undefined,
    },
    {
      value: "area",
      label: "Area",
      disabled: comparison
        ? "Each bar is a separate period; a filled area would suggest a continuous change between them."
        : "These are counts of separate events, not a continuous level.",
    },
  ];
  const resolutions: Option<Resolution>[] = [
    { value: "native", label: monthly ? "Monthly" : yearly ? "Yearly" : RES_LABEL.native },
  ];
  if (monthly) {
    resolutions.push({
      value: "yearly",
      label: "Yearly",
      disabled: years.size < 2 ? "Everything is in one year." : undefined,
    });
  }
  return { kinds, resolutions, band: null, log: null, initial: { kind: "bar", resolution: "native", band: false, log: false } };
}

/** Event counts per month -> per year (counts add up, unlike levels). */
export function barsByYear(chart: ChartSpec) {
  const totals = new Map<string, number>();
  for (const b of chart.bars ?? []) {
    const year = b.label.match(MONTH_LABEL)?.[2] ?? b.label;
    totals.set(year, (totals.get(year) ?? 0) + b.value);
  }
  return [...totals.entries()].map(([label, value]) => ({ label, value }));
}

/** Options for this chart, given the resolution currently picked (bars depend on how many points it leaves). */
export function viewOptions(chart: ChartSpec, resolution: Resolution = "native"): ViewOptions {
  return chart.type === "bar" && chart.bars?.length ? barOptions(chart) : seriesOptions(chart, resolution);
}

/** Keep a view valid for this chart (e.g. after the data changes). */
export function sanitize(view: ChartView, options: ViewOptions): ChartView {
  const ok = <T,>(opts: Option<T>[], v: T) => opts.some((o) => o.value === v && !o.disabled);
  return {
    kind: ok(options.kinds, view.kind) ? view.kind : options.initial.kind,
    resolution: ok(options.resolutions, view.resolution) ? view.resolution : "native",
    band: options.band ? view.band : false,
    log: options.log && !options.log.disabled ? view.log : false,
  };
}
