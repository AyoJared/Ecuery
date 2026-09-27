// Raw color values for code that can't use CSS variables (Recharts SVG attributes, the three.js
// globe, Clerk's theme). Keep in sync with the @theme tokens in src/app/globals.css.
// "Ocean and sun": slate-navy base, shades of ocean blue, amber highlights, green only for "good".
export const palette = {
  canvas: "#0a1118",
  surface: "#101a24",
  surfaceRaised: "#16232f",
  line: "rgba(196, 216, 236, 0.08)",
  lineStrong: "rgba(196, 216, 236, 0.14)",
  ink: "#eef3f8",
  inkMuted: "#a3b2c2",
  inkFaint: "#6a7888",
  oceanLight: "#b8defa",
  ocean: "#7cc4f5",
  oceanDeep: "#3d9be0",
  sun: "#f2c078",
  good: "#7fd6a0",
  /** Neutral bars/fills that shouldn't draw the eye. */
  muted: "#1c2b3a",
} as const;

/** Series colors for charts, in order. */
export const seriesColors = [palette.ocean, palette.sun, palette.oceanLight, "#fb7185"];

/** Shared Recharts axis/grid/tooltip styling. */
export const chartTheme = {
  axis: { fontSize: 11, fill: palette.inkFaint },
  grid: "rgba(196, 216, 236, 0.06)",
  tooltip: {
    contentStyle: { background: palette.surfaceRaised, border: `1px solid ${palette.lineStrong}`, borderRadius: 10, fontSize: 12 },
    labelStyle: { color: palette.inkMuted },
    itemStyle: { color: palette.ink },
  },
};
