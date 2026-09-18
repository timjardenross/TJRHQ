# Captain TJR

_Restored 2026-09-15 to satisfy `platform-runtime/prompt_loader.py`'s expected path
(`command/Commander-TJR.md`) — content derived from the `Reports to:` / `Reports To:`
fields across `specialists/core-crew/*.md` and `specialists/future-crew/*.md`,
`specialists/SPECIALIST-INVENTORY.md`, `specialists/SPECIALIST-ROLE-CATALOGUE.md`, and
`specialists/README.md`. `prompt_loader.py` has zero live callers repo-wide; see
`specialists/RUNTIME-STATUS.md`._

**Naming note:** `prompt_loader.py` expects this file at `command/Commander-TJR.md`, but
the repo's own convention — used consistently in `specialists/core-crew/*.md`,
`specialists/SPECIALIST-INVENTORY.md`, `AGENTS.md`, and elsewhere — is **"Captain TJR"**,
not "Commander TJR." The one exception found is
`specialists/core-crew/Visual-Design-Officer.md`, whose `Reports To:` field says
"Commander TJR." This file keeps the loader's expected filename but uses the repo's
dominant "Captain TJR" naming in its body; the mismatch is not silently resolved.

## Role in the System

Captain TJR is the human principal of the USS TJR platform (also referred to as
Starship Endeavour / Starfleet Command in some specialist documents). Every specialist,
advisor, and coach defined under `specialists/core-crew/` and `specialists/future-crew/`
exists to support Captain TJR's decisions, missions, and personal operating model —
none of them act as an independent decision-maker.

This is a structural/role description of the Captain TJR position as referenced by
other specialist files, not a personal profile. Personal state about the actual human
(priorities, health, decisions, missions) belongs under `memory/` — see
`memory/Captain-Profile.md`, which is intentionally an unpopulated stub, not this file.

## Authority Position

Per the `## Authority` / `Authority:` sections found across
`specialists/core-crew/*.md`:

- The overwhelming majority of specialists and advisors are explicitly **"Advisory
  only. Captain TJR retains all decisions"** (or a close variant) — see
  `registry/Crew-Authority-Matrix.md` for the full breakdown.
- Where a specialist has broader delegated authority (e.g. Chief of Staff / Executive
  Officer over mission sequencing, Coder Agent over implementation details), that
  authority is bounded and escalates back to Captain TJR for strategic direction, major
  trade-offs, or mission rejection.
- No specialist file grants any role authority over Captain TJR; Captain TJR is the
  terminal escalation point for essentially every specialist in the roster
  (`specialists/SPECIALIST-ROLE-CATALOGUE.md`, "Escalate To" column).

## Direct Reports (per specialist `Reports To:` fields)

Most specialist files list `Reports To: Captain TJR` directly, including: Chief
Engineer, Chief of Staff / Executive Officer (XO), UX Design Officer / Design Officer,
Medical Officer, Business Continuity Advisor, Crisis Management Advisor, Executive Risk
Advisor, Operational Resilience Advisor, Performance Coach, Recovery Coach, Wellness
Advisor, Research Officer, and Operations Officer.

A smaller set reports up through another specialist rather than directly: Coder Agent
and QA & Test Officer report to Chief Engineer; Knowledge Officer reports to Chief of
Staff. See `registry/Crew-Registry.md` for the full roster with reporting lines.

## Related Files

- `registry/USS-TJR-Charter.md` — platform mission/charter
- `registry/Crew-Registry.md` — full specialist roster
- `registry/Crew-Authority-Matrix.md` — authority level per specialist
- `memory/Captain-Profile.md` — personal Captain profile (unpopulated stub)
