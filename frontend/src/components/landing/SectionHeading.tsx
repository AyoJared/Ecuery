import { Reveal } from "@/components/motion/Reveal";

type SectionHeadingProps = {
  eyebrow: string;
  title: string;
  description?: string;
  align?: "center" | "left";
};

export function SectionHeading({ eyebrow, title, description, align = "center" }: SectionHeadingProps) {
  const alignment = align === "center" ? "items-center text-center mx-auto" : "items-start text-left";
  return (
    <Reveal className={`flex max-w-2xl flex-col gap-4 ${alignment}`}>
      <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">{eyebrow}</p>
      <h2 className="text-balance text-3xl font-semibold tracking-[-0.03em] text-ink sm:text-5xl">{title}</h2>
      {description && (
        <p className="text-pretty text-base leading-relaxed text-ink-muted sm:text-lg">{description}</p>
      )}
    </Reveal>
  );
}
