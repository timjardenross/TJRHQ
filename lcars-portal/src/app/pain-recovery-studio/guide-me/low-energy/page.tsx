"use client";

import { useState } from "react";

const steps = [
  {
    title: "Make one thing easier",
    body: "Put one non-essential demand down for the next ten minutes. Nothing else needs solving.",
    listen:
      "Put one non-essential demand down for the next ten minutes. Nothing else needs solving.",
  },
  {
    title: "Change the input",
    body: "Choose one small reduction: dim a screen, move somewhere quieter, or pause one conversation.",
    listen:
      "Choose one small reduction. Dim a screen, move somewhere quieter, or pause one conversation.",
  },
  {
    title: "Let this be enough",
    body: "You do not need to earn the next step. Notice whether there is a little more room, or simply stop here.",
    listen:
      "You do not need to earn the next step. Notice whether there is a little more room, or simply stop here.",
  },
];

export default function LowEnergyPage() {
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<"read" | "listen">("read");
  const [done, setDone] = useState(false);
  const [message, setMessage] = useState("");
  const current = steps[step];
  function listen() {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(
        new SpeechSynthesisUtterance(current.listen),
      );
      setMode("listen");
    }
  }
  function stopListening() {
    if (typeof window !== "undefined" && "speechSynthesis" in window)
      window.speechSynthesis.cancel();
    setMode("read");
  }
  async function save(patch: Record<string, unknown>) {
    try {
      const r = await fetch("/api/pain-recovery-studio/session", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      setMessage(r.ok ? "Saved to today’s guide." : "Kept for this screen.");
    } catch {
      setMessage("Kept for this screen.");
    }
  }
  function finish() {
    setDone(true);
    void save({
      current_action: "Low-energy guide completed.",
      action_status: "completed",
      learning_note: "Low-energy guide: one small reduction was offered.",
      adaptation_mode: "low",
    });
  }
  return (
    <main className="min-h-screen bg-[#eef3ef] px-4 py-6 text-[#193d46]">
      <div className="mx-auto max-w-xl">
        <nav aria-label="Breadcrumb">
          <a
            href="/pain-recovery-studio/start"
            className="inline-flex min-h-11 items-center text-sm font-semibold text-[#698078]"
          >
            ← What I need now
          </a>
        </nav>
        <p className="mt-5 text-xs font-semibold uppercase tracking-[0.18em] text-[#698078]">
          Guide me now · low energy
        </p>
        {done ? (
          <section
            className="mt-4 rounded-3xl bg-white p-6 shadow-sm"
            aria-labelledby="done-title"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#698078]">
              You are done for now
            </p>
            <h1 id="done-title" className="mt-3 font-serif text-4xl">
              Nothing else is required.
            </h1>
            <p className="mt-3 text-base leading-7 text-slate-600">
              You can return to this route later, or close the Studio. Stopping
              is a valid outcome.
            </p>
            <a
              href="/pain-recovery-studio"
              className="mt-6 inline-flex min-h-12 w-full items-center justify-center rounded-2xl bg-[#193d46] px-4 py-4 text-center font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#193d46]"
            >
              Return to today
            </a>
          </section>
        ) : (
          <section
            className="mt-4 rounded-3xl bg-white p-6 shadow-sm"
            aria-labelledby="energy-title"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold">One small route</span>
              <span
                className="text-sm text-slate-500"
                aria-label={`Step ${step + 1} of ${steps.length}`}
              >
                Step {step + 1} of {steps.length}
              </span>
            </div>
            <div
              className="mt-3 h-2 overflow-hidden rounded-full bg-[#d8e5df]"
              role="progressbar"
              aria-valuemin={1}
              aria-valuemax={steps.length}
              aria-valuenow={step + 1}
              aria-label={`Low-energy guide progress, step ${step + 1} of ${steps.length}`}
            >
              <div
                className="h-full bg-[#193d46] transition-all"
                style={{ width: `${((step + 1) / steps.length) * 100}%` }}
              />
            </div>
            <h1
              id="energy-title"
              className="mt-5 font-serif text-4xl leading-tight"
            >
              You have very little energy.
            </h1>
            <p className="mt-3 text-base leading-7 text-slate-600">
              Let’s make the next few minutes easier. You do not need to report
              anything before we begin.
            </p>
            <div
              className="mt-6 rounded-3xl bg-[#e1eee9] p-5"
              aria-live="polite"
            >
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#526b6c]">
                {current.title}
              </p>
              <p className="mt-3 text-xl leading-8">
                {mode === "listen"
                  ? "Listening is on. Use Stop listening if you want it to end."
                  : current.body}
              </p>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => {
                  stopListening();
                  setMode("read");
                }}
                aria-pressed={mode === "read"}
                className={
                  "min-h-12 rounded-xl border px-4 py-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#193d46] " +
                  (mode === "read" ? "bg-[#193d46] text-white" : "bg-white")
                }
              >
                Read this step
              </button>
              <button
                type="button"
                onClick={listen}
                aria-pressed={mode === "listen"}
                className={
                  "min-h-12 rounded-xl border px-4 py-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#193d46] " +
                  (mode === "listen" ? "bg-[#193d46] text-white" : "bg-white")
                }
              >
                Play spoken guidance
              </button>
            </div>
            {mode === "listen" && (
              <button
                type="button"
                onClick={stopListening}
                className="mt-2 min-h-12 w-full rounded-xl border border-[#8d3f35] px-4 py-3 text-sm font-semibold text-[#8d3f35] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#193d46]"
              >
                Stop listening
              </button>
            )}
            <div className="mt-6 grid gap-2">
              <button
                type="button"
                onClick={() => {
                  if (step === steps.length - 1) {
                    finish();
                  } else {
                    setStep(step + 1);
                    stopListening();
                  }
                }}
                className="min-h-12 rounded-2xl bg-[#193d46] px-4 py-4 font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#193d46]"
              >
                {step === steps.length - 1
                  ? "I’ve tried this"
                  : "Next small step"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setMessage("Okay. Nothing needs completing.");
                  void save({
                    action_status: "deferred",
                    current_action: "Low-energy route paused by user.",
                    adaptation_mode: "low",
                  });
                }}
                className="min-h-12 rounded-2xl border px-4 py-4 font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#193d46]"
              >
                Not possible right now
              </button>
              <button
                type="button"
                onClick={() => {
                  setMessage("The route is smaller now.");
                  void save({
                    action_status: "deferred",
                    current_action: "Low-energy route reduced to one step.",
                    adaptation_mode: "low",
                  });
                }}
                className="min-h-12 rounded-2xl border px-4 py-4 font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#193d46]"
              >
                Make this smaller
              </button>
            </div>
            <p className="mt-4 min-h-6 text-sm text-slate-500" role="status">
              {message}
            </p>
          </section>
        )}
        <p className="mt-5 text-center text-xs leading-5 text-slate-500">
          This guide does not judge symptoms or replace your care plan. If
          something is new, sudden, progressive or concerning, use your agreed
          safety pathway.
        </p>
      </div>
    </main>
  );
}
