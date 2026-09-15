# Commander Knowledge Index

_Restored 2026-09-15 to satisfy `platform-runtime/prompt_loader.py`'s expected path
(`knowledge/Commander-Knowledge-Index.md`) — content is a direct listing of the
top-level `knowledge/` directory as of 2026-09-15. `platform-runtime/MODULE-MAP.md`
independently names a "knowledge index" document among those `repository_awareness.py`
(BOT-008) reads, corroborating this file's intended purpose, though that module is
dead code — see `specialists/RUNTIME-STATUS.md`. `prompt_loader.py` has zero live
callers repo-wide._

## Files Directly Under `knowledge/`

| File | Approx. Size | Content |
|---|---|---|
| `Lessons-Learned.md` | ~30KB | Running lessons-learned log (referenced elsewhere in the repo by ID, e.g. `LL-146`, `LL-149`). |
| `MISSION-BRIEF-TEMPLATE.md` | ~3KB | The canonical mission-brief template `AGENTS.md` tells contributors to start new mission briefs from. |
| `NVIDIA-OSS-Assessment-2026-08-23.md` | ~6KB | Open-source-software assessment note. |
| `OSS-Capability-Search-2026-09-12.md` | ~17KB | OSS capability search results. |
| `OSS-Gap-Solutions-2026-08-23.md` | ~14KB | OSS gap/solution analysis (referenced by `knowledge/backlog-samples/README.md` re: the 814-document review backlog). |
| `SUOC-Platform-Registry.md` | ~229KB | Large platform registry document (by far the largest file in this directory). |

## Subdirectories

- **`backlog-samples/`** — `README.md` plus `comms-backup-procedure.html`; a small,
  real sample set used to exercise `tools/supabase/docling_ingest.py` end-to-end (per
  its own README), explicitly *not* a slice of the actual document-review backlog.
- **`memory/`** — `captain_profile.txt`, a real Captain identity/priorities/health/
  communication-preference profile (classification: "Captain & XO Use"). This is the
  actual source `memory/Captain-Profile.md` (one of `prompt_loader.py`'s expected
  `memory/` paths) mirrors — see that file for detail.
- **`missions/`** — a large set (71 files as of this check) of
  `<MISSION-ID>-knowledge-record.md` files, e.g.
  `USS-TJR-MSN-0384-knowledge-record.md`,
  `VULTURE-KNIP-DEAD-CODE-20260912-knowledge-record.md`. This is a per-mission
  knowledge-record archive, distinct from the top-level `Missions/` directory
  (`Missions/Active/`, `Missions/Engineering-Handoffs/`), which tracks mission status
  rather than knowledge records.

## What This Index Does Not Cover

This is a listing of `knowledge/` only. Related narrative/reference material also
lives under `docs/` (architecture docs, decision records), `specialists/`
(specialist charters and knowledge packs), and directly at the repo root (several
large mission/workbench `.md` files — see `knowledge/Repository-Catalogue.md`'s
"Notable Top-Level Files" section for that inconsistency).

## Related Files

- `knowledge/Repository-Catalogue.md` — full repo directory catalogue
- `knowledge/Source-of-Truth-Matrix.md` — canonical-source pointers
- `knowledge/Commander-Context-Pack.md` — short index across all restored files
