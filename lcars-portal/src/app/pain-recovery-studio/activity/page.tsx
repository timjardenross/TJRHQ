"use client";
import { useEffect, useState } from "react";

type Route = "start" | "smaller" | "later" | "pause" | "alternative" | "resume";
const routes: Record<Route, { title: string; body: string }> = {
  start: {
    title: "Start Peter’s planned activity",
    body: "Use Peter’s instructions exactly as provided. The Studio will not add, remove or change exercise details.",
  },
  smaller: {
    title: "Use a smaller version",
    body: "Choose the smaller version already agreed in Peter’s plan, or contact Peter before changing the exercise itself.",
  },
  later: {
    title: "Move it later",
    body: "Set it aside without catch-up pressure. You can return when there is more room.",
  },
  pause: {
    title: "Pause the activity",
    body: "Stop and use your agreed safety pathway if something feels new, sudden, progressive or concerning.",
  },
  alternative: {
    title: "Protect the valued outcome another way",
    body: "Choose a small non-exercise version of what mattered today, such as time outdoors, connection or a useful task.",
  },
  resume: {
    title: "Resume from where you stopped",
    body: "Return only to the point and instructions already agreed with Peter. Do not compensate for the pause.",
  },
};
export default function ActivityPage() {
  const [route, setRoute] = useState<Route | null>(null);
  const [resumeRoute, setResumeRoute] = useState<Route | null>(null);
  const [saved, setSaved] = useState("");
  useEffect(() => {
    const stored = window.localStorage.getItem(
      "pain-recovery-activity-route",
    ) as Route | null;
    if (stored && routes[stored]) setResumeRoute(stored);
  }, []);
  async function choose(next: Route) {
    setRoute(next);
    setResumeRoute(null);
    window.localStorage.setItem("pain-recovery-activity-route", next);
    try {
      const r = await fetch("/api/pain-recovery-studio/session", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action_status:
            next === "start"
              ? "started"
              : next === "resume"
                ? "resumed"
                : next === "pause"
                  ? "paused"
                  : next === "alternative"
                    ? "alternative"
                    : "deferred",
          current_action: routes[next].title,
        }),
      });
      setSaved(
        r.ok
          ? "Saved to today’s guide."
          : "Kept for this screen until remote storage is enabled.",
      );
    } catch {
      setSaved("Kept for this screen until remote storage is enabled.");
    }
  }
  return (
    <main className="min-h-screen bg-[#eef3ef] px-4 py-6 text-[#193d46]">
      <div className="mx-auto max-w-xl">
        <nav aria-label="Breadcrumb">
          <a
            href="/pain-recovery-studio"
            className="inline-flex min-h-11 items-center text-sm font-semibold text-[#698078]"
          >
            ← Studio
          </a>
        </nav>
        <header className="mt-5">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#698078]">
            Activity guidance
          </p>
          <h1 className="mt-2 font-serif text-4xl leading-tight">
            How do you want to meet today’s activity?
          </h1>
          <p className="mt-3 text-base leading-7 text-slate-700">
            Peter’s channel manages the exercise plan. This Studio helps you
            choose a route around it without changing the plan or judging
            symptoms.
          </p>
        </header>
        {route ? (
          <section
            className="mt-6 rounded-3xl bg-white p-6 shadow-sm"
            aria-labelledby="route-title"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#698078]">
              Your route
            </p>
            <h2 id="route-title" className="mt-2 text-2xl font-semibold">
              {routes[route].title}
            </h2>
            <p className="mt-3 text-base leading-7 text-slate-700">
              {routes[route].body}
            </p>
            <p className="mt-4 min-h-6 text-sm text-slate-500" role="status">
              {saved}
            </p>
            <div className="mt-5 grid gap-2 sm:flex">
              <button
                onClick={() => setRoute(null)}
                className="min-h-12 rounded-xl border px-4 py-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#193d46]"
              >
                Choose another route
              </button>
              <a
                href="/pain-recovery-studio"
                className="inline-flex min-h-12 items-center justify-center rounded-xl bg-[#193d46] px-4 py-3 text-sm font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#193d46]"
              >
                Return to today
              </a>
            </div>
          </section>
        ) : (
          <section className="mt-6" aria-labelledby="route-options">
            <h2 id="route-options" className="sr-only">
              Choose one route
            </h2>
            {resumeRoute && (
              <div className="mb-4 rounded-2xl bg-[#fff8e8] p-4" role="status">
                <p className="text-sm font-semibold">
                  You have an unfinished route.
                </p>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  {routes[resumeRoute].title}. Resume it, choose another route
                  or stop for now.
                </p>
                <div className="mt-3 flex flex-wrap gap-3">
                  <button
                    onClick={() => choose(resumeRoute)}
                    className="min-h-11 rounded-xl bg-[#193d46] px-4 py-3 text-sm font-semibold text-white"
                  >
                    Resume
                  </button>
                  <button
                    onClick={() => {
                      window.localStorage.removeItem(
                        "pain-recovery-activity-route",
                      );
                      setResumeRoute(null);
                    }}
                    className="min-h-11 rounded-xl border px-4 py-3 text-sm font-semibold"
                  >
                    Start fresh
                  </button>
                </div>
              </div>
            )}
            <div className="grid gap-3">
              {(Object.keys(routes) as Route[]).map((key) => (
                <button
                  key={key}
                  onClick={() => choose(key)}
                  className="min-h-16 rounded-2xl bg-white p-4 text-left shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#193d46]"
                >
                  <span className="block text-base font-semibold">
                    {routes[key].title}
                  </span>
                  <span className="mt-1 block text-sm leading-5 text-slate-600">
                    {key === "alternative"
                      ? "Keep the valued outcome without changing Peter’s plan."
                      : key === "pause"
                        ? "Stop and use the safety pathway if needed."
                        : "One clear route, with no catch-up."}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}
        <p className="mt-6 text-xs leading-5 text-slate-500">
          If you have a question about the exercise itself, use Peter’s channel.
          The Studio does not prescribe, progress or assess exercise.
        </p>
      </div>
    </main>
  );
}
