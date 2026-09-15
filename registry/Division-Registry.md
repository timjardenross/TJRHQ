# Division Registry

_Restored 2026-09-15 to satisfy `platform-runtime/prompt_loader.py`'s expected path
(`registry/Division-Registry.md`) — content derived from the `Department:` /
`Department` fields across `specialists/core-crew/*.md`,
`specialists/future-crew/*.md`, `specialists/SPECIALIST-INVENTORY.md`, and
`specialists/SPECIALIST-METADATA-MATRIX.md`. `prompt_loader.py` has zero live callers
repo-wide; see `specialists/RUNTIME-STATUS.md`._

## Divisions Found in Specialist Files

| Division | Specialists (as labelled in source file) |
|---|---|
| **Operations Division** / **Operations** | Chief of Staff / Executive Officer (XO), Knowledge Officer, Operations Officer, Executive Assistant, Business Continuity Advisor, Crisis Management Advisor, Executive Risk Advisor, Operational Resilience Advisor |
| **Engineering Division** | Chief Engineer, Coder Agent, QA & Test Officer |
| **Experience Division** | UX Design Officer / Design Officer, Visual Design Officer, UX Officer (future), Product Designer (future) |
| **Health Division** (per `SPECIALIST-INVENTORY.md`) / **Medical Bay** (per `Medical-Officer.md`, `Recovery-Officer.md` YAML front matter) / **Medical / Wellness** (per `Performance-Coach.md`, `Recovery-Coach.md`, `Wellness-Advisor.md`) | Medical Officer, Recovery Officer, Performance Coach, Recovery Coach, Wellness Advisor |
| **Intelligence Division** | Research Officer (future) |
| **Knowledge Division** | Knowledge Architect (future) |

## Naming Inconsistency Note

The health-related division is labelled three different ways depending on which
specialist file you read: "Health Division" in the narrative inventory
(`specialists/SPECIALIST-INVENTORY.md`), "Medical Bay" in the YAML front matter of
`Medical-Officer.md` and `Recovery-Officer.md`, and "Medical / Wellness" in the plain
`Department:` field of `Performance-Coach.md`, `Recovery-Coach.md`, and
`Wellness-Advisor.md`. This registry lists all three verbatim rather than picking one,
since no single file in the repo declares itself the canonical label.

## Division Ownership Summary

Per `specialists/SPECIALIST-METADATA-MATRIX.md`'s "By Department" table:

- **Operations** — Chief of Staff, Knowledge Officer, Operations Officer (future)
- **Engineering** — Chief Engineer, Coder Agent, QA Test Officer
- **Experience** — UX Design Officer, UX Officer (future), Product Designer (future)
- **Health** — Medical Officer
- **Intelligence** — Research Officer (future)

## Related Files

- `registry/Crew-Registry.md` — full roster with department per specialist
- `registry/Crew-Authority-Matrix.md` — authority level per specialist
- `registry/USS-TJR-Charter.md` — platform mission/charter
