# Mission Brief

## Mission Header

- **Mission ID:** _unminted_ — mint on the VM with `python3 tools/mint_id.py MSN`
  before starting, then rename this file to `USS-TJR-MSN-XXXX-tev1-suppression-audit-shadow.md`
  and replace this line. (Not minted at drafting time: the brief was written in a
  cloud sandbox whose `.id-counters.json` is not the VM's.)
- **Priority:** P3 — a scoped, log-only pilot. Nothing user-facing depends on it.
- **Source:** Captain request (2026-10-03): evaluate Ollama 0.35's local "decision
  models" (System One API, `/v1/systemone`) without adding cloud cost or VM load.
  A repo-wide fit survey ranked candidates; this mission pilots the single
  lowest-risk one: the daily Technical OSINT suppression audit
  (`tools/intelligence/suppression_audit.py`) on **Together AI's Tev1 4B** (`tev1:4b`).

### Background (read once, then verify — see Pre-flight 2)

- Ollama ≥ 0.35 exposes `POST /v1/systemone`: send a `state` (text) plus named
  typed `questions` (`choice` with named `criteria`, yes/no, or `score` against a
  rubric); get back structured answers **with probabilities**. No text
  generation, no thinking tokens. Published example:
  ```json
  {"model": "nimble",
   "state": "Our checkout has returned 500 errors since 9am.",
   "questions": {"label": {"type": "choice",
     "instructions": "Which label fits this ticket?",
     "criteria": {"billing": "Payments and refunds", "bug": "Software errors",
                  "account": "Login and account access"}}}}
  ```
  The exact **response** JSON shape was not verifiable from the drafting sandbox
  (docs.ollama.com blocked) — Stream 1 captures it for real.
- Why this job: it is **log-only** (writes verdicts to `audit_events`,
  `category='intelligence_suppression_audit'`, never unsuppresses anything),
  bounded (≤60 short items/day, `_DEFAULT_LIMIT = 60`), already a 3-way choice
  (`AGREE` / `DISAGREE` / `UNCERTAIN`, "default to UNCERTAIN over guessing"), and
  runs today as Gemini → Mistral → Ollama `qwen3:8b` via `core/llm/provider_chain.py`.
- Why Tev1 4B and not Nimble 9B / Clef: the VM is CPU-only and runs hot
  (single Ollama slot). `core/security/guardrails/config/config.yml:15-30`
  documents vision-projector and thinking-model overhead making a single
  yes/no check take 73–241 s. Tev1 4B is the smallest credible text-only option.
  Clef is multimodal — likely to hit the same projector cost; do not use it here.

## Pre-flight

1. [ ] **Existing-entry check.** This mission adds (a) a new provider function to
   `core/llm/provider_chain.py`, (b) possibly a moved cron slot in
   `intelligence/scheduler.py`, (c) new env flags. Run and paste:
   ```
   grep -rn "systemone\|tev1\|call_systemone" --include=*.py .
   grep -n "^def call_" core/llm/provider_chain.py
   grep -rn "SUPPRESSION_AUDIT_" --include=*.py --include=*.env* --include=*.service .
   grep -n "CronTrigger(hour=" intelligence/scheduler.py
   ```
   Expected at drafting time: no `systemone`/`tev1` hits; `call_gemini`,
   `call_mistral`, `call_ollama` only; no `SUPPRESSION_AUDIT_` flags. If any
   already exist, stop and reconcile rather than adding a second one.
   Do **not** add a new scheduler instance (AGENTS.md "Scheduled jobs") — only
   move the existing `intelligence_suppression_audit` job's trigger.
2. [ ] **Premise verification.** Verify each against the live VM, record
   claimed → actual:
   - Suppression audit is scheduled 06:40 daily, `--days 1`, subprocess timeout
     900 s (`intelligence/scheduler.py` ~L407 and `_suppression_audit_job`).
   - It is still log-only and still uses the Gemini → Mistral → Ollama chain.
   - Current installed Ollama version (`ollama --version`) and how it is
     installed/supervised (`systemctl status ollama`, unit file, install method)
     — needed for the upgrade and its rollback.
   - `OLLAMA_KEEP_ALIVE=0` is set system-wide (per `config.yml:58-66`) — this
     means **every request reloads the model**; see Stream 1 step 4.
   - Free RAM headroom with the usual resident models (`ollama ps`, `free -h`).
   - Which time slots are actually quiet (load average history / `sar` if
     available, plus the scheduler's own cron list). The 06:00–06:45 window is
     known-busy (collection 06:00, scoring 06:15, jobs at 06:30/06:45).
   - Both "eval sets" are **unlabelled**: `tools/intelligence/eval_set.jsonl`
     (38 rows, every `human_label` null; only 13 rows carry the two audited
     suppression reasons). This is why Stream 4 uses shadow comparison, not
     the eval set.
3. [ ] **Explicitly not in scope** — see below.

## Explicitly Not In Scope

- **Any other call site** from the fit survey — guardrails self-check rails,
  capture enrichment, health curation, blast-radius guard, REVS crisis Layer-2,
  Intelligence Analyst rubric, model-router escalation. Each is a follow-up
  mission *only if* this pilot passes. In particular, do not touch
  `core/security/guardrails/` or `telegram-bots/revs/crisis_layer2.py`
  (safety-critical).
- **Nimble, Clef, Tev1 0.8B.** One model, one call site. (0.8B may be a later
  comparison if 4B passes but is slow.)
- **Changing what the audit decides or writes.** Same 3 verdicts, same
  `audit_events` table and category, still never unsuppresses.
- **Changing `OLLAMA_KEEP_ALIVE` system-wide**, `-np`, or the model-router's
  `_OLLAMA_LOCK` design. Per-request keep-alive only, if supported.
- **Pulling or removing any other model.**
- **Labelling the eval sets.**

## Scope / Streams

Git safety (AGENTS.md "Concurrent session git safety"): do all code work in a
dedicated worktree, e.g.
`git worktree add ../wt-<MISSION-ID>-tev1 -b <MISSION-ID>-tev1-suppression-audit`.
Never `git checkout` in the shared `/opt/starship-endeavour` checkout. Prune the
worktree after merge.

### Stream 1 — VM: Ollama ≥ 0.35 + `tev1:4b` (ops, no code)

1. Record current Ollama version and the exact rollback path (previous
   binary/package) **before** upgrading.
2. Upgrade Ollama to ≥ 0.35 in a quiet window. This restarts Ollama and
   briefly interrupts every local-model consumer (model-router, guardrails,
   bots) — announce/accept that; confirm the model-router (port 8891) and
   intelligence scheduler are healthy afterwards.
3. `ollama pull tev1:4b`; record size on disk and resident RAM (`ollama ps`).
   Confirm `ollama show tev1:4b` lists **no** `vision` / `thinking` capability.
4. Smoke test and **capture the real response body** (paste it verbatim into
   the knowledge record — Stream 2's parser is locked to it):
   ```bash
   curl -s localhost:11434/v1/systemone -H 'Content-Type: application/json' -d '{
     "model": "tev1:4b",
     "state": "Title: Westpac app and online banking down nationally\nSummary: Customers unable to log in since 8am.\nSector: financial_services\nSuppression reason: media_source_low_relevance",
     "questions": {"verdict": {"type": "choice",
       "instructions": "A mechanical filter hid this item from an OSINT feed tracking operational-resilience risk for an Australian bank. Was hiding it correct?",
       "criteria": {
         "AGREE": "Suppression correct: noise, no real operational-resilience relevance for AU banking",
         "DISAGREE": "Genuine miss: a real outage, breach, cyber incident, regulatory action, critical-infrastructure or third-party-risk story a human should see",
         "UNCERTAIN": "Genuinely unclear either way"}}}}'
   ```
   Expect `DISAGREE` with high probability. Also test one obvious-noise item
   (e.g. a celebrity story) and expect `AGREE`.
5. Latency: run each curl 5× with `time`, both cold and warm. Given
   `OLLAMA_KEEP_ALIVE=0`, check whether `/v1/systemone` accepts a per-request
   `keep_alive` (try `"keep_alive": "5m"`); record whether it is honoured
   (`ollama ps` right after the call). Record p50/max warm and cold latency.
   **Stop gate:** if warm latency > 30 s/item, stop after Stream 1 and report —
   60 items would not fit the job's 900 s subprocess timeout.

### Stream 2 — code: `call_systemone()` provider

In `core/llm/provider_chain.py`, alongside `call_ollama`, add a stdlib-urllib
function in the same style (same `_llm_span` tracing, same `# nosec B310`
justification pattern, keyword-only args):

```python
def call_systemone(
    state: str,
    questions: dict,
    *,
    base_url: str,
    model: str,
    keep_alive: str | None = None,   # only if Stream 1 showed it is honoured
    timeout: int = 60,
) -> dict:  # {question_name: {"answer": str, "probabilities": {option: float}}}
```

- Normalise the real response (from Stream 1 step 4) into the return shape
  above; raise `RuntimeError` on a missing/unknown field rather than guessing.
- Do not route this through the model-router; call Ollama directly like the
  existing `call_ollama` does (same `OLLAMA_BASE_URL`).

### Stream 3 — code: shadow mode in the suppression audit

In `tools/intelligence/suppression_audit.py`:

- New env flag `SUPPRESSION_AUDIT_LOCAL` ∈ `off` (default) / `shadow` / `local`,
  plus `SUPPRESSION_AUDIT_LOCAL_MODEL` (default `tev1:4b`) and
  `SUPPRESSION_AUDIT_LOCAL_MIN_P` (default `0.7`).
- Build the `state` from the same fields `_judge()` already sends (title,
  summary[:500], sector, event_type, operational_relevance, suppression
  reason); move the AGREE/DISAGREE/UNCERTAIN definitions from `_SYSTEM_PROMPT`
  into the question's `criteria`, keeping their meaning identical.
- Thresholding: if the top option's probability < `MIN_P`, the local verdict is
  `UNCERTAIN` (matches the existing "don't guess" contract).
- **`off`:** behaviour byte-for-byte unchanged.
- **`shadow`:** the existing chain makes the real verdict exactly as today;
  additionally call Tev1 and record its verdict, top probability, full
  probabilities and latency alongside the real verdict in the same
  `audit_events` row's detail payload (no new table/column). Any Tev1 failure
  or timeout is logged and ignored — it must never change or delay the real
  verdict beyond its own timeout.
- **`local`:** Tev1 first; on failure/timeout fall back to the existing chain
  (Gemini → Mistral → Ollama). `reason` becomes
  `"tev1:4b p=0.93"`-style (decision models produce no free text).
- Budget: per-item Tev1 timeout from Stream 1's measured max (cap 60 s) and a
  whole-run local budget comfortably under the 900 s subprocess timeout; once
  exhausted, skip Tev1 for the remaining items (log a count).
- Log each local call under a distinct task type if `llm_cost_governance`
  `log_call()` is used by this module's other providers — check, don't assume.

### Stream 4 — schedule + shadow run

- Move the existing `intelligence_suppression_audit` CronTrigger out of the
  06:00–06:45 cluster to the quiet slot found in Pre-flight 2 (must still be
  after that day's collection + suppression writes; `--days 1` window still
  covers the day). Update the job docstring's "06:40" rationale to match.
- Deploy with `SUPPRESSION_AUDIT_LOCAL=shadow`. Restart the intelligence
  scheduler service only through its normal unit.
- Run shadow for **≥ 10 days or ≥ 300 items**, whichever is later.

### Stream 5 — tests

Mirror the existing provider tests' style (mock `urllib.request.urlopen`):
- `call_systemone` parses the captured real response; raises on malformed.
- Threshold: top p below `MIN_P` → `UNCERTAIN`.
- `off` mode: identical calls/outputs to today (regression guard).
- `shadow` mode: Tev1 exception/timeout leaves the real verdict untouched.
- `local` mode: Tev1 failure falls back to the existing chain.
- Run the repo's test suite for touched areas (`pytest` per `pytest.ini`) plus
  lint/format as CI does. All green before push.

### Stream 6 — evaluation + promotion decision

From the shadow `audit_events` rows compute: overall agreement Tev1 vs real
verdict, a 3×3 confusion matrix, Tev1 latency p50/p95/max, timeout/failure
count, and VM impact (load average during the run window vs the same window
before the change). Hand-review **every disagreement** (title + both verdicts)
and record a judgement on who was right.

**Promote to `local` only if all hold:**
- Agreement ≥ 85% on non-UNCERTAIN real verdicts.
- **Zero** cases where Tev1 said `AGREE` with p ≥ `MIN_P` and the hand review
  says it was a genuine miss (a confident AGREE on a real miss is the one
  error this audit exists to catch).
- p95 latency fits the run budget; no measurable degradation of other jobs.

Promotion is a **Captain decision** — present the numbers and recommendation;
do not flip the flag yourself. If it fails, leave it `off`, record why.

## Acceptance

- [ ] Ollama ≥ 0.35 live on the VM, `tev1:4b` pulled, rollback path recorded.
- [ ] Real `/v1/systemone` response body + latency figures recorded.
- [ ] PR merged: `call_systemone()`, suppression audit `off|shadow|local`
      flag (default `off`), tests green, CI green.
- [ ] Audit job moved to a documented quiet slot.
- [ ] ≥ 10 days / ≥ 300 items of shadow data collected.
- [ ] Evaluation (agreement, confusion matrix, latency, disagreement review,
      VM impact) written up with a promote / don't-promote recommendation.
- [ ] Cloud spend for this job unchanged or lower throughout (shadow adds no
      cloud calls).
- [ ] Worktree pruned after merge.

## Reporting

- One knowledge record: `knowledge/missions/<MISSION-ID>-knowledge-record.md`,
  covering Streams 1–6 (include the verbatim response body and the eval table).
- If promoted, list follow-up candidates in ranked order for separate
  missions: capture enrichment (privacy: currently Ollama Cloud `glm-5.2`),
  health OSINT curation, blast-radius guard, then guardrails rails.
- SUOC Platform Registry: no update unless promoted to `local` (then note
  "local decision model (System One) — pilot: suppression audit").
- Consider an ADR (from `docs/decisions/TEMPLATE-madr.md`, check
  `core/governance/architecture-decision-records/` for numbering) only if the
  pilot is promoted and a second call site is planned.
