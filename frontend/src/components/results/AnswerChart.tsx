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
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDate, formatTick } from "@/lib/format";
import type { ChartSpec } from "@/lib/api/types";

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

// Renders the backend's chart spec: {type:"line", series:[…]} or {type:"bar", bars:[…]}.
export function AnswerChart({ chart, height = 300 }: { chart: ChartSpec; height?: number }) {
  if (chart.type === "bar" && chart.bars?.length) return <Bars chart={chart} height={height} />;
  if (chart.series?.some((s) => s.points.length)) return <Lines chart={chart} height={height} />;
  return (
    <div
      className="grid place-items-center rounded-2xl border border-dashed border-line text-sm text-ink-faint"
      style={{ height }}
    >
      No data points for this period.
    </div>
  );
}

function Lines({ chart, height }: { chart: ChartSpec; height: number }) {
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
        </AreaChart>
      ) : (
        <LineChart {...shared}>
          {axes}
          <Legend wrapperStyle={{ fontSize: 12, color: "#a3b1a8" }} />
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

function Bars({ chart, height }: { chart: ChartSpec; height: number }) {
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
        <Bar dataKey="value" radius={[6, 6, 0, 0]} animationDuration={1000}>
          {bars.map((b) => (
            <Cell key={b.label} fill={b.highlight || !anyHighlight ? SERIES_COLORS[0] : MUTED} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
