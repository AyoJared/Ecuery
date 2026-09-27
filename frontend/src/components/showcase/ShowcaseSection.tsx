import { SectionHeading } from "@/components/landing/SectionHeading";
import { Reveal } from "@/components/motion/Reveal";
import { showcaseExamples } from "@/lib/showcase";
import { AnswerCard } from "./AnswerCard";
import { AskCard, CompareCard, TrendCard, VerifiedCard, VoiceCard } from "./BentoCards";

// Bento grid: one live answer as the centrepiece, smaller cards for what else an answer gives you.
export function ShowcaseSection() {
  return (
    <section id="showcase" className="relative scroll-mt-16 py-24 sm:py-32">
      <div className="mx-auto flex max-w-6xl flex-col gap-14 px-4 sm:gap-16 sm:px-6">
        <SectionHeading
          eyebrow="See it answer"
          title="A question in. An answer and a chart out."
          description="No dashboards to dig through and no SQL. Just ask."
        />

        <div className="grid gap-4 lg:grid-cols-3">
          <AnswerCard example={showcaseExamples[0]} className="lg:col-span-2 lg:row-span-2" />
          <Reveal delay={0.1} className="flex [&>*]:flex-1">
            <VoiceCard />
          </Reveal>
          <Reveal delay={0.2} className="flex [&>*]:flex-1">
            <VerifiedCard />
          </Reveal>
          <Reveal delay={0.1} className="flex [&>*]:flex-1">
            <CompareCard />
          </Reveal>
          <Reveal delay={0.2} className="flex [&>*]:flex-1">
            <TrendCard />
          </Reveal>
          <Reveal delay={0.3} className="flex [&>*]:flex-1">
            <AskCard />
          </Reveal>
        </div>

        <p className="text-center text-xs text-ink-faint">Preview · rounded public figures</p>
      </div>
    </section>
  );
}
