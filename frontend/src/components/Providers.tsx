"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";
import { AssistantProvider } from "@/components/assistant/AssistantProvider";
import { SearchProvider } from "@/components/search/SearchContext";

export function Providers({ children }: { children: ReactNode }) {
  return (
    // Honors the OS "reduce motion" setting for every Motion animation.
    <MotionConfig reducedMotion="user">
      <SearchProvider>
        <AssistantProvider>{children}</AssistantProvider>
      </SearchProvider>
    </MotionConfig>
  );
}
