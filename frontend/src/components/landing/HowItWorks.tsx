import { Reveal } from "@/components/motion/Reveal";
import { SectionHeading } from "./SectionHeading";

const steps = [
  {
    title: "Ask in plain English",
    body: "Type or speak a question about sea levels, storms, fires, air or heat. Any place, any time range.",
  },
  {
    title: "We query decades of data",
    body: "Your question becomes a structured query across recent sensor readings and long-term historical archives.",
  },
  {
    title: "Get an answer you can check",
    body: "A direct answer and a chart, with the source dataset cited on every result.",
  },
];

export function HowItWorks() {
  return (
    <section className="relative border-y border-line bg-surface/30 py-24 sm:py-32">
      <div className="mx-auto flex max-w-6xl flex-col gap-14 px-4 sm:px-6">
        <SectionHeading eyebrow="How it works" title="From question to evidence in seconds." />
        <ol className="grid gap-4 md:grid-cols-3">
          {steps.map((step, i) => (
            <li key={step.title}>
              <Reveal
                delay={i * 0.12}
                className="flex h-full flex-col gap-4 rounded-2xl border border-line bg-canvas/60 p-6"
              >
                <span className="font-mono text-sm text-accent">0{i + 1}</span>
                <h3 className="text-lg font-semibold tracking-tight text-ink">{step.title}</h3>
                <p className="text-sm leading-relaxed text-ink-muted">{step.body}</p>
              </Reveal>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
