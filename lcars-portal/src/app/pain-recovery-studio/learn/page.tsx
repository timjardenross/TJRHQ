"use client";
import { useEffect, useState } from "react";
import { contextHref, parseStep } from "@/lib/pain-recovery-continuity";
const lessons = [
  [
    "Pain is a whole-person experience",
    "Pain is real. The experience is shaped by the body, brain, emotions, relationships, and surroundings—not by one body part alone.",
    "understand",
  ],
  [
    "Find the ingredients",
    "Look for what turns the volume up: sleep disruption, stress, protective thoughts, isolation, too much demand, or an environment that keeps the alarm active.",
    "understand",
  ],
  [
    "Find the opposite ingredient",
    "For each ingredient, choose one small counter-move that is possible today. The aim is not perfection; it is changing the recipe by one ingredient.",
    "pace",
  ],
  [
    "Catch, check, change",
    "Catch the frightening thought. Check whether it is fact or fear. Change it into something more accurate and useful.",
    "understand",
  ],
  [
    "Build the healing cycle",
    "A helpful message can change emotion, behaviour, and the body’s response. Notice what you do next—not just what you feel.",
    "explore",
  ],
] as const;
export default function LearnPage() {
  const [step, setStep] = useState(0);
  const [resuming, setResuming] = useState(false);
  useEffect(() => {
    const saved = window.localStorage.getItem("pain-recovery-learning-step");
    if (saved !== null) {
      setStep(parseStep(saved, lessons.length));
      setResuming(true);
    }
  }, []);
  useEffect(() => {
    window.localStorage.setItem("pain-recovery-learning-step", String(step));
  }, [step]);
  const lesson = lessons[step];
  const resourcePath =
    lesson[2] === "pace"
      ? "/pain-recovery-studio/resources?need=pace"
      : lesson[2] === "understand"
        ? "/pain-recovery-studio/resources?need=understand"
        : "/pain-recovery-studio/resources";
  const resourceLink = contextHref(resourcePath, {
    source: "learning",
    label: lesson[0],
    returnPath: "/pain-recovery-studio/learn",
    step,
    total: lessons.length,
  });
  return (
    <main className="min-h-screen bg-[#f4f7f3] px-4 py-6 text-[#193d46]">
      <div className="mx-auto max-w-xl">
        <a href="/pain-recovery-studio" className="text-sm text-[#698078]">
          ← Back to today
        </a>
        <p className="mt-7 text-xs font-semibold uppercase tracking-[0.2em] text-[#698078]">
          Pain Recipe Journey
        </p>
        <h1 className="mt-2 font-serif text-4xl">
          Understand it. Change one ingredient.
        </h1>
        {resuming && (
          <p
            className="mt-3 rounded-2xl bg-[#fff8e8] p-3 text-sm text-slate-700"
            role="status"
          >
            You are back at step {step + 1}. Nothing needs repeating.
          </p>
        )}
        <div className="mt-6 rounded-3xl bg-[#193d46] p-6 text-white">
          <p className="text-xs uppercase tracking-[0.18em] text-[#c7dbd5]">
            Step {step + 1} of {lessons.length}
          </p>
          <h2 className="mt-3 font-serif text-3xl">{lesson[0]}</h2>
          <p className="mt-4 text-sm leading-7 text-[#d9e9e4]">{lesson[1]}</p>
        </div>
        <div
          className="mt-4 flex gap-2"
          aria-label={`Lesson progress: step ${step + 1} of ${lessons.length}`}
        >
          {lessons.map((_, i) => (
            <span
              key={i}
              className={`h-2 flex-1 rounded-full ${i <= step ? "bg-[#193d46]" : "bg-[#cbd9d3]"}`}
            />
          ))}
        </div>
        <div className="mt-5 rounded-3xl bg-white p-5 shadow-sm">
          <p className="text-sm leading-6 text-slate-600">
            {step < 2
              ? "When you are ready, add what you notice to your personal Pain Recipe."
              : step === 2
                ? "Then ask the Studio to help you choose the smallest counter-move."
                : step === 3
                  ? "You can use this whenever the Pain Voice starts making predictions."
                  : "The Studio will help you notice these links over time without turning your day into a spreadsheet."}
          </p>
          <div className="mt-4 rounded-2xl bg-[#eef3ef] p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#698078]">
              Take it further
            </p>
            <p className="mt-1 text-sm text-slate-700">
              Find an approved resource that matches this idea, without leaving
              the learning journey.
            </p>
            <a
              href={resourceLink}
              className="mt-3 inline-block text-sm font-semibold text-[#193d46]"
            >
              Browse related resources →
            </a>
          </div>
          <div className="mt-5 flex gap-2">
            <button
              disabled={step === 0}
              onClick={() => setStep(step - 1)}
              className="rounded-2xl border px-4 py-3 text-sm font-semibold disabled:opacity-40"
            >
              Back
            </button>
            {step < lessons.length - 1 ? (
              <button
                onClick={() => setStep(step + 1)}
                className="flex-1 rounded-2xl bg-[#193d46] px-4 py-3 text-sm font-semibold text-white"
              >
                Next idea
              </button>
            ) : (
              <a
                href="/pain-recovery-studio/recipe"
                className="flex-1 rounded-2xl bg-[#193d46] px-4 py-3 text-center text-sm font-semibold text-white"
              >
                Build my recipe
              </a>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
