"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDate, formatTick } from "@/lib/format";
import type { ChartSpec } from "@/lib/api/types";
import type { Insight } from "@/lib/answer-insights";
import { chartTheme, palette, seriesColors } from "@/lib/palette";

type References = Insight["references"];

const SERIES_COLORS = seriesColors;
const MUTED = palette.muted;
const AXIS = chartTheme.axis;
const GRID = chartTheme.grid;
const TOOLTIP = chartTheme.tooltip;

type AnswerChartProps = {
  chart: ChartSpec;
  height?: number;
  /** Dashed horizontal lines (thresholds, the usual level). Only drawn when inside the data's range. */
  references?: References;
};

// Renders the backend's chart spec: {type:"line", series:[…]} or {type:"bar", bars:[…]}.
export function AnswerChart({ chart, height = 300, references = [] }: AnswerChartProps) {
  if (chart.type === "bar" && chart.bars?.length)
    return <Bars chart={chart} height={height} references={references} />;
  if (chart.series?.some((s) => s.points.length))
    return <Lines chart={chart} height={height} references={references} />;
  return (
    <div
      className="grid place-items-center rounded-2xl border border-dashed border-line text-sm text-ink-faint"
      style={{ height }}
    >
      No data points for this period.
    </div>
  );
}

function Lines({ chart, height, references }: { chart: ChartSpec; height: number; references: References }) {
  const series = (chart.series ?? []).filter((s) => s.points.length);
  const granularity = series[0]?.granularity ?? "daily";
  const unit = series[0]?.unit ?? "";

  // Merge every series onto one time axis: [{ time, "<series name>": value, … }].
  const rows = new Map<string, Record<string, number | string | null>>();
  for (const s of series) {
    for (const p of s.points) {
      const row = rows.get(p.time) ?? { time: p.time };
      row[s.name] = p.value;
      rows.set(p.time, row);
    }
  }
  const data = [...rows.values()].sort((a, b) => String(a.time).localeCompare(String(b.time)));

  // Label the single highest point right on the chart (single-series charts only).
  const peak =
    series.length === 1
      ? series[0].points.reduce<(typeof series)[0]["points"][0] | null>(
          (best, p) => (p.value != null && (best?.value == null || p.value > best.value) ? p : best),
          null,
        )
      : null;

  const shared = {
    data,
    margin: { top: 8, right: 12, left: 0, bottom: 0 },
  };
  const axes = (
    <>
      <CartesianGrid stroke={GRID} vertical={false} />
      <XAxis
        dataKey="time"
        tick={AXIS}
        tickLine={false}
        axisLine={false}
        minTickGap={28}
        tickFormatter={(t: string) => formatTick(t, granularity)}
      />
      <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} domain={["auto", "auto"]} />
      <Tooltip
        {...TOOLTIP}
        labelFormatter={(t) =>
          granularity === "hourly" ? formatTick(String(t), "hourly") : formatDate(String(t))
        }
        formatter={(value, name) => [`${value} ${unit}`, series.length > 1 ? name : ""]}
        separator={series.length > 1 ? ": " : ""}
      />
      {referenceLines(references)}
    </>
  );

  return (
    <ResponsiveContainer width="100%" height={height}>
      {series.length === 1 ? (
        <AreaChart {...shared}>
          <defs>
            <linearGradient id="answer-area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={SERIES_COLORS[0]} stopOpacity={0.3} />
              <stop offset="100%" stopColor={SERIES_COLORS[0]} stopOpacity={0} />
            </linearGradient>
          </defs>
          {axes}
          <Area
            type="monotone"
            dataKey={series[0].name}
            stroke={SERIES_COLORS[0]}
            strokeWidth={2}
            fill="url(#answer-area)"
            connectNulls
            animationDuration={1200}
          />
          {peak?.value != null && (
            <ReferenceDot
              x={peak.time}
              y={peak.value}
              r={4}
              fill={SERIES_COLORS[0]}
              stroke={palette.canvas}
              strokeWidth={2}
              label={{
                value: `${Math.round(peak.value * 10) / 10}`,
                position: "top",
                fill: palette.ink,
                fontSize: 12,
                fontWeight: 600,
              }}
            />
          )}
        </AreaChart>
      ) : (
        <LineChart {...shared}>
          {axes}
          <Legend wrapperStyle={{ fontSize: 12, color: palette.inkMuted }} />
          {series.map((s, i) => (
            <Line
              key={s.name}
              type="monotone"
              dataKey={s.name}
              stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
              strokeWidth={2}
              dot={false}
              connectNulls
              animationDuration={1200}
            />
          ))}
        </LineChart>
      )}
    </ResponsiveContainer>
  );
}

function Bars({ chart, height, references }: { chart: ChartSpec; height: number; references: References }) {
  const bars = chart.bars ?? [];
  // Comparison charts highlight the selected period; plain counts (e.g. events per month) color every bar.
  const anyHighlight = bars.some((b) => b.highlight);
  const wholeNumbers = bars.every((b) => Number.isInteger(b.value));
  const years = new Set(bars.map((b) => b.label.match(/^[A-Z][a-z]{2} (\d{4})$/)?.[1] ?? "other"));
  const sameYear = years.size === 1 && !years.has("other");
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={bars} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis
          dataKey="label"
          tick={AXIS}
          tickLine={false}
          axisLine={false}
          // Few bars: label every one. Many (e.g. 12 months): let Recharts skip labels that would collide.
          interval={bars.length <= 6 ? 0 : "preserveStartEnd"}
          minTickGap={8}
          tickFormatter={(l: string) => {
            const short = l.replace(" (selected period)", "*");
            // "Jan 2024" → "Jan" when every bar is in the same year (the title already says which).
            return sameYear ? short.replace(/ \d{4}$/, "") : short;
          }}
        />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} allowDecimals={!wholeNumbers} />
        <Tooltip
          {...TOOLTIP}
          cursor={{ fill: "rgba(255,255,255,0.04)" }}
          formatter={(v) => [v, ""]}
          separator=""
        />
        {referenceLines(references)}
        <Bar dataKey="value" radius={[6, 6, 0, 0]} animationDuration={1000}>
          {bars.map((b) => (
            <Cell key={b.label} fill={b.highlight || !anyHighlight ? SERIES_COLORS[0] : MUTED} />
          ))}
        </Bar>
      </BarChart>
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
