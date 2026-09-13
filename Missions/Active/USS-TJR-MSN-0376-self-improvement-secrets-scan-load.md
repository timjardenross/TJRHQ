# Mission Brief

## Mission Header

- **Mission ID:** USS-TJR-MSN-0376
- **Priority:** P3 — a resource-hygiene follow-up from a transient incident, not a live outage
- **Source:** live VM investigation (this session, 2026-09-13) into a harness monitoring-loop kill during memory pressure. Root cause was transient (a burst of concurrent `detect-secrets` processes coinciding with steady baseline load, not the kernel OOM killer, not garak, not a structurally undersized VM). This mission investigates and fixes the one repeat-offender pattern identified: bulk `detect-secrets` scans spiking memory/process count.

## Pre-flight

1. **Existing-entry check.**
   ```
   grep -rn "detect-secrets\|detect_secrets" scripts/self_improvement/
   → no matches. The self-improvement package does not invoke detect-secrets directly.

   grep -n "id: detect-secrets" -A 20 .pre-commit-config.yaml
   → the hook already has `require_serial: true`, added deliberately (per its own
     comment, citing PR #189) to force exactly ONE pre-commit-level invocation with
     the complete file list — this already fixed a *different*, previously-diagnosed
     bug (baseline-rewrite false positives from pre-commit's own batching). It does
     NOT limit detect-secrets' own internal multiprocessing within that one invocation.

   grep -n "for i, finding in enumerate(findings)" scripts/self_improvement/orchestrator.py
   → confirmed: a plain sequential for-loop, no ThreadPoolExecutor/multiprocessing/
     asyncio.gather anywhere in scripts/self_improvement/. auto_remediation.py's
     git_commit() is one blocking subprocess.run() per call.

   git check-ignore -v data/self-improvement/runs/
   → not ignored. git ls-files data/self-improvement/ | wc -l → 98 tracked files.
   find data/self-improvement/runs -type f | wc -l → 92 files across 37 run
     subdirectories already, growing by (at least) one subdirectory per self-
     improvement cycle, all committed to git.
   ```

2. **Premise verification.** The working assumption going into this mission (from the live incident summary) was "self-improvement spawns 9 parallel detect-secrets instances per run-cycle." That does not hold up against the actual code:
   ```
   Claimed: self-improvement's own orchestration loop parallelizes bulk scans.
   -> ACTUALLY: the loop is sequential in-process; no parallel spawning found anywhere
      in scripts/self_improvement/. The "9 concurrent detect-secrets processes" seen
      during the live incident more plausibly came from ONE pre-commit-triggered
      detect-secrets invocation (from a single git commit, wherever it originated —
      self-improvement's or a concurrent session's) internally parallelizing its own
      file-scanning work-queue across worker processes, not from 9 separate commits.
      This mission's Stream 0 must confirm which explanation is actually true before
      Streams 1-2 pick a fix — the two explanations point at different code.

   Working assumption: excluding data/self-improvement/runs/ from the scan is safe.
   -> NOT verified. Those files (findings_raw.json, evidence.json, etc.) are captured
      output from the self-improvement pipeline's own discovery/collection steps —
      if that pipeline ever legitimately captures something that looks like a secret
      from what it scanned, excluding this directory would blind detect-secrets to a
      real leak precisely where the collector has the most contact with raw scanned
      content. This must be checked against real file contents (Stream 1), not assumed
      safe by analogy to data/mem0_qdrant/'s existing exclusion (vector embeddings,
      categorically different content, not evidence-of-a-scan output).
   ```

3. **Explicitly not in scope.** (see below)

## Explicitly Not In Scope

- **Re-investigating the OOM/monitoring-loop kill itself.** Already root-caused as transient (no kernel OOM event, garak unaffected, memory recovered within minutes) — that incident is closed. This mission only follows up on the one real repeat-offender pattern it surfaced.
- **Any change to `.pre-commit-config.yaml`'s `require_serial: true` setting.** That fix addressed a separate, already-diagnosed bug (PR #189's baseline-rewrite false positive) and must not be touched or reverted by this mission.
- **Pruning, archiving, or restructuring `data/self-improvement/runs/`'s growth pattern in general** (e.g., deciding whether old runs should ever be deleted or moved out of git). That's a retention-policy decision outside this mission's scope — this mission only asks whether the *scanning* behavior against that directory needs to change, not the directory's lifecycle.
- **Any other resource-hygiene finding from the live incident** (ollama's fixed ~5.3GB RSS, Phoenix, the telegram bots) — all confirmed expected and bounded, nothing to fix there.

## Scope / Streams

### Stream 0 — Confirm the actual mechanism before touching anything
Reproduce or directly evidence which of the two explanations is real: (a) `detect-secrets` internally parallelizes file-scanning within one invocation (check its CLI/library for a worker-count concept, and correlate the incident's observed process count against this VM's CPU core count — a match would support this explanation), or (b) multiple concurrent `git commit`s (from self-improvement and/or a concurrent session) each independently triggered the pre-commit hook at overlapping times. Do not proceed to Stream 1/2 on an assumption.

### Stream 1 — Check what's actually in the growing directory
Read a representative sample of real files under `data/self-improvement/runs/` (not just filenames) to determine whether they could plausibly ever contain a real secret pattern (API keys, tokens, credentials the collector's own grep/subprocess steps might have captured verbatim from scanned source). This determines whether excluding the directory from detect-secrets is safe or a real regression.

### Stream 2 — Pick and implement the fix based on Streams 0-1's real findings
Candidates to choose between (do not pre-commit to one — the pre-flight explicitly could not settle this):
- If Stream 0 shows internal worker-pool parallelism scanning a large file count: look for a `detect-secrets` flag/env var to cap workers, or reduce the scanned surface (Stream 1-gated).
- If Stream 1 shows the directory's content is safe to exclude (pure structured JSON with no raw-scan-content fields): add `data/self-improvement/runs/` to the existing `exclude:` pattern in `.pre-commit-config.yaml`, following the same precedent as `data/mem0_qdrant/`.
- If Stream 0 shows the real cause is overlapping concurrent commits (self-improvement + another session), the fix is a commit-time lock/lease for self-improvement's own commits, not a detect-secrets config change at all.

### Stream 3 — Verify the fix under real load
Don't just assert the fix works — reproduce a scan against the current (or a synthetically grown) `data/self-improvement/runs/` before and after, and show process count/peak memory actually drops, the same evidentiary bar MSN-0375's Stream 3 held itself to.

## Acceptance

- Stream 0's real mechanism is confirmed with evidence (process count vs. CPU cores, or timestamps of overlapping commits), not asserted.
- Stream 1's content check is real (actual file samples read), and the safety verdict on exclusion is stated plainly either way.
- Whatever fix Stream 2 lands is the one Streams 0-1's real findings actually support — not a default "just exclude it" if the evidence doesn't back that.
- Stream 3 shows a real before/after measurement, not just "should be fewer processes now."
- SUOC Platform Registry: note under CI/CD & Supply-Chain Hygiene or Observability (whichever fits the actual fix) if this mission changes shared tooling behavior; no update needed if Stream 0 finds the cause was one-off overlapping commits with no code fix required.

## Reporting

One knowledge record (`knowledge/missions/USS-TJR-MSN-0376-knowledge-record.md`) covering all four streams — small enough not to need per-stream splitting.
