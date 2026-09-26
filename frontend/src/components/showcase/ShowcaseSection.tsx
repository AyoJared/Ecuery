import { SectionHeading } from "@/components/landing/SectionHeading";
import { showcaseExamples } from "@/lib/showcase";
import { AnswerCard } from "./AnswerCard";

export function ShowcaseSection() {
  return (
    <section id="showcase" className="relative scroll-mt-16 py-24 sm:py-32">
      <div className="mx-auto flex max-w-5xl flex-col gap-14 px-4 sm:gap-20 sm:px-6">
        <SectionHeading
          eyebrow="See it answer"
          title="A question in. An answer and a chart out."
          description="No dashboards to dig through and no SQL. Just ask."
        />
        <div className="flex flex-col gap-10 sm:gap-16">
          {showcaseExamples.map((example) => (
            <AnswerCard key={example.question} example={example} />
          ))}
        </div>
        <p className="text-center text-xs text-ink-faint">Preview · rounded public figures</p>
      </div>
    </section>
  );
}
