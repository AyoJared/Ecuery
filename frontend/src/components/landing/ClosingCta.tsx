"use client";

import { Reveal } from "@/components/motion/Reveal";
import { useSearch } from "@/components/search/SearchContext";
import { SourcesStrip } from "./SourcesStrip";

export function ClosingCta() {
  const { ask } = useSearch();

  return (
    <section className="relative isolate overflow-hidden py-28 sm:py-36">
      <div
        aria-hidden
        className="absolute bottom-[-20rem] left-1/2 -z-10 h-[36rem] w-[56rem] max-w-[160vw] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgb(242_192_120/0.13),transparent)] blur-2xl"
      />
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-10 px-4 text-center sm:px-6">
        <Reveal className="flex flex-col items-center gap-6">
          <h2 className="text-balance text-3xl font-semibold tracking-[-0.03em] text-ink sm:text-5xl">
            What do you want to know about the planet?
          </h2>
          <button
            onClick={() => ask()}
            className="rounded-full bg-sun px-6 py-3 text-sm font-medium text-canvas transition-colors hover:bg-sun-soft"
          >
            Start asking
          </button>
        </Reveal>
      </div>
      {/* Full width so the sources band has room to scroll */}
      <Reveal delay={0.15} className="mx-auto mt-16 w-full max-w-6xl px-4 sm:px-6">
        <SourcesStrip />
      </Reveal>
    </section>
  );
}
