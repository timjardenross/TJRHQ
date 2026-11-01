# Knowledge Record — MSN-LCARS-003

| Field | Value |
|---|---|
| Mission ID | MSN-LCARS-003 |
| Title | A grep for one variable name undercounts real adoption of a pattern |
| Date | 2026-09-08 |
| Lesson | LL-136 |

## Outcome

Fixed the one real gap: capture-workbench now distinguishes a genuine fetch failure from a real zero-capture week. Synced naming: content-workbench's 4 views (error -> loadError) and human-systems-workbench (loadFailed boolean -> loadError string, now carrying the real message) match the dominant loadError convention. captains-chair-workbench's per-signal xError names and advisory-workbench's action-result error/apiError fields were deliberately left alone — different concepts, not gaps.

## Lesson

A single-string grep for a specific variable name is not evidence of absence — it only proves that name is absent, not that the underlying capability is. Before proposing a multi-file fix based on a grep, read the actual components; the grep undercounted 6 of 7 "gaps" as already correctly handled under different names (error, apiError, loadFailed).

## Future Guidance

When a mission asks "does every page do X", verify by reading the code, not by grepping for the one name you expect X to use — naming drift across a codebase this size is the norm, not the exception. Confirmed dominant convention going forward: loadError (string | null) for page/component-level load state; per-signal xError names are fine when a component genuinely combines multiple independent data sources.
