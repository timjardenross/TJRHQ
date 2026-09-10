# Knowledge Record — SD-FND-001 (model_catalogue_drift)

| Field | Value |
|---|---|
| Mission ID | SD-FND-001 |
| Title | A fallback guard added to one task type must be audited across every sibling task type |
| Date | 2026-09-10 |
| Lesson | LL-141 |

## Outcome

`core/model-router/app.py`'s `fallback-complex` task type routed to `glm-5.3:cloud` with no availability guard, hard-failing every call since the model was never actually live in the router's catalogue. Fixed by PR #101, adding the identical availability-fallback guard `escalate` already had (degrade to local `mistral-small3.2:24b` when `glm-5.3:cloud` isn't in `_available_model_names()`). Self-improvement's `model_catalogue_drift` check (`data/self-improvement/runs/2026-09-08-210035` and `2026-09-09-210043`, FND-001, high severity, conclusive evidence) flagged this twice before it was fixed.

## Lesson

PR #87 (merged 2026-09-08) bumped `MODEL_CLOUD` to `glm-5.3:cloud` and added an availability-fallback guard for `escalate` and `engineering-review` — but not `fallback-complex`, a third task type routed to the same unverified model, live in the same file, in the same function. PR #87's own description flagged the model tag as unverified. The gap sat for two days and two self-improvement cycles (both correctly classified `needs_signoff`, so auto-remediation never touched it) before a human-driven fix closed it.

## Future Guidance

When adding an availability/fallback guard because a model tag is unverified or newly introduced, grep the same file for every other task type routed to that model tag and guard all of them in the same PR — not just the one task type that prompted the change. A partial fix for a shared-risk config value is a latent recurrence, not a closed finding; self-improvement will keep re-flagging it every cycle until every sibling is covered.
