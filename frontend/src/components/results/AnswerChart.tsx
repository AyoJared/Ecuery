"use client";

import { useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDate, formatTick } from "@/lib/format";
import type { ChartSpec } from "@/lib/api/types";
import type { Insight } from "@/lib/answer-insights";
import {
  barsByYear,
  resample,
  sanitize,
  viewOptions,
  type ChartView,
  type Option,
  type ViewOptions,
} from "@/lib/chart-views";

type References = Insight["references"];

const SERIES_COLORS = ["#8fd6a5", "#7cc4f5", "#f2c078", "#fb7185"];
const MUTED = "#22332c";
const AXIS = { fontSize: 11, fill: "#6b7a71" };
const GRID = "rgba(214,235,222,0.06)";
const TOOLTIP = {
  contentStyle: {
    background: "#142520",
    border: "1px solid rgba(214,235,222,0.14)",
    borderRadius: 10,
    fontSize: 12,
  },
  labelStyle: { color: "#a3b1a8" },
  itemStyle: { color: "#eef2ea" },
};

// Renders the backend's chart spec: {type:"line", series:[…]} or {type:"bar", bars:[…]}, with controls
// to switch between the views that make sense for that data (see lib/chart-views.ts).
export function AnswerChart({
  chart,
  height = 300,
  references = [],
}: {
  chart: ChartSpec;
  height?: number;
  /** Dashed horizontal lines (thresholds, the usual level). Only drawn when inside the data's range. */
  references?: References;
}) {
  const [picked, setPicked] = useState<ChartView>(() => viewOptions(chart).initial);
  const options = viewOptions(chart, picked.resolution);
  const view = sanitize(picked, options);
  const hasBars = chart.type === "bar" && !!chart.bars?.length;
  const hasSeries = !hasBars && !!chart.series?.some((s) => s.points.length);

  if (!hasBars && !hasSeries) {
    return (
      <div
        className="grid place-items-center rounded-2xl border border-dashed border-line text-sm text-ink-faint"
        style={{ height }}
      >
        No data points for this period.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <ChartControls options={options} view={view} onChange={setPicked} />
      {hasBars ? (
        <Bars chart={chart} view={view} height={height} references={references} />
      ) : (
        <Series chart={chart} view={view} height={height} references={references} />
      )}
    </div>
  );
}

// ------------------------------------------------------------------ controls

function ChartControls({
  options,
  view,
  onChange,
}: {
  options: ViewOptions;
  view: ChartView;
  onChange: (v: ChartView) => void;
}) {
  const [note, setNote] = useState<string | null>(null);
  // Only offer a resolution picker when there's a real choice.
  const resolutions = options.resolutions.filter((o) => !o.disabled?.startsWith("Already"));
  const showResolutions = resolutions.filter((o) => !o.disabled).length > 1;

  const pick = <T,>(o: Option<T>, apply: () => void) => {
    if (o.disabled) {
      setNote(o.disabled);
      return;
    }
    setNote(null);
    apply();
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          label="Chart type"
          options={options.kinds}
          value={view.kind}
          onPick={(o) => pick(o, () => onChange({ ...view, kind: o.value }))}
        />
        {showResolutions && (
          <Segmented
            label="Resolution"
            options={resolutions}
            value={view.resolution}
            onPick={(o) => pick(o, () => onChange({ ...view, resolution: o.value }))}
          />
        )}
        {options.band && (
          <Toggle
            option={options.band}
            on={view.band}
            onPick={() => pick(options.band!, () => onChange({ ...view, band: !view.band }))}
          />
        )}
        {options.log && (
          <Toggle option={options.log} on={view.log} onPick={() => pick(options.log!, () => onChange({ ...view, log: !view.log }))} />
        )}
      </div>
      {note && (
        <p role="status" className="text-xs text-ink-faint">
          {note}
        </p>
      )}
    </div>
  );
}

function Segmented<T extends string>({
  label,
  options,
  value,
  onPick,
}: {
  label: string;
  options: Option<T>[];
  value: T;
  onPick: (o: Option<T>) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-full border border-line bg-surface/60 p-0.5">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            aria-disabled={!!o.disabled}
            title={o.disabled}
            onClick={() => onPick(o)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              active
                ? "bg-accent/15 text-accent"
                : o.disabled
                  ? "cursor-help text-ink-faint/50"
                  : "text-ink-muted hover:text-ink"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

function Toggle({ option, on, onPick }: { option: Option<boolean>; on: boolean; onPick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-disabled={!!option.disabled}
      title={option.disabled}
      onClick={onPick}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
        on
          ? "border-accent/35 bg-accent/10 text-accent"
          : option.disabled
            ? "cursor-help border-line text-ink-faint/50"
            : "border-line text-ink-muted hover:text-ink"
      }`}
    >
      {option.label}
    </button>
  );
}

// ------------------------------------------------------------------ time series (incl. forecasts)

type Row = Record<string, number | string | [number, number] | null>;

type ChartProps = { chart: ChartSpec; view: ChartView; height: number; references: References };

function Series({ chart, view, height, references }: ChartProps) {
  const series = (chart.series ?? [])
    .filter((s) => s.points.length)
    .map((s) => ({ ...s, points: resample(s.points, view.resolution) }));
  const granularity = view.resolution === "native" ? (series[0]?.granularity ?? "daily") : view.resolution;
  const unit = series[0]?.unit ?? "";
  const forecast = series.some((s) => s.points.some((p) => p.forecast));

  // One row per time: "<name>" observed, "<name>__f" forecast, "<name>__band" [lo, hi].
  const rows = new Map<string, Row>();
  for (const s of series) {
    const lastObserved = [...s.points].reverse().find((p) => p.forecast === false);
    for (const p of s.points) {
      const row = rows.get(p.time) ?? { time: p.time };
      if (p.forecast) {
        row[`${s.name}__f`] = p.value;
        if (view.band && p.lo != null && p.hi != null) row[`${s.name}__band`] = [p.lo, p.hi];
      } else {
        row[s.name] = p.value;
      }
      // Start the dashed forecast line where the observed line ends, so they join up.
      if (p === lastObserved) row[`${s.name}__f`] = p.value;
      rows.set(p.time, row);
    }
  }
  const data = [...rows.values()].sort((a, b) => String(a.time).localeCompare(String(b.time)));
  const legend = series.length > 1 || forecast;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.name} id={`answer-area-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={SERIES_COLORS[i % SERIES_COLORS.length]} stopOpacity={0.3} />
              <stop offset="100%" stopColor={SERIES_COLORS[i % SERIES_COLORS.length]} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        {referenceLines(references)}
        <XAxis
          dataKey="time"
          tick={AXIS}
          tickLine={false}
          axisLine={false}
          minTickGap={28}
          tickFormatter={(t: string) => formatTick(t, granularity)}
        />
        <YAxis
          tick={AXIS}
          tickLine={false}
          axisLine={false}
          width={52}
          scale={view.log ? "log" : "auto"}
          domain={["auto", "auto"]}
          allowDataOverflow={view.log}
        />
        <Tooltip
          {...TOOLTIP}
          labelFormatter={(t) => (granularity === "hourly" ? formatTick(String(t), "hourly") : formatDate(String(t)))}
          formatter={(value, name) => {
            const key = String(name);
            const text = Array.isArray(value) ? `${value[0]} – ${value[1]} ${unit}` : `${value} ${unit}`;
            return [text, key];
          }}
        />
        {legend && <Legend wrapperStyle={{ fontSize: 12, color: "#a3b1a8" }} />}
        {series.map((s, i) => {
          const color = SERIES_COLORS[i % SERIES_COLORS.length];
          const hasForecast = s.points.some((p) => p.forecast);
          return [
            view.band && hasForecast && (
              <Area
                key={`${s.name}-band`}
                dataKey={`${s.name}__band`}
                name={`${s.name} range`}
                stroke="none"
                fill={color}
                fillOpacity={0.14}
                isAnimationActive={false}
                connectNulls
              />
            ),
            view.kind === "bar" ? (
              <Bar key={s.name} dataKey={s.name} name={s.name} fill={color} radius={[4, 4, 0, 0]} />
            ) : view.kind === "area" ? (
              <Area
                key={s.name}
                type="monotone"
                dataKey={s.name}
                name={hasForecast ? `${s.name} (observed)` : s.name}
                stroke={color}
                strokeWidth={2}
                fill={`url(#answer-area-${i})`}
                connectNulls
                animationDuration={1200}
              />
            ) : (
              <Line
                key={s.name}
                type="monotone"
                dataKey={s.name}
                name={hasForecast ? `${s.name} (observed)` : s.name}
                stroke={color}
                strokeWidth={2}
                dot={false}
                connectNulls
                animationDuration={1200}
              />
            ),
            hasForecast && (
              <Line
                key={`${s.name}-forecast`}
                type="monotone"
                dataKey={`${s.name}__f`}
                name={`${s.name} (forecast)`}
                stroke={color}
                strokeWidth={2}
                strokeDasharray="6 4"
                dot={false}
                connectNulls
                animationDuration={1200}
              />
            ),
          ];
        })}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------------------------ categories / counts

function Bars({ chart, view, height, references }: ChartProps) {
  const bars = view.resolution === "yearly" ? barsByYear(chart) : (chart.bars ?? []);
  // Comparison charts highlight the selected period; plain counts (e.g. events per month) color every bar.
  const anyHighlight = bars.some((b) => "highlight" in b && b.highlight);
  const wholeNumbers = bars.every((b) => Number.isInteger(b.value));
  const years = new Set(bars.map((b) => b.label.match(/^[A-Z][a-z]{2} (\d{4})$/)?.[1] ?? "other"));
  const sameYear = years.size === 1 && !years.has("other");
  const tickFormatter = (l: string) => {
    const short = l.replace(" (selected period)", "*");
    // "Jan 2024" → "Jan" when every bar is in the same year (the title already says which).
    return sameYear ? short.replace(/ \d{4}$/, "") : short;
  };
  const axes = (
    <>
      <CartesianGrid stroke={GRID} vertical={false} />
      <XAxis
        dataKey="label"
        tick={AXIS}
        tickLine={false}
        axisLine={false}
        // Few bars: label every one. Many (e.g. 12 months): let Recharts skip labels that would collide.
        interval={bars.length <= 6 ? 0 : "preserveStartEnd"}
        minTickGap={8}
        tickFormatter={tickFormatter}
      />
      <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} allowDecimals={!wholeNumbers} />
      <Tooltip {...TOOLTIP} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v) => [v, ""]} separator="" />
      {referenceLines(references)}
    </>
  );

  return (
    <ResponsiveContainer width="100%" height={height}>
      {view.kind === "line" ? (
        <LineChart data={bars} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          {axes}
          <Line type="monotone" dataKey="value" stroke={SERIES_COLORS[0]} strokeWidth={2} dot={{ r: 3 }} animationDuration={1000} />
        </LineChart>
      ) : (
        <BarChart data={bars} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          {axes}
          <Bar dataKey="value" radius={[6, 6, 0, 0]} animationDuration={1000}>
            {bars.map((b) => (
              <Cell
                key={b.label}
                fill={("highlight" in b && b.highlight) || !anyHighlight ? SERIES_COLORS[0] : MUTED}
              />
            ))}
          </Bar>
        </BarChart>
      )}
    </ResponsiveContainer>
  );
}

function referenceLines(references: References) {
  return references.map((r) => (
    <ReferenceLine
      key={r.label}
      y={r.y}
      stroke={r.color}
      strokeDasharray="5 5"
      strokeOpacity={0.7}
      ifOverflow={r.extend ? "extendDomain" : "hidden"}
      label={{ value: r.label, position: "insideTopRight", fill: r.color, fontSize: 11 }}
    />
  ));
}

/** The same numbers as the chart, as a table (for exact values and screen readers). */
export function ChartTable({ chart }: { chart: ChartSpec }) {
  const bars = chart.type === "bar" ? (chart.bars ?? []) : [];
  const series = (chart.series ?? []).filter((s) => s.points.length);
  const granularity = series[0]?.granularity ?? "daily";
  const unit = series[0]?.unit ?? "";
  const times = [...new Set(series.flatMap((s) => s.points.map((p) => p.time)))].sort();
  const valueAt = (i: number, t: string) => series[i].points.find((p) => p.time === t)?.value;

  return (
    <div className="max-h-80 overflow-auto rounded-2xl border border-line">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-surface text-xs text-ink-faint">
          {bars.length ? (
            <tr>
              <th className="px-4 py-2.5 font-medium">{chart.x_label || "Period"}</th>
              <th className="px-4 py-2.5 text-right font-medium">{chart.y_label}</th>
            </tr>
          ) : (
            <tr>
              <th className="px-4 py-2.5 font-medium">Date</th>
              {series.map((s) => (
                <th key={s.name} className="px-4 py-2.5 text-right font-medium">
                  {series.length > 1 ? s.name : `${chart.y_label || s.name}`}
                </th>
              ))}
            </tr>
          )}
        </thead>
        <tbody className="divide-y divide-line tabular-nums">
          {bars.length
            ? bars.map((b) => (
                <tr key={b.label} className={b.highlight ? "text-ink" : "text-ink-muted"}>
                  <td className="px-4 py-2">{b.label}</td>
                  <td className="px-4 py-2 text-right">{b.value}</td>
                </tr>
              ))
            : times.map((t) => (
                <tr key={t} className="text-ink-muted">
                  <td className="px-4 py-2">
                    {granularity === "hourly" ? formatTick(t, "hourly") : formatDate(t)}
                  </td>
                  {series.map((s, i) => {
                    const v = valueAt(i, t);
                    return (
                      <td key={s.name} className="px-4 py-2 text-right text-ink">
                        {v == null ? "–" : `${v} ${series.length > 1 ? s.unit : unit}`}
                      </td>
                    );
                  })}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}
