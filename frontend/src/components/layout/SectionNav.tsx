"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";

// Landing page sections, in page order. `id` must match the section's id attribute.
const sections = [
  { id: "why", label: "Why?" },
  { id: "ask", label: "Explore" },
  { id: "numbers", label: "The numbers" },
  { id: "showcase", label: "Features" },
  { id: "how-it-works", label: "How it works" },
];

/** The section currently crossing the middle of the viewport (scroll-spy), or null at the very top. */
function useActiveSection() {
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    const els = sections.map((s) => document.getElementById(s.id)).filter((el): el is HTMLElement => !!el);
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) if (entry.isIntersecting) setActive(entry.target.id);
      },
      // A thin band around the middle of the screen decides which section is "current".
      { rootMargin: "-45% 0px -50% 0px" },
    );
    els.forEach((el) => observer.observe(el));
    // Back in the hero (above every section): nothing is active.
    const onScroll = () => {
      if (els[0] && window.scrollY < els[0].offsetTop - window.innerHeight / 2) setActive(null);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", onScroll);
    };
  }, []);
  return active;
}

/** Inline links for tablet/desktop, with a pill that slides to the current section. */
export function SectionNavLinks() {
  const active = useActiveSection();
  return (
    <nav aria-label="Page sections" className="hidden items-center gap-2 lg:flex xl:gap-4">
      {sections.map((s) => {
        const current = s.id === active;
        return (
          <a
            key={s.id}
            href={`#${s.id}`}
            aria-current={current ? "location" : undefined}
            className={`relative rounded-full px-4 py-2 text-[12px] font-medium uppercase tracking-[0.16em] transition-colors ${
              current ? "text-ink" : "text-ink-muted hover:text-ink"
            }`}
          >
            {current && (
              <motion.span
                layoutId="section-nav-pill"
                className="absolute inset-0 -z-10 rounded-full border border-line-strong bg-surface-raised/80"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            )}
            {s.label}
          </a>
        );
      })}
    </nav>
  );
}

/** Menu button + dropdown for phones. */
export function SectionNavMenu() {
  const active = useActiveSection();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="lg:hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="section-menu"
        aria-label={open ? "Close menu" : "Open menu"}
        className="grid size-9 place-items-center rounded-full border border-line-strong text-ink-muted transition-colors hover:text-ink"
      >
        <svg
          className="size-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          aria-hidden
        >
          {open ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
        </svg>
      </button>

      <AnimatePresence>
        {open && (
          <motion.nav
            id="section-menu"
            aria-label="Page sections"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-x-0 top-full border-b border-line bg-canvas px-4 py-3 shadow-2xl shadow-black/50"
          >
            {sections.map((s) => (
              <a
                key={s.id}
                href={`#${s.id}`}
                onClick={() => setOpen(false)}
                aria-current={s.id === active ? "location" : undefined}
                className={`flex items-center justify-between rounded-xl px-3 py-3.5 text-sm font-medium uppercase tracking-[0.16em] transition-colors ${
                  s.id === active ? "bg-surface-raised text-ink" : "text-ink-muted hover:text-ink"
                }`}
              >
                {s.label}
                {s.id === active && <span className="size-1.5 rounded-full bg-accent" />}
              </a>
            ))}
          </motion.nav>
        )}
      </AnimatePresence>
    </div>
  );
}
