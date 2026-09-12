# USS-TJR-MSN-0372 — "Check Existing State First" Guardrails — Knowledge Record

Priority P2. Source: this session's own repeated finding — the same failure mode (a new
mission adds something without checking whether it already exists) had been caught twice in
verified, code-level evidence (SOURCES duplicate rows breaking a 163-row upsert batch;
up-to-4 separate ADR registries), with AGENTS.md's existing "check first" line unenforced
prose that got skipped both times anyway. Process/tooling mission — one record covers all
three streams, no SUOC Platform Registry update (doesn't add or change a platform
capability).

## Pre-flight (dogfooding the template this mission created)

- Confirmed no mission-brief template existed anywhere in the repo before this mission
  (`Missions/Active`, `Missions/Engineering-Handoffs`, `knowledge/missions/` are all
  post-hoc records, not pre-mission authoring skeletons; `find . -iname "*MISSION-BRIEF*"`
  returned nothing).
- Verified the ADR canonical directory is `core/governance/architecture-decision-records/`
  (9 filed ADRs: 2 pre-existing + 7 from USS-TJR-MSN-0369 Stream 3), separate from
  `docs/decisions/` which holds the MADR *template* and one worked example — AGENTS.md
  already pointed at the latter for format, not the filing location, which is exactly the
  kind of confusable-registry situation Stream 3 needed to disambiguate.
- Verified the APScheduler count cited in the mission brief ("still open, 6 real independent
  instances") had already moved: commits `9e768ff` and `96c8e3f`, already on this branch's
  base (`origin/main`) before this mission started, re-verified the real count as 2 live
  instances (`intelligence/scheduler.py`, `telegram-bots/revs/scheduler.py`) and deleted
  `recovery_scheduler.py` as confirmed dead code. This is itself a live instance of Pre-flight
  item 2 ("cited numbers/locations drift") — the brief's own APScheduler framing was already
  stale by the time this mission ran, caught by checking real state instead of trusting the
  brief.
- Confirmed Stream 6 (scheduler consolidation) is not otherwise complete — `human_systems_
  scheduler.py`'s dormant daemon mode is still an open decision — so AGENTS.md's new
  scheduler line notes "consolidation in progress" rather than naming a single canonical
  scheduler, per the mission brief's own instruction for that case.

## Stream 1 — Mission-brief template

Created `knowledge/MISSION-BRIEF-TEMPLATE.md`: Pre-flight is the first section (before
Scope/Streams/Acceptance), with three concrete checklist items requiring a cited grep
command/result, a cited verification of the brief's own premise against real repo state, and
a required "Explicitly Not In Scope" section. Updated AGENTS.md's "Working in this repo"
section to point at it by name instead of duplicating the checklist there — one canonical
location for the checklist itself.

## Stream 2 — Registry audit

Checked every candidate named in the mission brief, plus the ADR directory and scheduler
files surfaced by Stream 1's pre-flight, for the same "list-of-dicts with no duplicate-key
protection" collision shape:

| Registry | Shape | Verdict | Reasoning |
|---|---|---|---|
| `tools/intelligence/seed_source_registry.py` `SOURCES` | list of dicts | **protected** (already fixed) | Commit `c1446f5` added a `seen_names` dedupe with a loud stderr warning on drop, specifically because this list is appended to independently across missions. |
| `tools/intelligence/seed_source_registry_old_64sources.py` | list of dicts (64-source predecessor) | **needs-guard-added → deleted instead** | Zero references anywhere in the repo (`grep -rl` across `.py`/`.md`/`.yml`/`.yaml` and a broader unrestricted grep found only a semgrep *scan report* mentioning the filename, not a real reference; zero imports, zero systemd/cron entries). Superseded by `seed_source_registry.py`'s "CANONICAL — 160 sources" framing. A dead duplicate of the exact file that already had this bug is itself a small instance of the pattern — nobody checked whether the old version should be removed when the new one was built. Deleted (`git rm`) rather than adding a guard to dead code. |
| `platform-runtime/prompt_loader.py` `SPECIALISTS` dict | dict literal, keyed by specialist_key | **no-real-risk** | `git log` shows this dict has effectively never been independently edited by separate missions (its only touching commits are a dependabot bump and the ruff autofix pass, neither of which changed its keys) — no realistic concurrent-append collision path today, unlike SOURCES which is a real, actively-grown intelligence-collection registry. Named in AGENTS.md's new list anyway so a future addition checks both this dict and `SPECIALIST-INVENTORY.md` before adding a specialist. |
| `specialists/SPECIALIST-INVENTORY.md` | narrative Markdown with per-specialist fields | **no-real-risk (not code-parsed)** | `grep -rl "SPECIALIST-INVENTORY"` across `.py` found zero consumers — it's prose documentation, not data loaded by any code path, so a duplicate-key guard doesn't apply. The real (separate) risk is drift between this file's prose and `prompt_loader.py`'s dict describing the same roster — noted in AGENTS.md, not fixed here (not a collision-guard problem). |
| `intelligence/ingestion/collection_engine.py` `_ADAPTER_MAP` | dict literal, keyed by `source_type` | **no-real-risk** | Matches the mission brief's own framing: a plain dict literal in one file, edited a handful of times total (`git log` shows 3 commits, none adding a duplicate key), Python would only silently keep the last duplicate rather than reproducing SOURCES's exact Postgres batch-collision failure mode. No realistic independent-append path. |
| `core/governance/architecture-decision-records/` | numbered Markdown files, not a list-of-dicts | **protected by numbering + prior consolidation** | Already the subject of dedicated formalization work (USS-TJR-MSN-0366/0368/0369); 9 ADRs now filed under distinct numbers. The ~23 remaining bare citations are explicitly tracked elsewhere (USS-TJR-MSN-0369 closing record) — not this mission's job to resolve, only to name the canonical location in AGENTS.md so a new decision-writer finds it before inventing another registry. |
| APScheduler instances | independent `Scheduler()` call sites, not a list | **in progress, not this mission's fix** | Real count re-verified at 2 live (see Pre-flight above); consolidation of the still-open `human_systems_scheduler.py` dormant-mode decision is Stream 6's own scope. Noted in AGENTS.md as "ask before adding a new instance" per the mission brief's instruction for an in-progress consolidation. |

## Stream 3 — AGENTS.md sharpened

Replaced the single "check `knowledge/` and any registry/CMDB-style docs" bullet with a named
"Check-first registries" subsection listing the four real registries above by path (SOURCES,
the ADR directory, the two live schedulers, and the two-angle specialist roster), each with
what to check before adding to it. Sequenced after Stream 2 so the list reflects the audit's
actual findings rather than the brief's original guesses.

## Follow-up (not this mission's scope, flagged for whoever picks it up next)

1. `specialists/SPECIALIST-INVENTORY.md` (prose) and `prompt_loader.py`'s `SPECIALISTS` dict
   (code) describe the same roster from two angles with no single source of truth — a real
   drift risk, just not a duplicate-key collision one. Worth a future mission if the two are
   ever found to disagree.
2. AGENTS.md's new registry list will go stale as registries get added/consolidated (expected
   per the mission brief) — update it opportunistically whenever this pattern surfaces again.
3. Scheduler consolidation itself (Stream 6, USS-TJR-MSN-0368) remains open:
   `human_systems_scheduler.py`'s unused daemon mode still needs a keep-or-remove decision,
   and the unexplained 8-event human_systems dispatch burst noted in commit `9e768ff` is
   still unresolved. Both explicitly out of this mission's scope.

---
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01PGfrc2GZ5PkKGF42WmAy2q
