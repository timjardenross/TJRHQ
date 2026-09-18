# USS TJR Specialists

Runtime Responsibility
- This folder contains specialist `.md` charter files and specialist knowledge packs, written for
  the (now-dead) Commander Runtime and for the newer `.claude/skills/` specialist rebuild.
- `specialist_registry.py` (BOT-010) was written to load `specialists/core-crew/*.md` and
  `specialists/future-crew/*.md`, but has zero live callers as of 2026-09-15 — it and the rest of
  its Commander Runtime cluster are confirmed dead code. See `RUNTIME-STATUS.md` for the full
  finding across all specialist registries, not just this one.
- Do not move runtime `.md` specialist files out of this folder regardless — `.claude/skills/`
  charters are still authored from them, even without a live loader.

Active Crew
(status: active per each charter's own front matter, verified 2026-09-15 — this list was stale
before that: Medical Officer and Operations Officer were still listed under Future Crew below
despite each being promoted to core-crew and marked active/operational in their own files)
- Chief of Staff
- Chief Engineer
- Coder Agent
- Knowledge Officer
- QA & Test Officer
- UX Design Officer (retitled Design Officer, MSN-0310 — see specialists/core-crew/UX-Design-Officer.md)
- Visual Design Officer
- Medical Officer
- Operations Officer

Future Crew
- Research Officer (canonical charter: `specialists/future-crew/Research-Officer.md` — the
  core-crew file of the same name is a deprecated pointer stub, P2-004 Specialist Deduplication)

Planned Crew
- Career Officer
- Content Officer
- Financial Officer

Note on the two "DEPRECATED"/"PROMOTED" stub files still on disk
(`specialists/future-crew/Medical-Officer.md`, `specialists/future-crew/Operations-Officer.md`,
`specialists/core-crew/Research-Officer.md`): these are completed-migration pointers, not open
conflicts — each names its own canonical replacement and says not to update it further. Harmless
if left as-is; a later cleanup mission can remove them per their own "pending git commit removal"
notes.

Crew Registry
→ ../registry/Crew-Registry.md (restored 2026-09-15 — the `core/crew/registry/specialist-registry.md`
  path this used to point to doesn't exist on disk; see RUNTIME-STATUS.md)

Approved Crew Deliverables
→ ../core/crew/

Runtime Specialist Charters
→ core-crew/

Runtime / Governance Bridge
→ ../registry/Crew-Authority-Matrix.md (restored 2026-09-15 — the
  `core/crew/registry/runtime-specialist-map.txt` path this used to point to doesn't exist either)

Specialist Standard
→ Specialist-Template.md
