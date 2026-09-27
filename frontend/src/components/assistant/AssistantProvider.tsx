"use client";

import dynamic from "next/dynamic";
import { createContext, useContext, useState, type ReactNode } from "react";

// Loaded on first open: the overlay pulls in the chart library and audio code the landing page doesn't need.
const ResearchAssistant = dynamic(() => import("./ResearchAssistant").then((m) => m.ResearchAssistant), {
  ssr: false,
});

type AssistantContextValue = {
  /** Open Research Assistant mode. Call from a click so the mic and audio playback are allowed. */
  openAssistant: () => void;
};

const AssistantContext = createContext<AssistantContextValue | null>(null);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <AssistantContext.Provider value={{ openAssistant: () => setOpen(true) }}>
      {children}
      {open && <ResearchAssistant onClose={() => setOpen(false)} />}
    </AssistantContext.Provider>
  );
}

export function useAssistant() {
  const ctx = useContext(AssistantContext);
  if (!ctx) throw new Error("useAssistant must be used inside <AssistantProvider>");
  return ctx;
}
