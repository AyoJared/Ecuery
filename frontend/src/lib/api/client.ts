import { mockAsk } from "./mock";
import type { AskResponse } from "./types";

/**
 * "live" calls the FastAPI backend through the /api/ecuery proxy (see next.config.ts).
 * "mock" (the default) answers with sample data in the backend's exact response shape,
 * so the UI works before the backend is running. Set NEXT_PUBLIC_API_MODE=live to switch.
 */
export const API_MODE: "live" | "mock" = process.env.NEXT_PUBLIC_API_MODE === "live" ? "live" : "mock";

const API_BASE = "/api/ecuery";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

/** Ask a question. Pass the previous response's conversation_id to ask a follow-up. */
export async function askQuestion(
  question: string,
  conversationId: string | null,
  signal?: AbortSignal,
): Promise<AskResponse> {
  if (API_MODE === "mock") return mockAsk(question, conversationId, signal);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, conversation_id: conversationId }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("Couldn't reach the Ecuery server. Is the backend running?");
  }
  if (!res.ok) {
    // FastAPI errors look like {"detail": "..."}; the proxy returns HTML/empty when the backend is down.
    const detail = await res
      .json()
      .then((body) => (typeof body?.detail === "string" ? body.detail : null))
      .catch(() => null);
    if (detail) throw new ApiError(detail, res.status);
    if (res.status >= 500) {
      // With the backend down, the /api/ecuery proxy answers with a bare 500.
      if (process.env.NODE_ENV === "development") {
        console.warn("[ecuery] Backend not reachable. Start it with `python main.py` in backend/ (ECUERY_API_URL).");
      }
      throw new ApiError("Ecuery's data service isn't responding right now. Please try again in a moment.", res.status);
    }
    throw new ApiError(`Something went wrong (error ${res.status}).`, res.status);
  }
  return res.json();
}

/** URL the browser can play for an answer's spoken version, or null when voice isn't available. */
export function audioSrc(audioUrl: string | undefined): string | null {
  return API_MODE === "live" && audioUrl ? `${API_BASE}${audioUrl}` : null;
}
