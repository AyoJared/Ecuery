"use client";

import { AnimatePresence, motion, useMotionValue, useTransform } from "motion/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AnswerChart } from "@/components/results/AnswerChart";
import { SourceLinks } from "@/components/results/SourceLinks";
import { saveHandoff } from "@/lib/answer-handoff";
import type { VoiceOption } from "@/lib/api/types";
import { fetchVoices } from "@/lib/api/voice";
import { exampleQueries } from "@/lib/example-queries";
import {
  AssistantSession,
  assistantSupported,
  type AssistantState,
  type AssistantTurn,
} from "@/lib/voice/assistant-session";

const VOICE_KEY = "ecuery:assistant-voice";

const statusCopy: Record<AssistantState, { title: string; hint: string }> = {
  starting: { title: "Starting…", hint: "Allow microphone access if your browser asks." },
  listening: { title: "Listening", hint: "Ask about any place and time range, then pause." },
  hearing: { title: "Listening…", hint: "Pause when you're done and I'll answer." },
  thinking: { title: "Looking into it", hint: "Checking the data for your question." },
  speaking: { title: "Speaking", hint: "Tap the orb or press space to interrupt." },
  paused: { title: "Paused", hint: "Tap the orb or press space to talk." },
  error: { title: "Something went wrong", hint: "" },
};

// Orb color per state: leaf while it's your turn, sun while it's talking, dim when paused.
const orbColor: Record<AssistantState, string> = {
  starting: "var(--color-ink-faint)",
  listening: "var(--color-accent)",
  hearing: "var(--color-accent)",
  thinking: "var(--color-accent-soft)",
  speaking: "var(--color-sun)",
  paused: "var(--color-ink-faint)",
  error: "var(--color-wildfire)",
};

const orbLabel: Record<AssistantState, string> = {
  starting: "Starting microphone",
  listening: "Listening",
  hearing: "Send now",
  thinking: "Working on your answer",
  speaking: "Interrupt and talk",
  paused: "Start talking",
  error: "Try again",
};

export function ResearchAssistant({ onClose }: { onClose: () => void }) {
  const [supported] = useState(assistantSupported);
  const [state, setState] = useState<AssistantState>("starting");
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [voices, setVoices] = useState<VoiceOption[]>([]);
  const [voiceMode, setVoiceMode] = useState<string | null>(null);
  const [voice, setVoice] = useState(readSavedVoice);
  const level = useMotionValue(0);
  const session = useRef<AssistantSession | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const transcriptEnd = useRef<HTMLDivElement>(null);

  // One session per open. Voice changes are passed in separately, so they don't restart it.
  useEffect(() => {
    if (!supported) return;
    const s = new AssistantSession(readSavedVoice(), {
      onState: (next) => {
        setState(next);
        if (next !== "error") setError(null);
      },
      onTurn: (turn) => setTurns((all) => [...all, turn]),
      onError: setError,
      onLevel: (v) => level.set(v),
    });
    session.current = s;
    s.start();
    return () => {
      s.close();
      session.current = null;
    };
  }, [supported, level]);

  useEffect(() => {
    const controller = new AbortController();
    fetchVoices(controller.signal).then((res) => {
      if (!res) return;
      setVoices(res.voices);
      setVoiceMode(res.mode);
    });
    return () => controller.abort();
  }, []);

  // Modal behavior: lock page scroll, focus the dialog, Escape closes, space talks.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      const target = e.target as HTMLElement;
      if (e.code === "Space" && !["BUTTON", "SELECT", "INPUT", "A"].includes(target.tagName)) {
        e.preventDefault();
        session.current?.tap();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  // Keep the newest turn in view (but leave the intro alone before the first one).
  useEffect(() => {
    if (turns.length) transcriptEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length]);

  function changeVoice(key: string) {
    setVoice(key);
    session.current?.setVoice(key);
    try {
      localStorage.setItem(VOICE_KEY, key);
    } catch {}
  }

  const status = statusCopy[state];
  const active = state !== "paused" && state !== "error" && state !== "starting";

  return (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-labelledby="assistant-title"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.25 }}
      className="fixed inset-0 z-[60] flex flex-col overflow-hidden bg-canvas"
    >
      {/* Ambient light behind the orb, in the current state's color */}
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-[30%] -z-0 size-[44rem] max-w-[140vw] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-[0.13] blur-3xl transition-[background] duration-700 lg:left-[24%] lg:top-1/2"
        style={{ background: `radial-gradient(closest-side, ${orbColor[state]}, transparent)` }}
      />

      <header className="relative flex h-16 shrink-0 items-center justify-between gap-4 border-b border-line px-4 sm:px-6">
        <div className="flex min-w-0 items-baseline gap-3">
          <h2 id="assistant-title" className="truncate text-base font-semibold tracking-tight text-ink">
            Research Assistant
          </h2>
          {voiceMode === "mock" && (
            <span className="hidden text-xs text-ink-faint sm:inline" title="Add ELEVENLABS_API_KEY to the backend for real speech">
              Voice preview mode
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {voices.length > 0 && (
            <label className="flex items-center gap-2 text-sm text-ink-muted">
              <span className="hidden sm:inline">Voice</span>
              <select
                value={voice}
                onChange={(e) => changeVoice(e.target.value)}
                className="rounded-full border border-line-strong bg-surface px-3 py-1.5 text-sm text-ink focus:outline-none focus-visible:border-accent/60"
              >
                {voices.map((v) => (
                  <option key={v.key} value={v.key}>
                    {v.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            ref={closeButton}
            onClick={onClose}
            aria-label="End session and close"
            className="grid size-9 place-items-center rounded-full border border-line-strong text-ink-muted transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" aria-hidden>
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </div>
      </header>

      <div className="relative grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:grid-rows-1">
        {/* Orb + status + controls */}
        <section className="flex flex-col items-center justify-center gap-6 border-b border-line px-4 py-8 sm:py-10 lg:border-b-0 lg:border-r">
          {supported ? (
            <>
              <Orb state={state} level={level} onTap={() => session.current?.tap()} />
              <div className="flex min-h-[4.5rem] max-w-sm flex-col items-center gap-1.5 text-center" aria-live="polite">
                <p className="text-xl font-semibold tracking-tight text-ink">{status.title}</p>
                <p className="text-pretty text-sm leading-relaxed text-ink-muted">
                  {state === "error" ? error : status.hint}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {active ? (
                  <button onClick={() => session.current?.pause()} className={secondaryButton}>
                    Pause
                  </button>
                ) : (
                  <button onClick={() => session.current?.tap()} disabled={state === "starting"} className={secondaryButton}>
                    {state === "error" ? "Try again" : "Resume"}
                  </button>
                )}
                <button onClick={onClose} className={secondaryButton}>
                  End session
                </button>
              </div>
            </>
          ) : (
            <div className="flex max-w-sm flex-col items-center gap-2 text-center">
              <p className="text-xl font-semibold tracking-tight text-ink">Voice isn&apos;t available here</p>
              <p className="text-sm leading-relaxed text-ink-muted">
                This browser can&apos;t record audio. Open Ecuery in a recent version of Chrome, Edge, Safari or Firefox to
                talk to the assistant.
              </p>
            </div>
          )}
        </section>

        {/* Conversation */}
        <section aria-label="Conversation" className="min-h-0 overflow-y-auto overscroll-contain px-4 py-8 sm:px-8 lg:py-12">
          <div className="mx-auto flex max-w-2xl flex-col gap-8">
            {turns.length === 0 ? (
              <EmptyState />
            ) : (
              <AnimatePresence initial={false}>
                {turns.map((turn) => (
                  <Turn key={turn.id} turn={turn} onOpenAnswer={onClose} />
                ))}
              </AnimatePresence>
            )}
            <div ref={transcriptEnd} />
          </div>
        </section>
      </div>
    </motion.div>
  );
}

const secondaryButton =
  "rounded-full border border-line-strong px-4 py-2 text-sm text-ink transition-colors hover:bg-surface-raised disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

type OrbProps = { state: AssistantState; level: ReturnType<typeof useMotionValue<number>>; onTap: () => void };

// The one animated thing on screen: it swells with whoever is talking.
function Orb({ state, level, onTap }: OrbProps) {
  const color = orbColor[state];
  const haloScale = useTransform(level, (v) => 1 + v * 0.55);
  const haloOpacity = useTransform(level, (v) => 0.18 + v * 0.5);
  const coreScale = useTransform(level, (v) => 1 + v * 0.12);

  return (
    <button
      onClick={onTap}
      aria-label={orbLabel[state]}
      disabled={state === "starting" || state === "thinking"}
      className="group relative grid size-44 place-items-center rounded-full focus-visible:outline-none sm:size-52"
      style={{ ["--orb" as string]: color }}
    >
      <motion.span
        aria-hidden
        className="absolute inset-0 rounded-full transition-colors duration-500"
        style={{ scale: haloScale, opacity: haloOpacity, background: "radial-gradient(closest-side, var(--orb), transparent)" }}
      />
      {state === "thinking" && (
        <span
          aria-hidden
          className="absolute inset-3 animate-spin rounded-full [animation-duration:2.4s] [background:conic-gradient(from_0deg,transparent_0_70%,var(--orb))] [mask:radial-gradient(closest-side,transparent_calc(100%-3px),#000_calc(100%-2px))]"
        />
      )}
      <motion.span
        aria-hidden
        className="relative grid size-28 place-items-center rounded-full border transition-[border-color,box-shadow] duration-500 group-focus-visible:ring-2 group-focus-visible:ring-accent group-focus-visible:ring-offset-4 group-focus-visible:ring-offset-canvas sm:size-32"
        style={{
          scale: coreScale,
          borderColor: "color-mix(in srgb, var(--orb) 55%, transparent)",
          background: "radial-gradient(circle at 35% 30%, color-mix(in srgb, var(--orb) 38%, var(--color-surface-raised)), var(--color-surface) 70%)",
          boxShadow: "0 0 40px color-mix(in srgb, var(--orb) 30%, transparent), inset 0 1px 0 rgb(255 255 255 / 0.08)",
        }}
      >
        <OrbIcon state={state} />
      </motion.span>
    </button>
  );
}

function OrbIcon({ state }: { state: AssistantState }) {
  const common = "size-8 text-[var(--orb)] transition-colors duration-500";
  if (state === "speaking") {
    return (
      <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" aria-hidden>
        <path d="M5 10v4M9 7v10M13 4v16M17 8v8M21 11v2" />
      </svg>
    );
  }
  return (
    <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col gap-6 lg:pt-16">
      <div className="flex flex-col gap-3">
        <h3 className="text-balance text-3xl font-semibold tracking-[-0.03em] text-ink sm:text-4xl">
          Talk through a question out loud.
        </h3>
        <p className="max-w-lg text-pretty leading-relaxed text-ink-muted">
          Ask something, then pause. I&apos;ll answer out loud, show the chart here, and keep listening, so you can follow up
          with things like &ldquo;what about last year?&rdquo;
        </p>
      </div>
      <div className="flex flex-col gap-2">
        <p className="text-sm text-ink-faint">You could ask</p>
        <ul className="flex flex-col gap-2">
          {exampleQueries.slice(0, 3).map((q) => (
            <li key={q} className="text-ink-muted">
              &ldquo;{q}&rdquo;
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Turn({ turn, onOpenAnswer }: { turn: AssistantTurn; onOpenAnswer: () => void }) {
  const { response } = turn;
  const answer = response.answer;

  return (
    <motion.article
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col gap-4"
    >
      <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-surface-raised px-4 py-3 text-ink">
        {turn.question || <span className="text-ink-muted">(inaudible)</span>}
      </p>
      <div className="flex flex-col gap-4">
        <p className="text-pretty text-lg leading-relaxed text-ink">{response.reply}</p>
        {answer?.chart && (
          <div className="rounded-2xl border border-line bg-surface/50 p-4">
            {answer.chart.title && <p className="mb-3 text-sm font-medium text-ink-muted">{answer.chart.title}</p>}
            <AnswerChart chart={answer.chart} height={200} />
          </div>
        )}
        {answer && <SourceLinks links={answer.source_links} />}
        {answer && (
          <Link
            href={`/search?q=${encodeURIComponent(turn.question)}`}
            // Hand over the answer we already have (so /search doesn't ask again), then close:
            // from /search itself the overlay would otherwise stay open over the new answer.
            onClick={() => {
              saveHandoff(turn.question, answer);
              onOpenAnswer();
            }}
            className="w-fit text-sm text-accent transition-colors hover:text-accent-soft"
          >
            Open the full answer with sources
          </Link>
        )}
      </div>
    </motion.article>
  );
}

function readSavedVoice() {
  try {
    return localStorage.getItem(VOICE_KEY) || "rachel";
  } catch {
    return "rachel";
  }
}
