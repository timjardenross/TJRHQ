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
- Chief of Staff
- Chief Engineer
- Coder Agent
- Knowledge Officer
- QA & Test Officer
- UX Design Officer

Future Crew
- Research Officer
- Operations Officer
- Medical Officer

Planned Crew
- Career Officer
- Content Officer
- Financial Officer

Crew Registry
→ ../core/crew/registry/specialist-registry.md

Approved Crew Deliverables
→ ../core/crew/

Runtime Specialist Charters
→ core-crew/

Runtime / Governance Bridge
→ ../core/crew/registry/runtime-specialist-map.txt

Specialist Standard
→ Specialist-Template.md
