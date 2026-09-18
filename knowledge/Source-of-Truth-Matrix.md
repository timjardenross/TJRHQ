# Source-of-Truth Matrix

_Restored 2026-09-15 to satisfy `platform-runtime/prompt_loader.py`'s expected path
(`knowledge/Source-of-Truth-Matrix.md`) — content derived from `AGENTS.md`'s
"Check-first registries" section and the explicit registry pointers in
`specialists/README.md`. `platform-runtime/MODULE-MAP.md` independently names a
"source-of-truth" document among those `repository_awareness.py` (BOT-008) reads,
corroborating this file's intended purpose, though that module is dead code — see
`specialists/RUNTIME-STATUS.md`. `prompt_loader.py` has zero live callers repo-wide._

## Check-First Registries (from `AGENTS.md`)

| Domain | Canonical Source | Note |
|---|---|---|
| Intelligence sources | `tools/intelligence/seed_source_registry.py` (`SOURCES` list) | Check `source_name`/`url` before adding; the file dedupes+warns on collision, but that's a safety net, not a substitute for checking first. Real incident: a duplicate row took down a 163-row upsert batch. |
| ADR citations | `core/governance/architecture-decision-records/` | The canonical **filed**-ADR directory. `docs/decisions/` holds only the MADR template and a worked example, not the filed registry — don't confuse the two. Real incident: up to 4 separate ADR registries existed before consolidation. |
| Scheduled jobs (APScheduler) | `intelligence/scheduler.py`, `telegram-bots/revs/scheduler.py` | Consolidation in progress (USS-TJR-MSN-0368 Stream 6); 2 live instances as of that stream. Ask before adding a new scheduler instance. |
| Specialist registry | `platform-runtime/prompt_loader.py`'s `SPECIALISTS` dict **and** `specialists/SPECIALIST-INVENTORY.md` | Two angles on the same roster — code-loaded dict vs. narrative inventory — that can drift apart; check both. Note: `prompt_loader.py` itself is confirmed dead code (`specialists/RUNTIME-STATUS.md`), so its `SPECIALISTS` dict is a source of truth for *intended* roster shape only, not for anything currently executing. |

## Registry Pointers From `specialists/README.md`

| Pointer | Target | Status as of 2026-09-15 |
|---|---|---|
| "Crew Registry" | `core/crew/registry/specialist-registry.md` | **Missing from disk.** `core/crew/registry/` contains only `retrieval-routing-rules.txt` and `specialist-retrieval-registry.txt`. |
| "Runtime / Governance Bridge" | `core/crew/registry/runtime-specialist-map.txt` | **Missing from disk.** |
| "Approved Crew Deliverables" | `core/crew/` | Present — governance folders per specialist (e.g. `core/crew/chief-engineer/`). |
| "Runtime Specialist Charters" | `specialists/core-crew/` | Present. |
| "Specialist Standard" | `specialists/Specialist-Template.md` | Present. |

This means `specialists/README.md` itself has two broken forward references. This
matrix's `registry/Crew-Registry.md` and `registry/Crew-Authority-Matrix.md` were
built directly from the specialist `.md` charter files rather than from those two
missing targets, and say so explicitly.

## Advisory-Board Retrieval Sources (found, not in `AGENTS.md`, but load-bearing)

- `core/crew/registry/specialist-retrieval-registry.txt` — the 5 build/engineering
  specialists (Chief Engineer, Chief of Staff, Knowledge Manager, Design Officer, Code
  Review Specialist) that `tools/supabase/collaboration_router.py` and
  `specialist_router.py` route Advisory Board questions to, plus each one's allowed
  Supabase `document_type` values. Per its own header comment, this file "never
  existed" until 2026-08-09, so retrieval silently degraded to empty results before
  that date — a precedent for exactly the kind of missing-file degradation this
  restoration effort addresses for `prompt_loader.py`.
- `core/crew/registry/retrieval-routing-rules.txt` — companion term-to-specialist
  routing rules for the same two router modules.

## Other Explicit Source-of-Truth Statements Found

- `platform-runtime/DEVELOPMENT-GUIDE.md` and `platform-runtime/MODULE-MAP.md` state
  that `commander_runtime.py`, `router.py`, and the BOT-008/010/011/012/013 cluster
  they dispatched to are confirmed dead code with zero live callers repo-wide — the
  same finding this restoration's provenance notes lean on for `prompt_loader.py`.
- `specialists/RUNTIME-STATUS.md` is the canonical write-up of that dead-code finding
  for the specialist-loading path specifically (out of scope for this file to author —
  see that document directly).

## Related Files

- `knowledge/Repository-Catalogue.md` — what exists where
- `knowledge/Commander-Knowledge-Index.md` — `knowledge/` directory detail
- `registry/Crew-Registry.md`, `registry/Crew-Authority-Matrix.md` — built around the
  missing-registry gap documented above
