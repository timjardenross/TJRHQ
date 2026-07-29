# Intelligence Brief Standard

The bar an Ops (OR Intelligence) Brief must clear before QA-pass. Written
against the fields that actually exist in `intelligence_briefs` and the
checks `intelligence/audit/brief_coherence.py` already runs — this
document describes the real pipeline, it does not invent a new one.

## Required fields, and what "done" means for each

- **executive_snapshot** — must be consistent with `top_events`: a reader
  who only sees this field should not be surprised by what's in the
  linked signal grid. (Automated check: `brief_coherence.py` check 1.)
- **emerging_themes** — must be grounded in actual signal patterns for
  the period, not restated boilerplate from a prior brief. (Check 2.)
- **forward_watch** — predictions must align with the trend data
  actually observed, not generic forward-looking language. (Check 3.)
- **cps230_implications** — populated whenever any linked signal has
  `cps230_relevance = true`; explicitly states the operational-resilience
  angle, not just a repeat of the executive_snapshot.
- **bottom_line** — a single sentence a Captain could act on without
  reading the rest of the brief.
- **overall_risk** — one of `RED` / `AMBER` / `GREEN` / `UNKNOWN` (the
  real live scale — not `HIGH`/`CRITICAL`/`LOW`/`MEDIUM`, which no
  production brief has ever actually used). Must be justified by the
  composition of `top_events` and `events_included`, not asserted alone.
- **signal_ids / top_events** — every referenced signal must resolve to
  a real, non-suppressed `intelligence_events` row for the brief's
  period.

## Automated pre-screen

Every brief in `IN_REVIEW` is scored nightly by
`intelligence/audit/brief_qa_agent.py::run_nightly()` (scheduled via
`intelligence/scheduler.py`, `brief_qa_agent_nightly`, 02:00 AEST). It
reuses `brief_coherence_checks()` 1–4 above, plus its own risk-accuracy
check against the real RED/AMBER/GREEN/UNKNOWN scale. This is a
pre-screen, not a replacement for human QA: a RED-rated brief always
fails the automated gate regardless of score and still requires a human
(`actor='intelligence_lead'`) to review and pass it.

## What "QA_PASSED" should mean

All six fields above are present, internally consistent per the
automated checks, and — for a RED brief specifically — have been
reviewed by a human who can be named in the audit trail
(`approval_audit.qa.approved_by`).

## What this standard does not cover

Health Intelligence (weekly synthesis) uses a different schema
(`health_insights`: `llm_narrative`, `deterministic_findings`,
`source_articles`) and is out of scope for this document. If a
Health-equivalent standard is needed, it should be written separately
rather than folded in here — the two pipelines are already
architecturally distinct.
