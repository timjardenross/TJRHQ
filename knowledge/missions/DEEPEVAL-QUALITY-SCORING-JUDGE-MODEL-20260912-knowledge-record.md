# Knowledge Record — deepeval score_output() gets a judge model and a caller, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | none (OSS-Gap-Solutions GAP 1 follow-up) |
| Title | The audit's P1 ("quality scoring dead") was half-solved and silently broken the other half |
| Date | 2026-09-12 |
| Lesson | LL-148 |

## Outcome

Tasked with wiring deepeval into `quality_scoring_service.py` because
`outcome_capture_service.py` defaults `quality_scoring_service=None` — the
audit's framing that "no LLM output is scored in production." Investigation
found this framing conflated two different scoring paths:

- `score_outcome()` (rule-based, maps outcome status to a 1.0-5.0
  effectiveness score) is fully wired and fires today from all three
  learning loops (`build_learning_loop.py:233`, `research_learning_loop.py:193`,
  `comms/comms_learning_loop.py:141`) — each constructs its own `QualityScoring`
  instance directly, bypassing `outcome_capture_service.py`'s optional
  `quality_scoring_service=None` parameter entirely. That default is a
  standard optional-dependency-injection default (gated by
  `if quality_scoring_service and outcome_id:`), not a disabled switch —
  flipping it would auto-construct a scorer for every caller of
  `record_outcome()` regardless of whether that's wanted, so it was left
  alone.
- `score_output()` (deepeval's `HallucinationMetric`, added `e27d1ead`,
  2026-08-23) is the actual dead path: zero callers anywhere, and even if
  called, `HallucinationMetric()` with no `model=` argument defaults to
  deepeval's OpenAI judge — `OPENAI_API_KEY` is not set anywhere on this
  platform, so every call would have silently failed (caught by
  `score_output()`'s own broad `except Exception`) and always returned
  `None`, indistinguishable from "nothing to score."

Also found: the audit's original write-target for these scores
(`quality_scores` table) was dropped outright in migration
`0183_drop_retired_dead_tables.sql` (2026-09-01) — `score_outcome()`'s
`INSERT INTO quality_scores` has therefore been silently failing in
production since that date too (caught by its own broad except, logged as
an error, not surfaced anywhere else). Out of scope for this fix (a
distinct bug in a different function), but recorded here so it isn't
rediscovered as a mystery later.

Fixed the real, in-scope gap:
1. Added `_ModelRouterJudge(DeepEvalBaseLLM)` in `quality_scoring_service.py`
   — a judge model backed by `core/model-router`'s `/api/model/escalate`
   endpoint (already availability-guarded, reasoning-capable) instead of
   deepeval's OpenAI default. Wired as `HallucinationMetric(..., model=_ModelRouterJudge())`.
2. Verified the HTTP contract against the real, running model-router (a
   plain "say hello" `escalate` call succeeded in 26s — using the local
   `mistral-small3.2:24b` fallback, confirming `glm-5.3:cloud` is still not
   pulled on this host, per EVO-0009). A full `score_output()` call
   (deepeval's own verdict-generation prompt, ~2000 chars including its
   JSON-schema instructions) did not complete within the router's own 300s
   `escalate` timeout. **Correction from an earlier draft of this record:**
   VM load (`/proc/loadavg` showed 11.08 on 8 cores at the time) was cited
   as the cause, but that's at most a compounding factor — the primary
   cause is almost certainly `escalate` always falling through to the slow,
   CPU-only 24B local model (same root cause as EVO-0009/PR #108's
   glm-5.3:cloud gap, surfacing again here). A short prompt fits in 300s on
   that fallback model; deepeval's much longer structured prompt likely
   does not, contention or no. **Practical consequence: shadow-mode
   score_output() calls will likely keep returning `None` in production
   until glm-5.3:cloud is actually pulled (an ops task, already tracked,
   not an engineering one) — the wiring is correct (verified by the unit
   tests below and the standalone HTTP-contract check), but its real-world
   yield depends on that separate, already-known gap closing first.**
   Re-test once glm-5.3:cloud is live.
3. Wired `score_output()`'s first real caller into `build_learning_loop.py`,
   deliberately **shadow-mode only** (compute + log, never persisted,
   default OFF via `QUALITY_SCORE_OUTPUT_SHADOW_ENABLED`, run in a
   background thread so a ~60-300s judge-model call can never block the
   actual decision/outcome write path). Matches
   `intelligence/scheduler.py`'s existing `shadow_mode=True` convention
   rather than inventing a new toggle pattern.
4. Extended `tests/test_b1c_quality_scoring.py` (+7 tests, all mocked, no
   network): `score_output()`'s hallucination-rate inversion, the
   judge-model wiring itself (regression test for the OpenAI-default bug),
   graceful `None` on failure/unavailability, and `_ModelRouterJudge`'s
   HTTP contract against `/api/model/escalate`.
5. Pinned `deepeval>=4.1.10` in `platform-runtime/requirements.txt` —
   installed since `e27d1ead`, never declared.
6. Narrowed (did not close) `config/evolution_watchlist.json`'s
   `retrieval-evaluation` entry — deepeval's `score_output()` is a real
   evaluation harness for LLM-output quality, but it checks
   hallucination/faithfulness against supplied context, not retrieval
   quality itself (what gets fetched), and has exactly one caller so far,
   in shadow mode.

## Lesson

"No LLM output is scored in production" and "the scoring code has no
caller" are different claims, and a fix aimed at the wrong one can look
complete while changing nothing observable. The audit's stated symptom
(`quality_scoring_service=None` default) was real but pointed at
`outcome_capture_service.py`'s optional-injection contract, not at
`score_output()`'s actual, more specific problem: a real function with a
default judge-model configuration that silently produces `None` on every
call, forever, with no distinguishing signal from "not called yet."

## Future Guidance

Any `except Exception: return None` (or equivalent silent-degrade) path
around an external judge/LLM call is invisible to normal testing unless a
test specifically asserts the *configuration* reaches the external call
correctly — not just that the function doesn't crash. `test_score_output_wires_model_router_judge_not_default`
exists specifically to catch a regression class that would otherwise
reintroduce this exact bug (someone removing the explicit `model=` kwarg
in a future refactor) without any test going red until someone notices the
scores are suspiciously always identical or always `None` in production.
