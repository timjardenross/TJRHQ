# Crew Registry

_Restored 2026-09-15 to satisfy `platform-runtime/prompt_loader.py`'s expected path
(`registry/Crew-Registry.md`) — content derived from `specialists/core-crew/*.md`,
`specialists/future-crew/*.md`, `specialists/SPECIALIST-INVENTORY.md`,
`specialists/SPECIALIST-METADATA-MATRIX.md`, and a direct listing of
`.claude/skills/`. `prompt_loader.py` has zero live callers repo-wide; see
`specialists/RUNTIME-STATUS.md`._

**Note on the pointer this file replaces:** `specialists/README.md` names
`core/crew/registry/specialist-registry.md` as "Crew Registry" and
`core/crew/registry/runtime-specialist-map.txt` as the "Runtime / Governance Bridge."
As of 2026-09-15, **neither file exists on disk** — `core/crew/registry/` contains only
`retrieval-routing-rules.txt` and `specialist-retrieval-registry.txt` (a 5-specialist
Advisory Board routing table, not a full crew roster). This file is built directly from
the specialist `.md` charters instead.

## Core Crew (Active)

| Specialist | Registry ID | Department | Reports To | `.claude/skills/` built? |
|---|---|---|---|---|
| Chief of Staff / Executive Officer (XO) | USS-TJR-002 (also cited as SFE-002 in `SPECIALIST-INVENTORY.md`) | Operations Division | Captain TJR | **Yes** — `chief-of-staff/SKILL.md` |
| Chief Engineer | USS-TJR-003 | Engineering Division | Captain TJR | **Yes** — `chief-engineer/SKILL.md` |
| Coder Agent | USS-TJR-004 | Engineering Division | Chief Engineer | No |
| QA & Test Officer | USS-TJR-005 | Engineering Division | Chief Engineer | No |
| Knowledge Officer | USS-TJR-006 | Operations Division | Chief of Staff | No |
| UX Design Officer / Design Officer | USS-TJR-009 | Experience Division | Captain TJR | No |
| Visual Design Officer | USS-TJR-013 | Experience Division | Commander TJR (per file; see naming note in `command/Commander-TJR.md`) | No |
| Medical Officer | USS-TJR-007 (`SPECIALIST-INVENTORY.md`) / USS-TJR-008 (`SPECIALIST-METADATA-MATRIX.md`) — **conflicting IDs, not resolved by this file** | Health Division / Medical Bay | Captain TJR | No |
| Recovery Officer | USS-TJR-009 | Medical Bay | Captain TJR (implicit; not explicit in file) | No |
| Operations Officer | USS-TJR-OPS-001 | Operations Division | Captain TJR | No |
| Executive Assistant | USS-TJR-EXA | Operations Division | Captain TJR (implicit) | No |
| Business Continuity Advisor | USS-TJR-BC-001 | Operations | Captain TJR | **Yes** — `bc-advisor/SKILL.md` (added during this restoration; see note below) |
| Crisis Management Advisor | USS-TJR-CM-001 | Operations | Captain TJR | No |
| Executive Risk Advisor | USS-TJR-ER-001 | Operations | Captain TJR | No |
| Operational Resilience Advisor | USS-TJR-OR-001 | Operations | Captain TJR | No |
| Performance Coach | USS-TJR-PC-001 | Medical / Wellness | Captain TJR | No |
| Recovery Coach | USS-TJR-RC-001 | Medical / Wellness | Captain TJR | No |
| Wellness Advisor | USS-TJR-WA-001 | Medical / Wellness | Captain TJR | No |

## Future Crew (Planned / Not Yet Commissioned)

| Specialist | Registry ID | Department | Status |
|---|---|---|---|
| Research Officer | USS-TJR-006 (collides with Knowledge Officer's ID above — as found in source files) | Intelligence Division | Planned |
| Operations Officer | USS-TJR-007 (superseded — promoted to core crew as `USS-TJR-OPS-001`; the `future-crew/Operations-Officer.md` file is itself marked DEPRECATED) | Operations Division | Promoted to core crew |
| UX Officer | USS-TJR-010 | Experience Division | Planned |
| Knowledge Architect | USS-TJR-011 | Knowledge Division | Planned |
| Product Designer | USS-TJR-012 | Experience Division | Planned |

## Deprecated / Duplicate Files (found in `specialists/core-crew/` and `specialists/future-crew/`)

Two files are explicitly marked `DEPRECATED` in their own headers, pointing to a
canonical location elsewhere:

- `specialists/core-crew/Research-Officer.md` → superseded by
  `specialists/future-crew/Research-Officer.md`
- `specialists/future-crew/Medical-Officer.md` → superseded by
  `specialists/core-crew/Medical-Officer.md`
- `specialists/future-crew/Operations-Officer.md` → marked "PROMOTED TO CORE CREW,"
  superseded by `specialists/core-crew/Operations-Officer.md`

## `.claude/skills/` Persona Skills (checked 2026-09-15)

The task that produced this file was told the list was "currently: chief-engineer, xo,
chief-of-staff" and might have grown — it had: `design-audit` was already present, and
`bc-advisor` was added mid-session while these registry files were being written. This
confirms the roster is actively growing; re-check `.claude/skills/` rather than trusting
this list as final.

Directories under `.claude/skills/` that contain a `SKILL.md` as of this check:

- `chief-engineer/SKILL.md` — maps to Chief Engineer (USS-TJR-003)
- `bc-advisor/SKILL.md` — maps to Business Continuity Advisor (USS-TJR-BC-001)
- `chief-of-staff/SKILL.md` — maps to Chief of Staff (USS-TJR-002); its own
  description also frames the role as "Chief of Staff," while `xo/SKILL.md` covers a
  differently-scoped "Executive Officer (XO)" persona (recovery-first capacity
  gatekeeper) — the repo's specialist files use "Chief of Staff" and "Executive
  Officer (XO)" as alternate titles for the *same* registry entry
  (`specialists/SPECIALIST-INVENTORY.md` calls the runtime file
  `specialists/core-crew/Chief-of-Staff.md` a "legacy file name, title updated" to
  Executive Officer), so there may be two skills for what the inventory treats as one
  role, or the `xo` skill may in practice cover a narrower slice (capacity gating)
  than the full Chief of Staff charter. This inconsistency is reported as found, not
  resolved here.
- `xo/SKILL.md` — see note above
- `design-audit/SKILL.md` — a read-only UI audit skill, not tied to a specialist
  registry ID; not part of the specialist roster above

`.claude/skills/chief-engineer-workspace/`, `chief-of-staff-workspace/`,
`xo-workspace/` hold eval/benchmark iterations for the corresponding skills, not
additional personas. `.claude/skills/bot-reviews/` and `.claude/skills/workbench-reviews/`
are archived review write-ups, not skills with their own `SKILL.md`.

## Related Files

- `registry/Crew-Authority-Matrix.md` — authority level per specialist
- `registry/Division-Registry.md` — department/division detail
- `knowledge/Source-of-Truth-Matrix.md` — canonical-source pointers, including the
  missing `core/crew/registry/specialist-registry.md` this file stands in for
