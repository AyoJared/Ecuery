"use client";

import Image from "next/image";
import { useEffect, useRef } from "react";
import { HazardIcon } from "@/components/globe/HazardIcon";
import { hazardColors } from "@/lib/hazard-icons";
import type { HeroClip } from "@/lib/hero-clips";

const FADE_MS = 1200;

type ClipLayerProps = {
  clip: HeroClip;
  durationMs: number;
  active: boolean;
  /** Mount the <video> (current and next clip only, to limit downloads). */
  load: boolean;
  playing: boolean;
  isMobile: boolean;
  staticOnly: boolean;
  priority: boolean;
  /** Hands the mounted <video> to the hero, which times the clip off its playback. */
  registerVideo?: (el: HTMLVideoElement | null) => void;
};

// One full-bleed background layer. Layers are stacked; the active one fades in
// and slowly zooms (Ken Burns) for the length of the clip.
export function ClipLayer({ clip, durationMs, active, load, playing, isMobile, staticOnly, priority, registerVideo }: ClipLayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const src = isMobile && clip.video?.mobileSrc ? clip.video.mobileSrc : clip.video?.src;
  const showVideo = Boolean(src) && load && !staticOnly;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (active && playing) {
      // Re-selected before the delayed rewind ran: start over rather than sit on the end.
      if (video.ended) video.currentTime = 0;
      video.play().catch(() => {});
      return;
    }
    video.pause();
    if (active) return;
    // Rewind only once the layer has faded out, so the fade shows the last frame.
    const t = setTimeout(() => (video.currentTime = 0), FADE_MS);
    return () => clearTimeout(t);
  }, [active, playing]);

  return (
    <div
      aria-hidden
      className="absolute inset-0 transition-opacity ease-out"
      style={{ opacity: active ? 1 : 0, transitionDuration: `${FADE_MS}ms` }}
    >
      <div
        className="absolute inset-0"
        style={{
          transform: active && !staticOnly ? "scale(1.08)" : "scale(1)",
          // Zoom in over the clip; reset only after the layer has faded out.
          transition: active ? `transform ${durationMs + FADE_MS}ms linear` : `transform 0s ${FADE_MS}ms`,
        }}
      >
        {showVideo ? (
          <video
            ref={(el) => {
              videoRef.current = el;
              registerVideo?.(el);
            }}
            src={src}
            poster={clip.poster}
            muted
            playsInline
            preload="auto"
            className="size-full object-cover saturate-[0.85]"
            style={{ objectPosition: clip.focus }}
          />
        ) : clip.poster ? (
          <Image
            src={clip.poster}
            alt=""
            fill
            sizes="100vw"
            priority={priority}
            className="object-cover saturate-[0.85]"
            style={{ objectPosition: clip.focus }}
          />
        ) : (
          <Placeholder clip={clip} />
        )}
      </div>
    </div>
  );
}

// Stand-in until real footage is added in lib/hero-clips.ts.
function Placeholder({ clip }: { clip: HeroClip }) {
  const color = hazardColors[clip.kind];
  return (
    <div
      className="relative size-full"
      style={{
        background: `radial-gradient(ellipse 60% 70% at 70% 40%, color-mix(in srgb, ${color} 28%, transparent), transparent 70%),
          radial-gradient(ellipse 50% 60% at 20% 80%, color-mix(in srgb, ${color} 14%, transparent), transparent 70%),
          #0a1712`,
      }}
    >
      <div className="absolute right-[8%] top-1/2 size-[42vmin] -translate-y-1/2 opacity-[0.12]" style={{ color }}>
        <HazardIcon type={clip.kind} />
      </div>
      {process.env.NODE_ENV === "development" && (
        <p className="absolute right-4 top-20 z-10 rounded-md border border-line bg-canvas/60 px-2 py-1 font-mono text-[11px] text-ink-faint">
          placeholder · add public/videos/{clip.id}.mp4
        </p>
      )}
    </div>
  );
}
