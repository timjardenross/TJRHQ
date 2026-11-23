# Weekly evidence labelling rubric — version 2.1 (DRAFT for freeze; awaiting the Captain's sign-off)

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

## Freeze procedure
The text is frozen by committing it with the Captain's explicit approval, after which any change creates 2.2. The third holdout may be drawn only after this freeze and
the model freeze.
