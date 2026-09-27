import { dataSources } from "@/lib/example-queries";

// Slowly scrolling band of data sources. The list is rendered twice so the loop is seamless;
// hovering pauses it, and reduce-motion users get a static, wrapped list instead.
export function SourcesStrip() {
  return (
    <div className="flex flex-col items-center gap-5">
      <p className="text-xs text-ink-faint">Built on public data from</p>
      <div className="group relative w-full overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)]">
        <div className="flex w-max animate-[marquee_40s_linear_infinite] group-hover:[animation-play-state:paused] motion-reduce:w-full motion-reduce:animate-none motion-reduce:flex-wrap motion-reduce:justify-center">
          {[0, 1].map((copy) => (
            <ul
              key={copy}
              aria-hidden={copy === 1}
              className={`flex shrink-0 items-center gap-10 pr-10 ${copy === 1 ? "motion-reduce:hidden" : "motion-reduce:flex-wrap motion-reduce:justify-center motion-reduce:gap-y-4"}`}
            >
              {dataSources.map((source) => (
                <li key={source.name} className="flex items-baseline gap-2 whitespace-nowrap">
                  <span className="font-mono text-base font-medium tracking-wider text-ink/80">{source.name}</span>
                  <span className="text-xs text-ink-faint">{source.topic}</span>
                </li>
              ))}
            </ul>
          ))}
        </div>
      </div>
    </div>
  );
}
