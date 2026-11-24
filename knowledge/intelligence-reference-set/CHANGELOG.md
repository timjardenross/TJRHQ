# Reference set changelog

## v0 (2026-11-24) - frozen

`reference_set.json` and `baseline-2026-11-24.json`: "Baseline V0 - exploratory and unreviewed". Not modified
by v1. Known v0 weaknesses are corrected only in v1 (see below).

## v1 (2026-11-24) - `reference_set_v1.json`, `baseline_v1-2026-11-24.json`, `events_export_2026-11-24.json`

DRAFT. Initial evidence review done by an AI agent (standard web search only). `reviewed_by_human: false` on all 53 records.

### What changed

- 26 new records (RS-028 to RS-053); the 27 v0 records are carried over (`set_membership: "v0"`) with a `status`,
  `primary_sector` and, where relevant, `v1_note` / `v1_correction`. v1-only records are `set_membership: "v1_new"`.
- Every record has one status: `confirmed_material`, `confirmed_non_material`, `stale_or_resurfaced`,
  `duplicate_report`, `unrelated_incident`, `unresolved_insufficiently_verified`.
- **Unverified is no longer a negative.** v0 treated RS-012, RS-013, RS-015, RS-026, RS-027 as provisional negatives; in v1
  they are `unresolved_insufficiently_verified`, excluded from all scoring (including false escalation). RS-006 and RS-007
  (CBA, Westpac) stay unresolved.
- v0 correction: RS-010 first-report time (the Bloomberg "FAA grounds all flights nationwide" item is 2026-11-13T22:04Z, not 12 Nov).

### Counts (53 records)

| Status | n |
|---|---|
| confirmed_material | 15 |
| confirmed_non_material | 10 |
| stale_or_resurfaced | 14 |
| unrelated_incident | 1 |
| duplicate_report | 3 |
| unresolved_insufficiently_verified | 10 |

Negatives (confirmed_non_material + stale + unrelated + duplicate) = 28. Scored negatives for false escalation = 25
(duplicates are clustered under their parent).

**Targets not met:** the Captain asked for at least 25 independently evidenced material incidents; v1 has **15**
(8 carried from v0, 7 new). The search tool could not surface more dated, Australian, confirmed incidents for Sep-Nov 2026.
Negatives (28) exceed the 20 target.

Confirmed-material by sector: telecommunications 3, government 3, financial services 2, energy 2, cloud 1,
retail/cyber 1, education/cyber 1, healthcare 1, cyber security 1. **No confirmed-material examples yet** for
payments, identity or transport (only unresolved or non-material records exist for those).

### Scorecard changes

- Reports `all`, `v0_subset` and `v1_new_only` views so benchmark expansion is not mistaken for capability change.
- False escalation counts a scored negative that reached a brief (brief_id / brief text) **or** has disposition BRIEF/ESCALATE.
- False-recovery and incorrect-correlation are implemented and measured against a production export (below).

### Measured vs unverified

Measured by the agent (SELECT only, 2026-11-24, `published_at` post the +10h RSS repair): all `tjr_detection` blocks;
`events_export_2026-11-24.json`; the `measured_checks` block (full-table false-recovery and correlation checks);
scorecard outputs in `baseline_v1-2026-11-24.json`. Unverified: every incident fact taken from web search
(times, scale, causes) unless an authoritative source is named in `sources`; see `uncertain_facts` per record.
The events export is a **sample** (<=5 earliest + <=3 brief + <=3 restoration rows per incident, titles lightly normalised),
so use `tjr_detection` counts, not `len(events)`. Brief *text* was not supplied to the scorecard, so brief surfacing
there uses `brief_id` and disposition only (earlier v0 SQL showed Coles and Microsoft/OpenAI-Medicare also named in daily briefs).

## v3 (2026-11-24) - `reference_set_v3.json` (owner-reviewed)

Applies the owner's decisions Q1-Q9 to the review of the v2 candidates. v0, v1 and the candidates file are not modified.

- Window extended to 2026-07-28. Observation periods are fixed 7-day UTC blocks; 8 of 17 are coverage-limited and reported separately.
- 84 records (v1's 53 plus RS-054..RS-084). Every record has `intelligence_category`; `status` keeps the v1 vocabulary (mapping in the file header).
- Origin Energy is one incident (RS-042) with dated lifecycle entries; C2-U03 is folded in. RS-005 is retrospective; its findings are RS-082.
  RS-004 is non-material; its forward-looking signal is RS-083. Sydney Airport is one parent (RS-075) with the cause marked disputed.
- Q4 thresholds (20,000 premises or 24 h with a critical service) are automatic inclusion, not exclusion; per-item outcomes are in `q4_assessment`.
- Q9: the Fiji fuel contamination record (RS-077) resolved to confirmed_material (medium) after reading the ABC article and a specialist site.
- Corrections CORR-01..12 (and SUPP-01/02) carry an audit trail in the data. `reviewed_by_human` is true for the 48 records the owner decided; the 36 other
  carried v1 records stay false.
- Counts: see `counts` in the file (34 confirmed material: 27 operational disruptions, 6 emerging risks or warnings, 1 retrospective finding).
