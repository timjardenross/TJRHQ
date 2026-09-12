<!--
Formalized USS-TJR-MSN-0368 Stream 7. ADR-027 has been cited by number
(`ADR-027`) across this codebase since at least MSN-0210's SUOC work
(knowledge/SUOC-Platform-Registry.md cites it 5 times as a governing
principle for Scheduling, Authority, Audit, and Delivery), but until this
file, no numbered ADR file backing that citation existed anywhere in the
repo -- 18 distinct `ADR-NNN` numbers are referenced in prose across the
tree (grep `ADR-[0-9]{3}`), and platform-runtime/adr_conflict_detector.py
has scanned this directory's own path since it was written without ever
finding anything in it. This file formalizes the ONE principle with the
clearest, most-repeated existing grounding rather than retroactively
inventing content for all 18 -- see this mission's knowledge record for
the full inventory of what's still unformalized.
-->

---
status: "accepted"
date: 2026-09-12
decision-makers: Chief Engineer, Number One
informed: all officers, all Platform Service owners
---

# Whole-of-system principle: no component is complete in isolation

## Context and Problem Statement

Starship Endeavour is built as one operating core, not a federation of
independently-evolving systems (SUOC Principle 1). Repeated post-mortems
across this codebase (dead-end wiring, silently-dormant "activated"
systems, dashboards nobody linked to, tables nothing reads) trace back to
the same root cause: a component was built and shipped as complete once
its own internal logic worked, without anyone checking whether the wider
system could actually find it, watch it, govern it, query it, or evolve
it. How do we stop "it works" from being treated as "it's done"?

## Decision Drivers

* Recurring pattern of "activated" systems later found to have zero real
  callers or zero real rows (see knowledge/built-vs-live-consolidated-registry-2026-07-17.md
  and knowledge/quality-scoring-dead-end-wiring.md for two concrete
  instances).
* SUOC Platform Registry needing one consistent bar to score every
  component against (see knowledge/SUOC-Platform-Registry.md's own
  per-component "Y·Y·~·Y" style checklist, which this principle backs).

## Decision Outcome

Chosen option: **a component is not complete until it can be (1)
discovered by the rest of the platform without tribal knowledge, (2)
linked into at least one real consumer, (3) monitored (a health signal or
heartbeat exists), (4) governed (an authority/approval path applies if the
component takes actions), (5) queryable (its state is inspectable, not
only inferable from logs), and (6) evolvable (a clear owner and a known
extension point exist).

### Consequences

* Good, because it converts "I shipped the code" into a checklist the
  SUOC Platform Registry can actually score components against instead of
  a vague completeness feeling.
* Good, because it directly explains and prevents the repeated
  dead-wiring pattern this codebase has hit multiple times.
* Bad, because it raises the real bar for calling something "done," which
  can look like scope creep on a mission that only meant to ship the
  narrow logic — the cost is real and deliberate.

<!-- USS TJR usage notes -->
## USS TJR usage notes

- Referenced elsewhere in this repo as `ADR-027` (bare form) — e.g.
  `knowledge/SUOC-Platform-Registry.md`, `docs/LifeOS-Wall-Tablet-V1-Component-Scope.md`.
  Both predate this file and were not edited to point here; they already
  resolve correctly once a reader knows to look in this directory.
- Scanned by `platform-runtime/adr_conflict_detector.py` (`scan_adrs()`),
  which discovers this file by its `ADR-027` filename prefix, not by its
  content matching any registry.
