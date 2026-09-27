import type { AskResponse } from "@/lib/api/types";

// Lets another view (the Research Assistant) hand an answer it already has to /search, so the
// results page shows it instantly and continues the same conversation instead of asking again.

const KEY = "ecuery:answer-handoff";
const MAX_AGE_MS = 10 * 60 * 1000;

type Handoff = { question: string; response: AskResponse; savedAt: number };

export function saveHandoff(question: string, response: AskResponse) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ question, response, savedAt: Date.now() } satisfies Handoff));
  } catch {
    // Storage full or blocked: /search just asks the question again.
  }
}

/** The handed-off answer for this question, if there is a fresh one. */
export function readHandoff(question: string): AskResponse | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const handoff = JSON.parse(raw) as Handoff;
    if (handoff.question !== question || Date.now() - handoff.savedAt > MAX_AGE_MS) return null;
    return handoff.response;
  } catch {
    return null;
  }
}
