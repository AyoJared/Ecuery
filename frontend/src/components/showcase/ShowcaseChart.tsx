"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ShowcaseExample } from "@/lib/showcase";

const ACCENT = "#8fd6a5";
const SUN = "#f2c078";
const MUTED = "#22332c";
const AXIS = { fontSize: 11, fill: "#6b7a71" };

export function ShowcaseChart({ example }: { example: ShowcaseExample }) {
  const { chart, data, unit, highlight, yDomain } = example;
  const shared = {
    data,
    margin: { top: 8, right: 8, left: -8, bottom: 0 },
  };
  const axes = (
    <>
      <CartesianGrid stroke="rgba(214,235,222,0.06)" vertical={false} />
      <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} minTickGap={16} />
      <YAxis tick={AXIS} tickLine={false} axisLine={false} width={40} domain={yDomain ?? [0, "auto"]} />
      <Tooltip
        cursor={{ fill: "rgba(255,255,255,0.04)", stroke: "rgba(255,255,255,0.1)" }}
        contentStyle={{ background: "#142520", border: "1px solid rgba(214,235,222,0.14)", borderRadius: 10, fontSize: 12 }}
        labelStyle={{ color: "#a3b1a8" }}
        itemStyle={{ color: "#eef2ea" }}
        formatter={(value) => [`${value} ${unit}`, ""]}
        separator=""
      />
    </>
  );

  return (
    <ResponsiveContainer width="100%" height="100%">
      {chart === "area" ? (
        <AreaChart {...shared}>
          <defs>
            <linearGradient id="showcase-area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ACCENT} stopOpacity={0.35} />
              <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
            </linearGradient>
          </defs>
          {axes}
          <Area type="monotone" dataKey="value" stroke={ACCENT} strokeWidth={2} fill="url(#showcase-area)" animationDuration={1400} />
        </AreaChart>
      ) : chart === "bar" ? (
        <BarChart {...shared}>
          {axes}
          <Bar dataKey="value" radius={[6, 6, 0, 0]} animationDuration={1200}>
            {data.map((d) => (
              <Cell key={d.label} fill={highlight?.includes(d.label) ? ACCENT : MUTED} />
            ))}
          </Bar>
        </BarChart>
      ) : (
        <LineChart {...shared}>
          {axes}
          <Line type="monotone" dataKey="value" stroke={SUN} strokeWidth={2} dot={false} animationDuration={1600} />
        </LineChart>
      )}
    </ResponsiveContainer>
  );
}
