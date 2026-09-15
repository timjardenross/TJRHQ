<!--
This is the MADR (Markdown Architectural Decision Records) 4.0.0 template,
adopted format-only for USS-TJR-MSN-0366 Stream 10 (Stage 2A: New
Open-Source Tool Adoption) — no new tool or dependency, just a target
Markdown shape so a future ADR-consolidation mission has something to
migrate existing decision-doc-like content (comments, scattered docs,
runbooks) *into*, instead of picking a format mid-migration.

MADR project: https://adr.github.io/madr/ (MIT licensed). This file mirrors
its official template almost verbatim; the only repo-specific addition is
this header comment and the trailing "USS TJR usage notes" section.

How to use: copy this file to a new one named
`ADR-NNN-short-kebab-case-title.md` in this directory (three-digit,
zero-padded number — see the "USS TJR usage notes" section at the bottom
for why), fill in every section, delete bracketed placeholder text, and
delete any optional section you don't need (marked below). Keep the
Context and Problem Statement, Decision Outcome, and Consequences
sections even for a small decision — those three carry the most value for
a future reader trying to understand *why*.
-->

---
# These are optional metadata elements. Feel free to remove any of them.
status: "{proposed | rejected | accepted | deprecated | superseded by ADR-NNN}"
date: {YYYY-MM-DD when the decision was last updated}
decision-makers: {list everyone involved in the decision}
consulted: {list everyone whose opinions are sought (typically subject-matter experts); and with whom there is a two-way communication}
informed: {list everyone who is kept up-to-date on progress; and with whom there is a one-way communication}
---

# {short title, representative of solved problem and found solution}

## Context and Problem Statement

{Describe the context and problem statement, e.g., in free form using two
to three sentences or in the form of an illustrative story. You may want
to articulate the problem in form of a question and add links to
collaboration boards or issue-management systems.}

## Decision Drivers

<!-- optional, but strongly encouraged -->

* {decision driver 1, e.g., a force, facing concern, …}
* {decision driver 2, e.g., a force, facing concern, …}
* … <!-- numbers of drivers can vary -->

## Considered Options

* {title of option 1}
* {title of option 2}
* {title of option 3}
* … <!-- numbers of options can vary -->

## Decision Outcome

Chosen option: "{title of option 1}", because {justification. e.g., only
option, which meets k.o. criterion decision driver | which resolves force
{force} | … | comes out best (see below)}.

### Consequences

* Good, because {positive consequence, e.g., improvement of one or more
  desired qualities, …}
* Bad, because {negative consequence, e.g., compromising one or more
  desired qualities, …}
* … <!-- numbers of consequences can vary -->

### Confirmation

<!-- optional -->

{Describe how the implementation / compliance of the ADR is confirmed.
E.g., a review, a linked test, an observed metric, or a specific log line
this platform's own tooling checks for. Fitness functions may be
described using the Gherkin language.}

## Pros and Cons of the Options

<!-- optional, but strongly encouraged for anything but a trivial or
     one-option decision -->

### {title of option 1}

{example | description | pointer to more information | …}

* Good, because {argument a}
* Good, because {argument b}
* Neutral, because {argument c}
* Bad, because {argument d}
* … <!-- numbers of pros and cons can vary -->

### {title of other options}

{example | description | pointer to more information | …}

* Good, because {argument a}
* Good, because {argument b}
* Neutral, because {argument c}
* Bad, because {argument d}
* …

## More Information

<!-- optional -->

{You might want to provide additional evidence/confidence for the
decision outcome, e.g., a link to the actual PR/issue, and/or define
when/how this decision was validated. Also link related ADRs here, e.g.
"Supersedes ADR-002" or "Conflicts with ADR-005" — a future
ADR-conflict-detection pass over this directory can key off exactly that
phrasing.}

<!--
USS TJR usage notes (not part of upstream MADR — repo-specific):

- File naming: `ADR-NNN-short-kebab-case-title.md`, zero-padded to three
  digits (ADR-001, ADR-002, …) to match the `ADR-\d{3}` pattern that
  platform-runtime/adr_conflict_detector.py already looks for in
  `core/governance/architecture-decision-records/` and
  `knowledge/architecture/`. This directory (`docs/decisions/`) is not one
  of that tool's scanned paths yet — this stream adopts the MADR *format*
  only; wiring this directory into cross-reference/conflict detection is
  in scope for the later ADR-consolidation mission, not this one.
- "supersedes ADR-NNN" / "conflicts with ADR-NNN" phrasing in the body
  (as in "More Information" above) is a convention the conflict detector
  already parses via regex — keep using that exact phrasing so records
  written now stay machine-readable once consolidation wires this
  directory in.
- See `docs/decisions/EXAMPLE-ADR-001-model-router-cloud-escalation-degrade-chain.md`
  for a filled-out real example (a decision already made in this repo,
  written up retroactively in this format).
-->
