# Crew Authority Matrix

_Restored 2026-09-15 to satisfy `platform-runtime/prompt_loader.py`'s expected path
(`registry/Crew-Authority-Matrix.md`) — content derived from a grep of `## Authority`,
`Authority:`, `Decision Authority:`, and `## Authority Model` sections across
`specialists/core-crew/*.md` and `specialists/future-crew/*.md`, cross-checked against
`specialists/SPECIALIST-ROLE-CATALOGUE.md`'s "Specialist Decision Authority Matrix."
`prompt_loader.py` has zero live callers repo-wide; see
`specialists/RUNTIME-STATUS.md`._

## Standard Advisory Wording

The following specialists carry the exact (or near-exact) sentence **"Advisory only.
Captain TJR retains all decisions."** under a `## Authority` heading:

- Business Continuity Advisor (`BC-Advisor.md`)
- Crisis Management Advisor (`Crisis-Management-Advisor.md`)
- Executive Risk Advisor (`Executive-Risk-Advisor.md`)
- Operational Resilience Advisor (`OR-Advisor.md`)
- Performance Coach (`Performance-Coach.md`)
- Recovery Coach (`Recovery-Coach.md`)

**Variant wording** — Wellness Advisor (`Wellness-Advisor.md`) scopes the sentence to
health/lifestyle specifically: *"Advisory only. Captain TJR retains all decisions
regarding health and lifestyle."*

## Specialists With a Different Shape of Authority Statement

- **Chief Engineer** (`Chief-Engineer.md`) — plain field `Authority: Advisory` (no
  `## Authority` heading; same substance).
- **UX Design Officer / Design Officer** (`UX-Design-Officer.md`) — `Authority:
  Advisory Only`.
- **Visual Design Officer** (`Visual-Design-Officer.md`) — three separate fields:
  `Authority: Visual Language & Brand Review`, `Decision Authority: Advisory Only`,
  `Implementation Authority: None`.
- **Operations Officer** (`Operations-Officer.md`) — the only file with a materially
  different structure, a `## Authority Model` heading stating: "Operations Officer
  **RECOMMENDS**" and "Number One **REVIEWS escalations**" (rather than the flat
  "advisory only" sentence used elsewhere). Worth flagging because it introduces a
  two-tier recommend/review pattern not used anywhere else in the roster.
- **Executive Assistant** (`Exec-Assistant.md`) — has both a `## Decision Authority`
  section and a separate `## Charter Authority` section; no single-line advisory
  disclaimer.
- **Future-crew files** (`Knowledge-Architect.md`, `Product-Designer.md`,
  `Research-Officer.md`, `UX-Officer.md`) — each uses the same three-field pattern as
  Visual Design Officer: a role-specific `Authority:` line, then `Decision Authority:
  Advisory Only`, then `Implementation Authority: None`.
- **Chief of Staff, Coder Agent, Knowledge Officer, QA & Test Officer, Medical
  Officer** — no explicit `Authority` field or heading was found in these files at
  all; their authority is only documented indirectly via
  `specialists/SPECIALIST-ROLE-CATALOGUE.md`'s summary matrix (see below) and
  `specialists/SPECIALIST-INVENTORY.md`'s "Decision Authority" column.

## Cross-Check: `specialists/SPECIALIST-ROLE-CATALOGUE.md` Decision Authority Matrix

| Specialist | Full | Advisory | Implementation | Escalate To |
|---|---|---|---|---|
| Chief of Staff | Prioritisation, decomposition | Resource allocation | None | Captain TJR |
| Chief Engineer | None | Architecture, standards | None | Captain TJR |
| Coder Agent | None | None | Code implementation | Chief Engineer |
| QA Test Officer | None | Quality assessment | Testing strategy | Chief Engineer |
| Knowledge Officer | None | Governance | Documentation | Chief of Staff |
| UX Design Officer | None | UX assessment | None | Chief Engineer |
| Medical Officer | None | Wellness guidance | None | Captain TJR |
| Research Officer (Future) | None | Research findings | None | Captain TJR |
| Operations Officer (Future) | None | Operations | None | Chief of Staff |

Chief of Staff is the one specialist in this table with any **Full** authority
(mission prioritisation/sequencing/decomposition) — everything else in the roster is
Advisory or Implementation-only, consistent with the "Captain TJR retains all
decisions" pattern found directly in the advisor files above.

## Bottom Line

Regardless of which exact wording a given file uses, every specialist charter found in
this repo is either explicitly advisory-only or bounded to a narrow implementation/
recommendation role that escalates upward — none grants a specialist final decision
authority over Captain TJR. The one partial exception is Chief of Staff's delegated
Full authority over mission sequencing/decomposition, which is itself scoped and still
escalates to Captain TJR for strategic direction or mission rejection.

## Related Files

- `registry/Crew-Registry.md` — full roster with reporting lines
- `registry/Division-Registry.md` — department/division detail
- `command/Commander-TJR.md` — Captain TJR's role as the terminal authority
