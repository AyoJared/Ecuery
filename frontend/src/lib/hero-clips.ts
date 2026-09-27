import type { HazardKind } from "./hazard-icons";

// Background clips for the landing hero, shown in order and crossfaded.
//
// To add real footage: drop files in public/videos/ and fill in `video` + `poster`.
//   video.src        1280px wide H.264 .mp4, no audio, 6–10 s, ideally < 3 MB
//   video.mobileSrc  optional ~720px version for phones
//   poster           first frame as .webp (shown instantly, and to reduce-motion users)
// Clips without `video` render a styled placeholder, so the hero works either way.
// Only use footage you have rights to (NASA/NOAA public domain, Pexels, Pixabay…).

export type HeroClip = {
  id: string;
  kind: HazardKind;
  label: string;
  /** Optional specifics once real footage is in, e.g. "Québec, 2023". */
  detail?: string;
  /** Question the "Ask about this" link puts in the search bar. */
  question: string;
  video?: { src: string; mobileSrc?: string };
  poster?: string;
  /** CSS object-position for the crop, e.g. "60% 50%". Matters most on phones (portrait crop). */
  focus?: string;
  durationMs?: number;
  credit?: string;
};

export const HERO_CLIP_DURATION_MS = 7000;

export const heroClips: HeroClip[] = [
  {
    id: "hurricane",
    kind: "cyclone",
    label: "Hurricanes",
    question: "Which hurricanes intensified fastest in the last decade?",
    video: { src: "/videos/hurricane.mp4", mobileSrc: "/videos/hurricane-mobile.mp4" },
    poster: "/videos/hurricane.webp",
    focus: "45% 50%",
  },
  {
    id: "wildfire",
    kind: "wildfire",
    label: "Wildfires",
    question: "Compare 2023 vs 2024 wildfire acreage in Canada",
    video: { src: "/videos/wildfire.mp4", mobileSrc: "/videos/wildfire-mobile.mp4" },
    poster: "/videos/wildfire.webp",
    focus: "72% 50%",
  },
  {
    id: "tornado",
    kind: "tornado",
    label: "Tornadoes",
    question: "How many EF4+ tornadoes hit the US each year since 2000?",
    video: { src: "/videos/tornado.mp4", mobileSrc: "/videos/tornado-mobile.mp4" },
    poster: "/videos/tornado.webp",
    focus: "58% 50%",
  },
  {
    id: "ice",
    kind: "ice",
    label: "Sea ice",
    question: "How fast is Arctic sea ice shrinking?",
    video: { src: "/videos/icecap.mp4", mobileSrc: "/videos/icecap-mobile.mp4" },
    poster: "/videos/icecap.webp",
    focus: "60% 50%",
  },
  {
    id: "flood",
    kind: "flood",
    label: "Floods",
    detail: "Bangladesh",
    question: "How has monsoon flooding in Bangladesh changed since 2000?",
    video: { src: "/videos/flood.mp4", mobileSrc: "/videos/flood-mobile.mp4" },
    poster: "/videos/flood.webp",
    focus: "50% 50%",
  },
];
