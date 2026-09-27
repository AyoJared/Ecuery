import { API_BASE, ApiError } from "./client";
import type { ConverseResponse, VoicesResponse } from "./types";

/** Send one recorded turn to Research Assistant mode. Pass the last conversation_id to keep context. */
export async function converse(
  audio: Blob,
  voice: string,
  conversationId: string | null,
  signal?: AbortSignal,
): Promise<ConverseResponse> {
  const form = new FormData();
  // The backend picks the decoder from the part's type; the extension is just for logs.
  form.append("audio", audio, `turn.${audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm"}`);
  form.append("voice", voice);
  if (conversationId) form.append("conversation_id", conversationId);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/voice/converse`, { method: "POST", body: form, signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("Couldn't reach the Ecuery server. Is the backend running?");
  }
  if (!res.ok) {
    const detail = await res
      .json()
      .then((body) => (typeof body?.detail === "string" ? body.detail : null))
      .catch(() => null);
    if (detail) throw new ApiError(detail, res.status);
    throw new ApiError(
      res.status >= 500
        ? "Ecuery's data service isn't responding right now. Please try again in a moment."
        : `Something went wrong (error ${res.status}).`,
      res.status,
    );
  }
  return res.json();
}

/** The voices the assistant can speak in, or null if the backend can't be reached. */
export async function fetchVoices(signal?: AbortSignal): Promise<VoicesResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/voice/voices`, { signal });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}
