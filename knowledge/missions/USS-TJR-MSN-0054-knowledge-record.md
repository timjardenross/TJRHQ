# Knowledge Record — USS-TJR-MSN-0054

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0054 |
| Title | A shared-vocabulary grouping can hide a real one-sided opportunity behind a fake three-way conflict |
| Date | 2026-09-08 |
| Lesson | LL-138 |

## Outcome

Deleted platform-runtime/lib/research/ (11 files, zero live callers). Wired number_one.py into context_service.py's /brief/number-one endpoint (replacing its hand-rolled scorer with NumberOne.get_daily_brief()). Added lcars-portal/src/app/api/number-one-brief/route.ts and a Number One Coordination card on Mission Workbench's Open tab — first real UI surface for this engine anywhere in the platform. Corrected the registry's "3 variants" framing. 48 tests total (41 pre-existing + 7 new) all pass.

## Lesson

Grouping technical debt by shared vocabulary ("these all have Task/Queue in the name") rather than verified function produces a false N-way-conflict framing that obscures the real, much smaller finding: one file was genuinely obsolete (safe to delete, zero risk), and one file was a completely different, working, tested capability that nobody had ever wired up — a missed-opportunity bug, not consolidation debt. The "3 variants, low urgency, not worth it" framing nearly caused a live, valuable capability to keep sitting unused indefinitely under the "not urgent" label a genuinely dead file deserved.

## Future Guidance

When technical debt is framed as "N variants of the same thing," verify each one's actual data model and real callers before accepting the grouping — a pattern match on class/field names is not evidence of functional overlap. Treat "well-built, tested, zero callers" as a wiring bug to fix, not consolidation debt to defer — the fix is usually cheaper than the discovery that found it.
