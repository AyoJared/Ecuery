import { audioSrc } from "@/lib/api/client";
import type { ConverseResponse } from "@/lib/api/types";
import { converse } from "@/lib/api/voice";

// The hands-free loop behind Research Assistant mode:
//   listening (waiting for speech) → hearing (recording) → thinking (backend) → speaking → listening …
// Speech start/end is detected from mic volume, so nobody has to press a button per turn.

export type AssistantState = "starting" | "listening" | "hearing" | "thinking" | "speaking" | "paused" | "error";

export type AssistantTurn = { id: number; question: string; response: ConverseResponse };

type Callbacks = {
  onState: (state: AssistantState) => void;
  onTurn: (turn: AssistantTurn) => void;
  onError: (message: string) => void;
  /** 0–1 loudness of whoever is talking (mic while listening, the voice while speaking), ~60×/s. */
  onLevel: (level: number) => void;
};

// Voice activity detection, tuned for a laptop mic in a normal room.
const MIN_SPEECH_THRESHOLD = 0.018; // RMS below this is never speech
const NOISE_MULTIPLIER = 2.6; // speech must be this much louder than the room's noise floor
const END_OF_TURN_SILENCE_MS = 1300; // pause long enough to count as "done talking"
const MIN_SPEECH_MS = 350; // ignore coughs and clicks
const MAX_TURN_MS = 30_000; // backend accepts ~a minute; keep turns snappy
const IDLE_TIMEOUT_MS = 20_000; // stop listening if nobody says anything

const RECORDER_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

export function assistantSupported() {
  return typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
}

export class AssistantSession {
  private state: AssistantState = "starting";
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private micAnalyser: AnalyserNode | null = null;
  private outAnalyser: AnalyserNode | null = null;
  private audio: HTMLAudioElement | null = null;
  private recorder: MediaRecorder | null = null;
  private request: AbortController | null = null;
  private raf = 0;
  private closed = false;
  private turnId = 0;
  private conversationId: string | null = null;

  constructor(
    private voice: string,
    private cb: Callbacks,
  ) {}

  setVoice(voice: string) {
    this.voice = voice;
  }

  /** Must be called from a user gesture (click), so audio playback and the mic are allowed. */
  async start() {
    this.setState("starting");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (e) {
      const name = (e as Error).name;
      this.fail(
        name === "NotAllowedError" || name === "SecurityError"
          ? "Microphone access is blocked. Allow it for this site in your browser's settings, then try again."
          : name === "NotFoundError"
            ? "No microphone was found. Connect one and try again."
            : "Couldn't start the microphone. Try again.",
      );
      return;
    }
    if (this.closed) return this.teardown();

    this.ctx = new AudioContext();
    await this.ctx.resume();
    this.micAnalyser = this.ctx.createAnalyser();
    this.micAnalyser.fftSize = 1024;
    this.ctx.createMediaStreamSource(this.stream).connect(this.micAnalyser);

    // One reusable player, unlocked by this gesture, routed through an analyser for the orb.
    this.audio = new Audio();
    this.audio.crossOrigin = "anonymous";
    this.outAnalyser = this.ctx.createAnalyser();
    this.outAnalyser.fftSize = 1024;
    const source = this.ctx.createMediaElementSource(this.audio);
    source.connect(this.outAnalyser);
    this.outAnalyser.connect(this.ctx.destination);

    this.listen();
  }

  /** The orb button: talk now / send now / interrupt / resume, depending on what's happening. */
  tap() {
    switch (this.state) {
      case "listening":
        return; // already waiting for speech
      case "hearing":
        return this.recorder?.stop(); // send what we have
      case "speaking":
        this.audio?.pause();
        return this.listen(); // barge in
      case "paused":
        return this.listen();
      case "error":
        return this.stream ? this.listen() : this.start();
    }
  }

  pause() {
    this.request?.abort();
    this.audio?.pause();
    this.stopRecorder(true);
    this.stopMeter();
    this.setState("paused");
  }

  close() {
    this.closed = true;
    this.teardown();
  }

  // ---------- listening ----------

  private listen() {
    if (this.closed || !this.stream || !this.micAnalyser) return;
    this.stopRecorder(true);
    this.setState("listening");

    const mimeType = RECORDER_TYPES.find((t) => MediaRecorder.isTypeSupported(t));
    const recorder = new MediaRecorder(this.stream, mimeType ? { mimeType } : undefined);
    const chunks: Blob[] = [];
    let heardSpeech = false;
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = () => {
      if (this.recorder !== recorder || recorder.discarded) return;
      this.recorder = null;
      this.stopMeter();
      if (!heardSpeech) return this.setState("paused");
      this.send(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
    };
    this.recorder = recorder;
    recorder.start(250);

    // Learn the room's noise floor for the first moment, then watch for speech and the pause after it.
    const buf = new Float32Array(this.micAnalyser.fftSize);
    const startedAt = performance.now();
    let noiseFloor = 0.008;
    let speechStartedAt = 0;
    let lastVoiceAt = 0;

    this.meter(() => {
      this.micAnalyser!.getFloatTimeDomainData(buf);
      const level = rms(buf);
      const now = performance.now();
      const threshold = Math.max(MIN_SPEECH_THRESHOLD, noiseFloor * NOISE_MULTIPLIER);

      if (level > threshold) {
        if (!speechStartedAt) speechStartedAt = now;
        lastVoiceAt = now;
        if (!heardSpeech && now - speechStartedAt > MIN_SPEECH_MS) {
          heardSpeech = true;
          this.setState("hearing");
        }
      } else {
        // Slowly track the room noise while nobody is speaking.
        if (!heardSpeech) noiseFloor = noiseFloor * 0.97 + level * 0.03;
        if (!heardSpeech && speechStartedAt && now - lastVoiceAt > 250) speechStartedAt = 0; // was just a blip
      }

      const done =
        (heardSpeech && now - lastVoiceAt > END_OF_TURN_SILENCE_MS) ||
        (heardSpeech && now - startedAt > MAX_TURN_MS) ||
        (!heardSpeech && now - startedAt > IDLE_TIMEOUT_MS);
      if (done && recorder.state === "recording") recorder.stop();

      return Math.min(1, level * 7);
    });
  }

  // ---------- thinking ----------

  private async send(audio: Blob) {
    this.setState("thinking");
    this.request = new AbortController();
    let response: ConverseResponse;
    try {
      response = await converse(audio, this.voice, this.conversationId, this.request.signal);
    } catch (e) {
      if ((e as Error).name === "AbortError" || this.closed) return;
      return this.fail((e as Error).message || "Something went wrong.");
    }
    if (this.closed) return;
    this.conversationId = response.conversation_id;
    if (response.transcript || response.answer) {
      this.cb.onTurn({ id: this.turnId++, question: response.transcript, response });
    }
    this.speak(response);
  }

  // ---------- speaking ----------

  private speak(response: ConverseResponse) {
    const src = audioSrc(response.speech_url);
    if (!src || !this.audio || !this.outAnalyser) return this.listen();

    const audio = this.audio;
    const buf = new Uint8Array(this.outAnalyser.fftSize);
    const finish = () => {
      audio.onended = audio.onerror = null;
      if (!this.closed && this.state === "speaking") this.listen();
    };
    audio.onended = finish;
    audio.onerror = finish; // no voice (e.g. TTS down): carry on listening
    audio.src = src;
    this.setState("speaking");
    audio.play().catch(finish);

    this.meter(() => {
      this.outAnalyser!.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += ((v - 128) / 128) ** 2;
      return Math.min(1, Math.sqrt(sum / buf.length) * 5);
    });
  }

  // ---------- plumbing ----------

  private meter(read: () => number) {
    this.stopMeter();
    let smooth = 0;
    const tick = () => {
      smooth += (read() - smooth) * 0.35;
      this.cb.onLevel(smooth);
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  private stopMeter() {
    cancelAnimationFrame(this.raf);
    this.cb.onLevel(0);
  }

  private stopRecorder(discard: boolean) {
    const recorder = this.recorder;
    if (!recorder) return;
    this.recorder = null;
    if (discard) recorder.discarded = true;
    if (recorder.state !== "inactive") recorder.stop();
  }

  private setState(state: AssistantState) {
    this.state = state;
    if (!this.closed) this.cb.onState(state);
  }

  private fail(message: string) {
    this.stopMeter();
    this.setState("error");
    this.cb.onError(message);
  }

  private teardown() {
    this.request?.abort();
    this.stopRecorder(true);
    cancelAnimationFrame(this.raf);
    if (this.audio) {
      this.audio.onended = this.audio.onerror = null;
      this.audio.pause();
      this.audio.removeAttribute("src");
    }
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close().catch(() => {});
    this.stream = null;
    this.ctx = null;
  }
}

function rms(buf: Float32Array) {
  let sum = 0;
  for (const v of buf) sum += v * v;
  return Math.sqrt(sum / buf.length);
}

declare global {
  interface MediaRecorder {
    /** Set when we stop a recording we don't want to send (pause, barge-in, close). */
    discarded?: boolean;
  }
}
