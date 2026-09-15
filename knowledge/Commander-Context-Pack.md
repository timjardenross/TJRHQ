# Commander Context Pack

_Restored 2026-09-15 to satisfy `platform-runtime/prompt_loader.py`'s expected path
(`knowledge/Commander-Context-Pack.md`) — this is a short pointer/index bundle over the
other files restored alongside it, not new source material of its own.
`prompt_loader.py` has zero live callers repo-wide; see
`specialists/RUNTIME-STATUS.md`._

## Purpose

A single entry point that indexes the registry, knowledge, and memory documents
`prompt_loader.py`'s three loader functions (`load_core_context()`,
`load_memory_context()`, `load_knowledge_retrieval_context()`) assemble. Read this
first, then follow the links below to the specific document you need.

## Core Context (`load_core_context()`)

- `command/Commander-TJR.md` — who Captain TJR is in this system, structurally
- `registry/USS-TJR-Charter.md` — platform mission/charter
- `registry/Crew-Registry.md` — full specialist roster
- `registry/Crew-Authority-Matrix.md` — authority level per specialist
- `registry/Division-Registry.md` — departments/divisions

## Memory Context (`load_memory_context()`)

- `memory/Crew-Context.md` — not yet populated (no real equivalent found elsewhere)
- `memory/Captain-Profile.md` — **mirrors real content** at
  `knowledge/memory/captain_profile.txt`; not a stub
- `memory/Active-Priorities.md` — not yet populated
- `memory/Decision-Register.md` — not yet populated
- `memory/Active-Missions.md` — not yet populated
- `memory/Health-Summary.md` — not yet populated

## Knowledge Retrieval Context (`load_knowledge_retrieval_context()`)

- `knowledge/Commander-Knowledge-Index.md` — index of the `knowledge/` directory
- `knowledge/Source-of-Truth-Matrix.md` — canonical-source pointers and known gaps
- `knowledge/Repository-Catalogue.md` — top-level repository directory catalogue

## Status of the Runtime Path These Files Serve

All 15 files `prompt_loader.py` expects were missing from disk before this
restoration. `prompt_loader.py`'s own public loader functions have zero live callers
repo-wide (confirmed by grep and independently flagged by
`reports/vulture/vulture-2026-09-12-full-output.txt`) — see
`specialists/RUNTIME-STATUS.md` for the full dead-code write-up. Restoring these files
does not revive any live runtime behaviour; it removes the "these files are missing"
caveat a couple of specialist skills currently have to disclose, and gives real
backing material if this loader path is ever revived.

## Related Files

- `specialists/RUNTIME-STATUS.md` — dead-code status (authored separately, not by this
  restoration)
- `specialists/SPECIALIST-INVENTORY.md`, `specialists/SPECIALIST-METADATA-MATRIX.md`,
  `specialists/SPECIALIST-ROLE-CATALOGUE.md` — deeper specialist reference material
  this pack's registry files were built from
