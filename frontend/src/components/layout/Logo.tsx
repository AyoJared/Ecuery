import Link from "next/link";

// Placeholder mark until there's a real logo.
export function Logo() {
  return (
    <Link href="/" className="group flex items-center gap-2.5" aria-label="Ecuery home">
      <span className="relative grid size-7 place-items-center rounded-lg border border-line-strong bg-surface-raised">
        <span className="size-2.5 rounded-full bg-accent shadow-[0_0_12px_2px_rgb(143_214_165/0.55)] transition-shadow group-hover:shadow-[0_0_16px_4px_rgb(143_214_165/0.7)]" />
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-ink">Ecuery</span>
    </Link>
  );
}
