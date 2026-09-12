# Knowledge Record — MADR template adoption, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0366 |
| Title | Format-only adoption of the MADR (Markdown Architectural Decision Records) template, ahead of a later ADR-consolidation mission |
| Date | 2026-09-12 |
| Lesson | LL-164 |

## Outcome

Adopted the MADR 4.0.0 template as this repo's target format for
Architectural Decision Records, format only — no new tool or dependency,
per USS-TJR-MSN-0366 Stream 10 ("Stage 2A: New Open-Source Tool
Adoption"). Added:

- `docs/decisions/TEMPLATE-madr.md` — the standard MADR 4.0.0 template
  (Context and Problem Statement, Decision Drivers, Considered Options,
  Decision Outcome with Consequences and an optional Confirmation
  subsection, Pros and Cons of the Options, More Information), reproduced
  from the upstream project (https://adr.github.io/madr/, MIT licensed)
  with a repo-specific header comment and a "USS TJR usage notes" footer
  covering file-naming (`ADR-NNN-short-title.md`, three-digit, to match
  the `ADR-\d{3}` pattern `platform-runtime/adr_conflict_detector.py`
  already looks for) and the supersedes/conflicts phrasing that tool's
  regexes already key off.
- `docs/decisions/EXAMPLE-ADR-001-model-router-cloud-escalation-degrade-chain.md`
  — a filled-out worked example, not invented: it transcribes the real
  FND-001 decision already made and shipped in `core/model-router/app.py`
  (`_resolve_cloud_escalation()` and the `MODEL_CLOUD`/`MODEL_CLOUD_ALT`/
  `MODEL_ESCALATION_SAFE_LOCAL` degrade chain) — a cloud-tag registration
  drift (`glm-5.3:cloud` configured 2026-09-08 but never `ollama pull`ed)
  that made every `escalate`/`fallback-complex` call fall through to a
  24B CPU-only model this host cannot serve within any real timeout,
  caught by self-improvement on 2026-09-10/11 and fixed 2026-09-12 with a
  three-step degrade chain that never lands on the unsafe fallback
  automatically. This was checked against three other real candidates
  named in the task brief (the Slack-retirement decision in
  `core/platform/notification_service.py`'s header, and the garak-venv
  isolation decision) before picking the model-router one — it had the
  richest in-code narrative (root cause, detection timeline, and the
  explicit "why not the obvious one-step fix" reasoning) to transcribe
  faithfully into MADR's Considered Options / Pros-and-Cons shape.
- A pointer in `platform-runtime/adr_conflict_detector.py`'s module
  docstring: the tool's existing scan only covers
  `core/governance/architecture-decision-records/` and
  `knowledge/architecture/` (both empty as of 2026-09-12) with a plainer
  `Title:`/`Status:` header shape, not `docs/decisions/`'s YAML front
  matter — the docstring now says so explicitly and points future ADR
  authors at the new template instead of leaving them to guess why a file
  they wrote in `docs/decisions/` never shows up in a conflict scan.
- A pointer in `AGENTS.md` (this repo's short onboarding file for AI
  coding agents) under a new "Writing a new decision record (ADR)"
  section, naming both the template and the worked example.

No existing ADR corpus was migrated and no directory `adr_conflict_
detector.py` scans was touched or seeded — this stream is deliberately
format-only, matching the mission brief's framing that ADR *consolidation*
(reconciling the plain `Title:`/`Status:` shape the detector already
parses with the new MADR shape, and deciding whether `docs/decisions/`
should become one of the detector's scanned directories) is separate,
later work.

## Lesson

A "just adopt this format" task still needs a real usage check before the
template is written, not after: reading
`docs/self-improvement/DECISION-REMEDIATION-WORKFLOW.md` (a substantial
decision-flow document that turned out to have *no* ADR-shaped structure
at all — narrative and code-driven instead) and
`platform-runtime/adr_conflict_detector.py` (which does expect a specific
existing plain-text ADR shape, just not one used anywhere in the repo
yet — both its scanned directories are empty) established, before writing
a single line of template, that (a) the template needed to be genuinely
new infrastructure rather than a reformat of something existing, and (b)
the one existing piece of ADR-aware tooling had specific parsing
expectations (`ADR-\d{3}` filenames, `Title:`/`Status:` lines,
"supersedes ADR-NNN" / "conflicts with ADR-NNN" phrasing) worth mirroring
in the new template's naming convention even though the tool doesn't scan
the new directory yet — cheap forward-compatibility that costs nothing
now and saves the later consolidation mission from a naming mismatch it
would otherwise have to reconcile by hand.

Separately: "don't invent a fake decision, use a real one" produced a
noticeably better template example than a toy would have. Transcribing
FND-001's actual root-cause narrative into MADR's Decision
Drivers/Considered Options/Pros-and-Cons sections surfaced real friction
in the template itself worth knowing about going in — a real decision
rarely has neatly independent, mutually exclusive options the way a
textbook example does (the three "options" here are really "the old
behavior," "the new behavior," and "a stricter behavior nobody chose"),
and MADR's structure absorbed that fine, which is itself useful evidence
the format fits this repo's actual decisions before a large migration
commits to it.

## Future Guidance

When the later ADR-consolidation mission runs: it will need to decide (1)
whether `core/governance/architecture-decision-records/` and
`knowledge/architecture/` get retired in favor of `docs/decisions/` or
`adr_conflict_detector.py` gets pointed at `docs/decisions/` in addition
to (or instead of) them, and (2) whether the detector's regex-based
`Title:`/`Status:` parsing gets extended to also read MADR's YAML front
matter (`status:` field) so both shapes stay scannable during any
transition period, or whether every existing plain-shape ADR gets
reformatted to MADR up front instead. Both files this stream added
(`docs/decisions/TEMPLATE-madr.md`'s "USS TJR usage notes" footer and
`adr_conflict_detector.py`'s updated docstring) already name this
decision explicitly rather than leaving it implicit, so that mission can
start from a documented open question instead of rediscovering it.
