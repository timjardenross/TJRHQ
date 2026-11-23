# Weekly evidence labelling rubric — version 2.0 (FROZEN 2026-11-23; approved by the Captain)

Supersedes rubric v1 (the labels in `weekly_evidence_eval_set.json`, `weekly_evidence_holdout_set.json` and
`labels_holdout2_reviewer{A,B}.json` were written under v1 and are retained unchanged for audit history). v2 labels are written to
separate files tagged `"rubric_version": "2.0"`. Any change to this text creates v2.1 and invalidates labels written under 2.0.

Label each headline from its title, source, time and geography only. If a fact is not in the headline, it is not known: do not infer it.

## Six dimensions (record all six for every event)
1. **sector_tier** (relevance only; it never determines materiality or priority by itself)
   * 1: energy, telecommunications, healthcare, water, financial infrastructure, transport, aviation, emergency services
   * 2: cloud platforms, major technology providers, food supply, retail distribution, government services
   * 3: consumer services, recreation, tourism and other context-dependent entities; also "none" for no recognisable sector (write `null`)
2. **event_type**: `outage` | `cyber_incident` | `data_breach` | `vulnerability` | `physical` | `other_incident` | `none`
3. **impact_status**: `confirmed` (the headline states a consequence: service down, data stolen, flights grounded, power cut, safety harm) |
   `unconfirmed` (an incident is reported but no consequence is stated, e.g. "investigating a cyber incident") | `retrospective`
   (a past, resolved event: complaints, compensation, AGM, review) | `potential` (warnings, risks, commentary, analysis) | `none`
4. **materiality** (operational, from the stated consequence): `high` = severe operational disruption, major safety consequences,
   essential-service interruption or cascading impact; `medium` = real but limited/brief/partial impact, or a serious unconfirmed
   Tier 1 incident; `low` = no operational incident.
5. **evidence** (how well the headline's source supports it): `primary` (regulator, vendor or operator notice) | `mainstream`
   (established news outlet) | `weak` (aggregator, status feed with no detail, blog, unverified claim).
6. **urgency**: `immediate` (ongoing or just happened and needs a decision now) | `soon` | `routine`.

## Outcome (expected_priority)
* **E — ESCALATE:** credible evidence of severe operational disruption, major safety consequences, essential-service interruption or
  cascading impact. One credible source is enough (mark `provisional: true` when evidence is a single mainstream/primary source).
* **V — VERIFY:** potentially material incident with unresolved facts or consequences (including an unconfirmed breach or cyber incident
  with no stated operational consequence, and a serious claim from a weak source).
* **W — WATCH:** relevant development with no immediate operational decision.
* **R — REFERENCE:** background or low-materiality intelligence.

## Hard rules
* A sector or tier alone never makes an event E. Tier 1 weights a stated consequence; it is not a consequence.
* An unconfirmed breach is not E (it is V). A CISA known-exploited-vulnerabilities listing is not E by itself; an advisory is E only if
  exploitation is stated AND the headline names an affected product/service widely used in essential services AND the source is primary.
* Retrospective items and commentary/analysis/roundups are never E.
* A brief or partial disruption (e.g. minutes long, some customers, regional) is `medium`, not `high`, unless a safety consequence is stated.
* Incident groups: label the same real-world incident across headlines with one `group` slug (same organisation/service/event within days);
  a different incident at the same organisation is a different group; commentary about an incident joins that group with role `commentary`;
  a copy of another headline with a wire suffix has role `syndicated`; otherwise `original`. Use `null` for unique events.
* If a headline is too vague to judge, choose the lower-impact label and write "unclear".

## Output per event
`{"id","sector_tier":1|2|3|null,"event_type","impact_status","materiality","evidence","urgency","priority":"E|V|W|R","provisional":bool,"group":null|slug,"role":"original|commentary|syndicated","note":"<=12 words"}`
