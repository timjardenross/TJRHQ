# MSN-0361: Tighten technology_outage/telecom_outage classifier keyword rules

Mission: USS-TJR-MSN-0361 | Status: Implemented (Tested) | 2026-08-10

## Problem

`intelligence/classification/classifier.py`'s `technology_outage` and
`telecom_outage` `_EVENT_TYPE_RULES` entries matched on bare vendor/platform
names ("microsoft", "aws", "azure", "google cloud", "salesforce",
"servicenow", "cloud", "platform", "incident" for tech; "telstra", "optus",
"tpg", "vodafone", "nbn", "mobile network", "broadband", "telecommunications",
"telco", "connectivity" for telecom) with no requirement that any
outage-specific language co-occur. Any story merely mentioning a tech vendor
or platform — earnings reports, product launches, lawsuits, regulatory or
political stories — got tagged a `technology_outage`/`telecom_outage`
regardless of content.

A narrower mitigation (`_has_outage_language()` in
`intelligence/persistence/intelligence_store.py`) already shipped
2026-08-09/10, scoped only to the outage-push-alert trigger. This mission
fixes the underlying classifier itself so every consumer benefits (weekly
report severity counts, general signal feed, CPS230/dependency-risk flags,
push alerts) — not just the one gated trigger.

Same root defect class as the 2026-07-18 fixes to
payments_disruption/energy_disruption/severe_weather/transport_disruption/
supply_chain, but those were fixed by deleting ambiguous common-English-word
substrings ("port", "cards", "ses"...). That approach doesn't work here — the
ambiguous terms are real vendor/product names that ARE the correct signal
when paired with genuine incident language, so deleting them outright would
cost recall on real outages, not just cut false positives.

## Fix

In `classify()`'s event-type scoring loop, bare vendor/platform/"incident"
terms for `technology_outage` and `telecom_outage` now only count toward the
category's match score if the text also contains a genuine outage-indicator
term (`_OUTAGE_INDICATOR_TERMS`) — mirroring `_has_outage_language()` but
applied at the classification source, not one downstream trigger. All other
categories and their keyword lists are untouched.

```python
_TECH_OUTAGE_GENERIC_TERMS = frozenset({
    "incident", "aws", "azure", "google cloud", "microsoft", "salesforce",
    "servicenow", "cloud", "platform",
})
_TELECOM_OUTAGE_GENERIC_TERMS = frozenset({
    "telstra", "optus", "tpg", "vodafone", "nbn", "mobile network",
    "broadband", "telecommunications", "telco", "connectivity",
})
```

`_OUTAGE_INDICATOR_TERMS` starts from plain dramatic-incident vocabulary
("outage", "degrad", "unavailable", "service disruption", "system failure",
"restored", "resolved", "mitigat", etc.) and — after a second pass over what
got *excluded* (see Verification below) surfaced real vendor status-page
incidents using non-dramatic in-progress language — was extended with the
Statuspage.io-style structural markers vendor status feeds use
("investigating -", "identified -", "monitoring -", "update -", "scheduled
-", "completed -", "in progress -") plus a few plain-English phrases
("issue affecting", "availability issue", "errors accessing", "rollback",
"network disruption", "network problem"). The status-page markers are safe
because ordinary news prose doesn't write "Identified - " with that exact
space-hyphen punctuation — it's specific to the incident-log template these
feeds use.

## Verification — live 30-day sample

Pulled the full current `intelligence_events` population tagged
`technology_outage`/`telecom_outage` over the trailing 30 days from Supabase
(project `cjvrpjwewsrumnbdydgg`): **664 events** (655 technology_outage + 9
telecom_outage). Reconstructed the pre-fix flat-keyword-count logic and
confirmed it reproduces the DB-recorded `event_type` for all 664/664 rows
(100% fidelity) before comparing against the fixed classifier — so the
before/after numbers below are against the actual classification history,
not a synthetic proxy.

**Before → after:**
- 664/664 (100%) tagged technology_outage/telecom_outage under the old rules
  (by definition of the query population).
- **157/664 (23.6%)** reclassified away (mostly to `other`, some to a more
  correct category like `cyber` for bare CVE IDs) after the fix — matching
  the mission's own diagnostic definition exactly: of the 664, 157 relied
  *solely* on generic/bare terms with zero outage-indicator language present
  anywhere in the text.
- **507/664 (76.4%)** retained their technology_outage/telecom_outage tag.

(The originally-reported 152/510 (30%) audit figure was from a different
snapshot/window taken the previous night; the mechanism and rate — roughly
a quarter to a third of tagged events being bare-keyword-only — match.)

**Sanity check on exclusions (per the mission brief's own instruction — read
what gets correctly excluded, not just what stays):** manually reviewed all
157 demoted items. Confirmed false positives include: "Buffett drops Gates
Foundation from $6bn Berkshire donation" (matched "microsoft" via a
Gates/Epstein mention), "Netflix and Sony Are Reportedly Circling
Letterboxd" (matched "platform"), "Oracle acquisition sees Count launch
Count Wealth" (matched "platform"/"cloud"), "Kourtney Kardashian's Brand
Lemme Hit With Class-Action Lawsuit" (matched "platform"), "Hormuz Dispute
Clouds US Iran Diplomacy" (matched "cloud"-adjacent text), "EU review of
airline ownership rules clouds Apollo's £5.7bn easyJet bid" — none of these
are outages. Zero false positives found reintroduced by the extended
indicator vocabulary (spot-checked all 16 items the status-page-marker
addendum pulled back in: all genuine vendor incidents/scheduled maintenance
windows, e.g. "R2 Availability Issues", "SSL/TLS Certificate Management
Maintenance", "Workflow Send and Review Errors").

**Recall check — did the fix under-classify real outages using non-dramatic
language?** First cut of `_OUTAGE_INDICATOR_TERMS` (plain dramatic
vocabulary only) demoted several *genuine* vendor status-page incidents that
used in-progress, non-dramatic reporting language instead ("Incident with
Actions" — GitHub Actions capacity/failure reports, "R2 Availability
Issues", "Network Performance Issues in Hamburg, Germany", "Workflow Send
and Review Errors", "Customers may experience errors when signing up for
new accounts"). This was a real regression, caught by the mission's
instruction to inspect exclusions rather than trust the false-positive count
alone. Fixed by adding the status-page structural markers described above;
re-verification confirmed all of these are now correctly retained, dropping
the demoted count from 173 (26.1%) to the final 157 (23.6%).

**Residual, disclosed gap:** a handful of items remain incorrectly demoted —
title-only duplicate rows with an empty `raw_summary` and a generic-only
title (e.g. "Incident with GraphQL API Requests" with no body text, "Users
may have issue with Signup/Login via Microsoft"). These are genuinely
ambiguous from text alone (indistinguishable from a false positive without
more context), and in every case checked, a companion row for the same
underlying incident with a populated summary exists elsewhere in the same
30-day window and classifies correctly — so the real incident isn't
silently lost from the pipeline, just this thin duplicate snapshot of it.
Not fixed further; flagged rather than expanding scope.

## Tests

- `python3 -m py_compile intelligence/classification/classifier.py` — clean.
- `tests/test_intelligence_classifier.py` — 36/36 pass (one test,
  `test_telecom_outage` — "Telstra network disruption impacts mobile
  services" — initially regressed on the first cut of the fix; fixed by
  adding "network disruption" to `_OUTAGE_INDICATOR_TERMS`, matching the
  same principle as the status-page-marker addendum: compound
  outage-specific phrases are safe, bare "disruption" is not, per the
  2026-07-18 precedent).
- Broader `tests/` intelligence suite run for regression: 218 passed, 3
  failed — confirmed via `git stash` that all 3 failures
  (`test_intelligence_filter.py::test_media_source_low_relevance_suppressed`,
  two in `test_intelligence_phase2.py::TestReadinessHistory`) are
  pre-existing and unrelated to this change (reproduce identically with
  `classifier.py` reverted to `main`).

## Files changed

- `intelligence/classification/classifier.py` — the fix (event-type rule
  comments, generic-term/outage-indicator constants, gated counting logic
  in `classify()`).

## Scope note

Out of scope, not touched: a few pre-existing cross-category
misclassifications surfaced incidentally while reviewing the 157 demoted
items (e.g. "Immigration Detention as Racialized Violence" landing on
`transport_disruption`, "Can I have boundaries with Slack and the group
chat?" landing on `transport_disruption`) — these were already wrong before
this fix and belong to a different defect class (unrelated keyword
collisions in other categories), not the technology_outage/telecom_outage
bare-vendor-term defect this mission was commissioned to fix.
