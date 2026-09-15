# Knowledge Officer skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established Chief-of-Staff/BC-Advisor
pattern. Tier choice: lightweight (SKILL.md + this inline eval, no separate benchmark.json/
with_skill dirs/cross-specialist review/Artifact page) — `specialists/core-crew/Knowledge-Officer.md`
is 14 lines, thinner than Chief-of-Staff's source charter, which used this same tier.

## Q1 — "Can you check our specialist registries for any inconsistencies before I hand this inventory to someone new?"

**Baseline**: Reasonable generic checklist — confirm formatting is consistent, contact/reporting
fields are filled in, statuses look current, no obvious typos. Didn't open
`specialists/SPECIALIST-INVENTORY.md` itself to check; treated "inconsistencies" as a formatting
question rather than a data-integrity one.

**With-skill**: Opened `specialists/SPECIALIST-INVENTORY.md` directly and found a real, verifiable
duplicate-ID bug: Registry ID `USS-TJR-006` is assigned to Knowledge Officer (line 68, under Core
Crew) **and** to Research Officer (line 112, under Planned/Future Crew) in the same document — the
file's own "Registry mappings verified against canonical sources ✅" checklist item is therefore
wrong. Named both claims explicitly rather than silently picking one as "the real" USS-TJR-006 (per
the charter's "don't quietly resolve a registry collision" instruction), and also flagged that the
document is dated June 7, 2026 and hasn't been touched since — itself a documentation-lifecycle
staleness signal independent of the ID collision. Routed the fix as a Chief-of-Staff-sequenced item
rather than renumbering unilaterally.

**Verdict: with-skill clearly better.** The duplicate-ID finding is real, independently checkable
(both line numbers cited above), and exactly the class of check-first-registry drift this charter
exists to catch — the baseline's formatting-level pass had no mechanism to surface it because it
never opened the actual registry.

## Q2 — "We're about to file a new ADR for a caching decision — anything I should check first?"

**Baseline**: Generic ADR hygiene advice — write a clear problem statement, list real alternatives
considered, get a decision-maker to sign off, "check nothing similar already exists." Gestured at
checking for duplicates without actually doing it.

**With-skill**: Applied `AGENTS.md`'s "Check-first registries" ADR rule directly — checked the real
canonical filed-ADR directory, `core/governance/architecture-decision-records/`, and found 11 real
filed ADRs (`ADR-003`, `004`, `006`, `013`, `020`, `022`, `024`, `027`, `030`, `031`, `032` — the
numbering gaps consistent with `AGENTS.md`'s own note that up to 4 separate ADR registries existed
before consolidation) plus `TEMPLATE-madr.md` sitting inside that same directory. That's a real,
concrete finding worth surfacing: `AGENTS.md`'s own text says "`docs/decisions/` holds the MADR
*template* and worked example, not the filed registry itself," but the actual template file lives
inside the canonical *filed* directory, not in `docs/decisions/` (which holds only
`EXAMPLE-ADR-001-*.md` and one unrelated `SD-*.md` decision doc — verified by listing both
directories). Flagged this as a small, real documentation-drift item in `AGENTS.md`'s own
check-first-registry guidance — ironic given what that section exists to prevent — and recommended
checking the real ADR number/title list above before filing, rather than trusting the
docs/decisions/ description of where things live.

**Verdict: with-skill clearly better**, and on a dimension the baseline had no way to reach: it
surfaced a real inconsistency in the very document that tells contributors how to avoid registry
drift, which is a materially more useful catch than generic ADR-writing advice.

## Q3 — "Is the Repository Governance doc up to date? Can I point a new contributor at it?"

**Baseline**: Skimmed the doc, judged it "looks thorough and current," recommended pointing the new
contributor at it with no further caveat.

**With-skill**: Read `specialists/knowledge-packs/Repository-Governance-Standard.md` in full and
checked its two named "still needs retiring" duplicate-page examples against the actual code
(`captains-chair` vs `captains-chair-workbench`, `comms` vs `content-workbench`). Found both pairs
have in fact already been retired — the legacy pages now contain real "this page moved" notices
dated 2026-08-11 and 2026-08-29 respectively, with commit-level detail in their own code comments —
so the standard's prose still frames these as live open problems when they're now resolved history.
Applied the Draft → Active → Review → Archive framework explicitly: recommended the doc go through
a **Review** pass to update its worked examples to reflect the current (resolved) state, while
confirming its core policy (retire-don't-delete, parity-check first, fix every live link) is still
sound and fine to point a new contributor at today.

**Verdict: with-skill better.** The baseline's answer isn't wrong on the policy itself, but it
missed that the doc's own examples are stale — a genuine documentation-lifecycle finding the
baseline had no reason to look for, since it never checked the cited examples against the live
code.

## Overall

3/3 with-skill responses graded better than baseline, each on a dimension traceable to a specific
charter instruction (check-the-real-registry-first, disclose-and-don't-quietly-resolve-collisions,
apply-the-lifecycle-framework-to-real-files) rather than general LLM variance. No re-run needed —
ship as-is.

One real side-effect worth a follow-up, logged not fabricated: the `TEMPLATE-madr.md` location
mismatch between `AGENTS.md`'s prose and the actual filesystem (surfaced in Q2) hasn't been
corrected anywhere yet — it's a small, real drift in the platform's own check-first-registry
documentation, worth a short fix (either move the template or correct `AGENTS.md`'s description) but
out of scope for this skill build itself.
