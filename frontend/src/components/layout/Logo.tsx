import Link from "next/link";

// Wordmark: heavy, wide-tracked caps. The letters shade from white into the brand's leaf → sun
// gradient (echoing the hero headline), and the gradient drifts a little on hover.
export function Logo() {
  return (
    <Link href="/" aria-label="Ecuery home" className="group shrink-0">
      <span
        className="mr-[-0.2em] bg-[linear-gradient(100deg,var(--color-ink)_0%,var(--color-ink)_42%,var(--color-accent-soft)_72%,var(--color-sun)_100%)] bg-[length:140%_100%] bg-left bg-clip-text text-[19px] font-extrabold uppercase tracking-[0.2em] text-transparent transition-[background-position] duration-700 ease-out group-hover:bg-right"
      >
        Ecuery
      </span>
    </Link>
  );
}
