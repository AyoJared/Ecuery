import { eventTypes, type EventType } from "./events";

export type HazardKind = EventType | "flood" | "ice";

export const hazardColors: Record<HazardKind, string> = {
  cyclone: eventTypes.cyclone.color,
  tornado: eventTypes.tornado.color,
  wildfire: eventTypes.wildfire.color,
  air: eventTypes.air.color,
  flood: "#2dd4bf",
  ice: "#e0f2fe",
};

// Inner SVG markup (24×24 viewBox) for each hazard. One source of truth for the
// globe markers (raw DOM) and <HazardIcon> (React). Animation classes live in globals.css.
export const hazardIconMarkup: Record<HazardKind, string> = {
  // Meteorological hurricane symbol, spinning counter-clockwise (N. hemisphere)
  cyclone: `<g class="hz-spin">
    <circle cx="12" cy="12" r="2.6"/>
    <path d="M9.9 10.5C8.8 6.2 11.7 3 17 3"/>
    <path d="M14.1 13.5C15.2 17.8 12.3 21 7 21"/>
  </g>`,
  // Funnel lines swaying out of phase
  tornado: `
    <path class="hz-sway" style="--i:0" d="M21 4H3"/>
    <path class="hz-sway" style="--i:1" d="M18 8H6"/>
    <path class="hz-sway" style="--i:2" d="M19 12H9"/>
    <path class="hz-sway" style="--i:3" d="M16 16h-6"/>
    <path class="hz-sway" style="--i:4" d="M11 20H9"/>`,
  // Flickering flame
  wildfire: `<path class="hz-flicker" d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>`,
  // Drifting haze / smog layers
  air: `
    <path class="hz-drift" style="--i:0" d="M3 7.5c2-1.5 4-1.5 6 0s4 1.5 6 0 4-1.5 6 0"/>
    <path class="hz-drift" style="--i:1" d="M3 12c2-1.5 4-1.5 6 0s4 1.5 6 0 4-1.5 6 0"/>
    <path class="hz-drift" style="--i:2" d="M6 16.5c1.5-1.1 3-1.1 4.5 0s3 1.1 4.5 0 3-1.1 4.5 0"/>`,
  // Falling drop over rising water
  flood: `
    <path class="hz-bob" d="M12 2.5s-4 4.4-4 7.3a4 4 0 0 0 8 0c0-2.9-4-7.3-4-7.3z"/>
    <path class="hz-drift" style="--i:0" d="M2 17c1.7-1.3 3.3-1.3 5 0s3.3 1.3 5 0 3.3-1.3 5 0 3.3 1.3 5 0"/>
    <path class="hz-drift" style="--i:1" d="M2 21c1.7-1.3 3.3-1.3 5 0s3.3 1.3 5 0 3.3-1.3 5 0 3.3 1.3 5 0"/>`,
  // Slowly turning ice crystal
  ice: `<g class="hz-spin-slow">
    <path d="M12 2v20"/>
    <path d="M3.3 7l17.4 10"/>
    <path d="M20.7 7 3.3 17"/>
    <path d="m9 4 3 2 3-2"/>
    <path d="m9 20 3-2 3 2"/>
  </g>`,
};

export function hazardSvg(type: HazardKind, south = false) {
  return `<svg class="hz${south ? " hz--south" : ""}" viewBox="0 0 24 24" aria-hidden="true">${hazardIconMarkup[type]}</svg>`;
}
