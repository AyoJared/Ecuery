"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { API_MODE, askQuestion } from "@/lib/api/client";
import { isEventsAnswer, type AnsweredResponse, type AskResponse } from "@/lib/api/types";
import { eventTypeLabel } from "@/lib/event-types";
import { AnswerView } from "./AnswerView";
import { FollowUpInput } from "./FollowUpInput";
import { ThinkingSteps } from "./ThinkingSteps";

type Turn = {
  id: number;
  question: string;
  /** loading → (answer arrives) finishing → (thinking animation completes) done */
  phase: "loading" | "finishing" | "done";
  response?: AskResponse;
  error?: string;
};

// The search results page: the question, a "thinking" state, the answer, then a follow-up chat.
// Follow-ups reuse the backend conversation (conversation_id), so "what about Phoenix?" works.
export function ResultsExperience({ question }: { question: string }) {
  const [turns, setTurns] = useState<Turn[]>(() => [{ id: 0, question, phase: "loading" }]);
  const conversationId = useRef<string | null>(null);
  const nextId = useRef(1);
  const turnEls = useRef(new Map<number, HTMLElement>());

  const update = (id: number, patch: Partial<Turn>) =>
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch } : t)));

  async function fetchTurn(id: number, q: string, signal?: AbortSignal) {
    try {
      const res = await askQuestion(q, conversationId.current, signal);
      conversationId.current = res.conversation_id;
      update(id, { response: res, phase: "finishing" });
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      update(id, { error: (e as Error).message || "Something went wrong.", phase: "finishing" });
    }
  }

  // First question: fetched on mount (the page remounts this component for each new ?q=).
  useEffect(() => {
    const controller = new AbortController();
    fetchTurn(0, question, controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per mount by design
  }, []);

  function askFollowUp(q: string) {
    const id = nextId.current++;
    setTurns((all) => [...all, { id, question: q, phase: "loading" }]);
    fetchTurn(id, q);
  }

  function retry(turn: Turn) {
    update(turn.id, { phase: "loading", error: undefined, response: undefined });
    fetchTurn(turn.id, turn.question);
  }

  // Bring each new follow-up into view as it's asked.
  const lastId = turns[turns.length - 1].id;
  useEffect(() => {
    if (lastId === 0) return;
    turnEls.current.get(lastId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [lastId]);

  const [first, ...followUps] = turns;
  const busy = turns.some((t) => t.phase !== "done");
  const firstAnswer = first.response?.status === "answered" ? first.response : null;

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 px-4 pb-24 pt-8 sm:px-6 sm:pt-12">
      <Link href="/#ask" className="w-fit text-sm text-ink-muted transition-colors hover:text-ink">
        ← New search
      </Link>

      {API_MODE === "mock" && (
        <p className="rounded-2xl border border-sun/30 bg-sun/10 px-4 py-3 text-sm text-sun">
          Demo mode: the backend isn&apos;t connected, so these are sample answers, not answers to your exact question.
        </p>
      )}

      <motion.h1
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="text-balance text-3xl font-semibold tracking-[-0.03em] text-ink sm:text-5xl"
      >
        {question}
      </motion.h1>

      <TurnBody turn={first} onFinished={() => update(first.id, { phase: "done" })} onRetry={() => retry(first)} />

      {first.phase === "done" && !first.error && (
        <section aria-label="Follow-up questions" className="mt-6 flex flex-col gap-6 border-t border-line pt-10">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Keep exploring</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink">Ask a follow-up</h2>
          </div>

          <AnimatePresence initial={false}>
            {followUps.map((turn) => (
              <motion.article
                key={turn.id}
                ref={(el) => {
                  if (el) turnEls.current.set(turn.id, el);
                  else turnEls.current.delete(turn.id);
                }}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex scroll-mt-24 flex-col gap-4"
              >
                <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-surface-raised px-4 py-3 text-ink">
                  {turn.question}
                </p>
                <div className="rounded-3xl border border-line bg-surface/40 p-4 sm:p-6">
                  <TurnBody
                    turn={turn}
                    compact
                    onFinished={() => update(turn.id, { phase: "done" })}
                    onRetry={() => retry(turn)}
                  />
                </div>
              </motion.article>
            ))}
          </AnimatePresence>

          <FollowUpInput
            disabled={busy}
            onSubmit={askFollowUp}
            suggestions={followUps.length === 0 ? suggestionsFor(firstAnswer) : []}
          />
        </section>
      )}
    </div>
  );
}

function TurnBody({
  turn,
  compact = false,
  onFinished,
  onRetry,
}: {
  turn: Turn;
  compact?: boolean;
  onFinished: () => void;
  onRetry: () => void;
}) {
  if (turn.phase !== "done") {
    return <ThinkingSteps done={turn.phase === "finishing"} onFinished={onFinished} compact={compact} />;
  }
  if (turn.error) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-sun/30 bg-sun/10 p-5">
        <p className="text-sm text-sun">{turn.error}</p>
        <button
          onClick={onRetry}
          className="rounded-full border border-sun/40 px-4 py-1.5 text-sm text-sun transition-colors hover:bg-sun/15"
        >
          Try again
        </button>
      </div>
    );
  }
  const res = turn.response!;
  if (res.status === "needs_clarification") {
    return (
      <div className="flex gap-3 rounded-2xl border border-line bg-surface/60 p-5">
        <span className="mt-0.5 size-2 shrink-0 rounded-full bg-accent" />
        <p className="text-base leading-relaxed text-ink">{res.clarification}</p>
      </div>
    );
  }
  return <AnswerView answer={res} compact={compact} />;
}

/** Starter follow-ups based on what the first answer covered. */
function suggestionsFor(answer: AnsweredResponse | null): string[] {
  if (!answer) return ["PM2.5 in Chicago last week", "Was last month hotter than usual in Phoenix?"];
  if (isEventsAnswer(answer)) {
    const type = eventTypeLabel(answer.plan.event_types[0] ?? "event").toLowerCase();
    return [
      "How does that compare to last year?",
      answer.plan.place ? `What about ${type}s worldwide?` : `What about ${type}s in the US?`,
      "Which one caused the most damage?",
    ];
  }
  const place = answer.plan.locations.map((l) => answer.plan.places[l]?.label).find((l) => l && !/global/i.test(l));
  const out: string[] = [];
  if (answer.plan.operation !== "compare_history") out.push("How does that compare to past years?");
  out.push("What about the last 30 days?");
  out.push(place ? "What about a nearby city?" : "What about New York?");
  return out;
}
