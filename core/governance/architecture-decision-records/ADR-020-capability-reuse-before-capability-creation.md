<!--
Formalized USS-TJR-MSN-0368 Stream 7 alongside ADR-027 -- see that file's
header comment for why only these two of the 18 referenced-but-unfiled
ADR numbers were formalized this pass, and this mission's knowledge record
for the full inventory of what's left.
-->

---
status: "accepted"
date: 2026-09-12
decision-makers: Chief Engineer, Number One
informed: all officers, all Platform Service owners
---

# Capability reuse before capability creation

## Context and Problem Statement

This platform has repeatedly rebuilt capability that already existed
elsewhere in the codebase under a different name (see
knowledge/composition-first-design-principle.md and the multiple
"N mechanisms doing the same job" findings in
knowledge/suoc-universal-concept-duplication.md — 4 permission mechanisms,
5+ notification senders, 9 `config.py` files at last count). How do we
stop a new mission from reaching for "build a new one" as the default
before checking whether an existing Platform Capability already does the
job, or is close enough to extend?

## Decision Drivers

* Concept duplication findings under MSN-0210 (SUOC) — multiple
  independently-evolved mechanisms for the same conceptual job, discovered
  only after both existed and had to be reconciled.
* Composition-first-design-principle.md's own standing guidance: check
  existing Platform Capabilities for overlap before building.

## Decision Outcome

Chosen option: **existing capability is checked and extended before new
capability is created.** Concretely: before starting implementation, a
mission checks the SUOC Platform Registry (`knowledge/SUOC-Platform-Registry.md`)
and the relevant domain's existing services for something that already
does this job or is close enough to extend. New capability is justified
in the mission record when reuse is rejected, not assumed by default.

### Consequences

* Good, because it's the direct fix for this codebase's most repeated
  structural problem (concept duplication under independent evolution).
* Good, because it gives "why did we build a new one instead of
  extending X" a documented answer to point to, rather than relying on
  the original author's memory.
* Bad, because checking for reuse takes real time up front and can feel
  like it's slowing down a mission that "just" needs one small thing —
  the SUOC concept-duplication findings show that shortcut is exactly how
  the duplication happened in the first place.

<!-- USS TJR usage notes -->
## USS TJR usage notes

- Referenced elsewhere in this repo as `ADR-020` (bare form) — e.g.
  `knowledge/SUOC-Platform-Registry.md`, `docs/LifeOS-Wall-Tablet-V1-Component-Scope.md`
  (as "SUOC Principle 3, ADR-020"). Both predate this file.
