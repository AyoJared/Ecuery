"use client";

import { motion, useScroll, useSpring } from "motion/react";

// Thin accent line along the top of the viewport that fills as you scroll.
export function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 120, damping: 30, restDelta: 0.001 });

  return (
    <motion.div
      aria-hidden
      style={{ scaleX }}
      className="fixed inset-x-0 top-0 z-50 h-px origin-left bg-gradient-to-r from-accent via-sun to-accent"
    />
  );
}
