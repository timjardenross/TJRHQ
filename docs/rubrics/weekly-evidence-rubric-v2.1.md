# Weekly evidence labelling rubric — version 2.1 (FROZEN 2026-11-23; policy direction approved by the Captain)

Identical to rubric 2.0 (`weekly-evidence-rubric-v2.md`, frozen and retained unchanged) except for the changes below. Labels written under 2.0 are retained for audit
and are not silently converted; the five disputed cases are adjudicated in `docs/review/adjudication_pack_v2_escalate.md`.

## Changes
1. **Hard rule replaced.** 2.0: "A brief or partial disruption (minutes long, some customers, regional) is `medium`." 2.1: a brief or partial disruption is `medium`
   **except** that a credible report of a *significant active regional outage of an essential network service* (electricity, telecommunications, water, emergency
   calls) is **E, provisional**. Customer count is a proportionality input, not a universal threshold: about 20,000 customers qualifies; 11,000 still without power
   in the same incident qualifies; 300 customers in a suburb does not; a restored outage does not. Reassess when new evidence arrives.
2. **Escalation record.** For every E and V item record: confirmed vs reported impact; number of affected customers; duration and restoration status;
   critical-service dependencies; geographic scope; source confidence; next verification action.
3. Everything else (six dimensions, outcomes, other hard rules, group/role definitions) is unchanged from 2.0.

## Adjudication outcomes incorporated (Captain, 2026-11-23)
* South Australia regional blackout (about 20,000 properties, restoration in days): **one provisional ESCALATE at incident level**; the three reports are members of that one incident.
* Supermarket freezer cyber-attack: **VERIFY** pending substantiated consequences (store closures or a supply interruption).
* Strait of Hormuz container-ship sinking: **VERIFY** pending evidence of wider disruption (casualties, traffic disruption).
Final decisions with original labels preserved: `docs/review/adjudication_v2_final_decisions.csv`.

## Freeze
Frozen by this commit. Any change creates 2.2 and invalidates labels written under 2.1. The third holdout may be drawn only after the model is also frozen.
