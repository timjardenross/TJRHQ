# Intelligence presentation specification (lightweight)

Status: specification only. No application development is requested or implied. HQ Development is not an active workstream and nothing in the intelligence programme depends on it. Everything marked **FWR** below is a future Workbench requirement, recorded so it is not lost. Items marked **ESSENTIAL-IF** describe a point at which an application change would become essential to intelligence delivery; each needs Captain approval before any work starts.

Field and object names below are provisional until the Batch 1 work packages are merged. Where a name is not yet in the codebase it is written in angle brackets.

## 1. Principles
- Show what the evidence supports; never imply more certainty, freshness or coverage than exists.
- One canonical treatment per incident; other mentions link to it.
- Collection failure is never displayed as an operational disruption. Incomplete coverage is never displayed as an all-clear.
- Depth is progressive disclosure, not reduction: L1 and L2 first, the rest on demand.

## 2. Layered product (L1 to L7)
| Layer | Content | Display rule |
|---|---|---|
| L1 | Executive BLUF and the three axis badges | Top of page; about 1,200 characters is a flexible target, not a cap |
| L2 | Key judgements: evidence quality, analytical confidence, competing explanations, known unknowns, indicators that would change the assessment | One card per judgement |
| L3 | Detailed assessment per material incident | Proportionate; no character cap |
| L4 | National, systemic and sector implications | Shown when present |
| L5 | Forward outlook and indicators; scheduled events kept distinct from assessed risk; unmatched high-severity "Watch" lane | Shown when present |
| L6 | Collection limitations and uncertainty | Always rendered, including quiet days |
| L7 | Evidence ids, URLs, lifecycle | Collapsed by default |

Empty sections are omitted (never "None"). International developments with material national, systemic or sector relevance are shown in full whether or not Australian impact has occurred; only low-relevance international items collapse into a counted line that expands on request. The audio script is derived from L1 and L2 and carries no ids or URLs.

## 3. Three separate axes (three separate badges)
| Axis | Values | Notes |
|---|---|---|
| Operational posture | RED, AMBER, GREEN, **UNKNOWN (NOT ASSESSED)** | UNKNOWN is used when evidence is insufficient for a defensible risk judgement. It is a distinct neutral style, never green and never red. |
| Intelligence coverage | FULL, PARTIAL, DEGRADED | Names the limiting sources. Never changes posture. |
| Assessment confidence | per judgement and overall | Qualitative. No unvalidated numerical probabilities. |

Rules: a quiet posture with partial coverage reads "No significant development identified; assessment limited by: <named sources>". A degraded collector appears on the coverage axis only.

## 4. Six epistemic classes
Every statement carries one label, shown as a small tag and a legend: established fact; reported but unverified; analytical assessment; inference; forecast or scenario; known unknown. Evidence quality, analytical confidence and likelihood are three separate fields and are never merged into one score.

## 5. Freshness states
Computed from the age of `as_of` in hours and the cadence deadline, not from the generated-for date.

| State | Meaning |
|---|---|
| Current | Latest scheduled assessment completed within its expected deadline and within usable age |
| Refresh overdue | The expected completion deadline for the cadence has passed, even if the previous assessment is still inside the usable-age limit |
| Stale | Usable age exceeded (36 hours daily, 8 days weekly; Captain confirmation pending) |
| Unavailable | No assessment exists for the period |

Every product line shows the reporting date (Melbourne), `as_of` age in hours, and the freshness badge. A successful refresh that produced identical content updates "last refreshed" without creating a new content generation and without implying new analysis.

## 6. Assessment history
Append-only generations per product, cadence and reporting date. The detail view shows: generation number, `as_of` (UTC) and Melbourne reporting date, content-change versus refresh-only activity, input watermark (event count, latest collection time), a plain-language change summary, and supersedes links. Historical rows with uncertain attribution display the recorded basis label (for example "derived from as_of" or "uncertain") rather than an inferred date. History is never deleted by the display layer.
- **FWR:** products view reads the current-view (`intelligence_products_current`) rather than the base table, plus a history drawer.
- **ESSENTIAL-IF (Captain approval):** the history writer cut-over is enabled in production while the existing products view still reads the base table by its old key. Reading the base table after the key change would show several generations per product. Either the view switch ships first or the flag stays off.

## 7. Production status versus delivery status (two badges)
| Badge | Values | Source |
|---|---|---|
| Production status | NORMAL, DEGRADED, FAILED | Content and collection only; never derived from delivery |
| Delivery status (per channel) | CONFIRMED, PARTIAL, FAILED, UNKNOWN, UNCONFIRMED | Attempt-level records |

Rules: an empty, boilerplate or placeholder narrative is never NORMAL. UNKNOWN and UNCONFIRMED are shown as such and are never rendered as success. Where a marked authorised recovery resend occurred, both attempts are listed, the resend is labelled "Earlier delivery unconfirmed, resent", and it is counted separately from preventable duplicates. No claim of exactly-once delivery is made. Historical rows with no record display "unrecorded", never NORMAL or FAILED.
- **ESSENTIAL-IF (Captain approval):** delivery badges require the platform notify call to return a structured per-chunk result (a Production Operations dependency). Without it, delivery shows only UNCONFIRMED for chunked sends and the UNKNOWN/PARTIAL distinction cannot be displayed.

## 8. PIR display (shadow)
Priority Intelligence Requirement tags are shadow-only. They are not shown in the Captain-facing brief and do not change selection, ranking or delivery. A diagnostic view may list, per item, matched PIR ids with priority (A national/systemic resilience, B professional/sector, X emerging), the match basis, the unmatched high-severity lane (never capped or hidden) and coverage by PIR. Direct exposure of any specific technology estate is not a display or relevance criterion.
- **FWR:** diagnostic PIR coverage panel.
- **ESSENTIAL-IF (Captain approval):** promoting PIR tags from shadow to the Captain-facing brief or the Workbench, which also needs the shadow-to-enforce approval gate.

## 9. Incident anchors
Each incident has a stable key and an anchor link. The brief mentions an incident in full once; later mentions link to that anchor. The portal incident page carries L3 and L7 for that key and the brief's per-incident reference list. Stable keys are stored with the brief row.
- **FWR:** anchor targets on the existing incident pages.
- **ESSENTIAL-IF (Captain approval):** if the brief starts linking to anchors that do not resolve in the portal, either the portal gains the anchor target or the brief omits the link.

## 10. Summary of future Workbench requirements
1. Products view reads the current-view; shows reporting date, `as_of` age in hours, freshness badge, last-refreshed time.
2. Assessment history drawer.
3. Three axis badges including UNKNOWN posture.
4. Epistemic class tags and legend.
5. Production and delivery badges, resend disclosure, "unrecorded" state.
6. Collection-limits line (always present).
7. Incident anchors.
8. Shadow PIR diagnostic panel.
9. Date display: replace "Generated for <UTC date>" with the Melbourne reporting date.
10. Migration numbering for the products history change is coordinated with HQ (0262 is claimed by an existing HQ change).

Sequencing for any approved application work: persistence first, then the brief block, then the Workbench (the Workbench is last).

## 11. Out of scope
New agents or services, application code, routing or egress changes, and any production enablement. Enabling any flag or applying any schema change requires the approval gates recorded in the Captain's decision pack.
