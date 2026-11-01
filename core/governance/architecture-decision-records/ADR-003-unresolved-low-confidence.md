---
status: "Reconstructed — low confidence"
date: 2026-09-12
decision-makers: {unknown}
consulted: {unknown}
informed: {unknown}
---

# ADR-003 — content unresolved (conflicting/thin evidence)

## Context and Problem Statement

USS-TJR-MSN-0369 Stream 3 was asked to formalize a real decision behind every
`ADR-NNN` number cited in the live repository, including ADR-003. Unlike
ADR-013/022/024/030, ADR-003 has **no substantive, load-bearing citation
anywhere in real production code**. The available sources are thin and, worse,
directly contradict each other about what ADR-003 even is:

* `lcars-portal/src/app/knowledge-workbench/_components/ArchitectureIndex.tsx`
  and `lcars-portal/src/lib/investigations/captainReview.ts` (a "hand-maintained
  ... not guaranteed complete or current" static index the code itself says
  should be retired — MSN-0353 §4) list: "ADR-003 — Python FastAPI for Command
  Centre backend".
* `core/infrastructure/supabase/backups/2026-09-01-dead-tables-pre-drop.json`
  (a pre-drop dump of the orphaned `temporal_entities_archived_2026` "ghost"
  table — confirmed elsewhere in this repo's own knowledge base to have "zero
  owning application code," status `UNKNOWN`/`APPROVED` inconsistently across
  entries) instead names ADR-003 "Tailscale Private Network Architecture,"
  referencing a file `ADR-003-Tailscale-Private-Network-Architecture.txt` that
  does not exist anywhere in the tracked repo.
* `tools/supabase/event_listeners.py` (an MSN-0013C demo/example script dated
  2026-06-08) contains only a generic placeholder recommendation string,
  "Link to related ADR-003 if introducing new services" — illustrative example
  text for a code-review-bot mockup, not an actual citation of a real decision
  (the same file also invents "ADR-001" and "DEC-015" as example filler in the
  same function).

These three sources agree on nothing except that the number "ADR-003" exists
somewhere in someone's mental model. Two of them (the UI mock and the ghost
table) actively disagree about the subject matter (FastAPI backend framework
choice vs. Tailscale network architecture), and the third is demo filler text,
not a citation.

## Decision Outcome

**No decision reconstructed.** Per this mission's explicit instruction, a
confident decision must not be invented from thin or contradictory evidence.
This file exists so the `ADR-003` number is not left dangling from other
documents' citations, but its content is deliberately left as an honest
statement of "not enough evidence," not a fabricated MADR body.

### Confirmation

Any future work that wants to resolve ADR-003 for real should first check
whether either candidate topic (Command Centre backend framework choice, or
Tailscale private network architecture) actually happened as a real,
load-bearing decision elsewhere in the repo's history (e.g. `git log`,
deployment configs, `core/infrastructure/`), rather than trusting either of
the two conflicting title sources above.

## More Information

Full evidence list found by `grep -rn "ADR-003"` repo-wide (2026-09-12,
USS-TJR-MSN-0369 Stream 3): `lcars-portal/src/app/knowledge-workbench/_components/ArchitectureIndex.tsx`,
`lcars-portal/src/lib/investigations/captainReview.ts`,
`core/infrastructure/supabase/backups/2026-09-01-dead-tables-pre-drop.json`,
`tools/supabase/event_listeners.py`, and
`knowledge/missions/USS-TJR-MSN-0368-knowledge-record.md` (which itself only
lists ADR-003 as one of "the genuinely real, code-referenced ones... still an
unverified list, not confirmed one by one" — i.e. the prior mission already
flagged this as unverified and deliberately did not write content for it).
