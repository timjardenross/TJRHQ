# Capacity gating is advisory for now (owner decision, 2026-10-18)

**Decision.** Capacity is still measured and shown everywhere it was. A Red, Amber or Unknown reading no
longer holds anything back: no nudges are trimmed, no missions are deferred or limited, and the
improvement budget does not close on Red. This is for the time being.

**Why.** The daily capacity signal is not linked into HQ yet. The TJR Life phone app is a capture source,
not a decision helper; aggregation, trends and alerts on problems belong in HQ and will come from a future
link between the two. Until then, gating on a missing or thin signal holds things back for no good reason.

**What changed.** `core/health/capacity_enforcement.py` is a single switch (`CAPACITY_ENFORCEMENT`,
default `advisory`). It is read in five places: the follow-through engine's `_apply_capacity_gate`, the
D-055 `CapacityGate` (emits one advisory notice instead of defer / limit / recovery actions), the
improvement budget (sized as Green, Red does not block), Number One's `get_health_adjusted_queue`
(the mission workbench queue: no DEFERRED / P0-only marks, normal focus list), and the recommendation
engine (no Red score reduction; health notes become pacing notes, never a defer instruction), shared
Attention State (Red no longer demotes items to can_wait; this also covers personal-task attention and
`/remember`), the Command Bus (HIGH escalations are no longer held on Red), and Remember's capture limit
(one common limit instead of per-band caps). Reported values (`capacity_status`, the governance
statement) are unchanged apart from saying "advisory".

**How to reverse it.** Set `CAPACITY_ENFORCEMENT=enforce`. That restores the original D-055 behaviour exactly
(the pre-existing tests run with it on). Reverse it when the HQ-side capacity link exists.

**Scope exception.** The Mission Workbench "Suitable today" filter is an opt-in view (default is All), not a
hold-back; it is unchanged, and its overcommitment warning now reads as advice only.

**Not changed.** Discovery was never gated. Quiet hours and daily caps in the follow-through engine are not
capacity gates and are untouched. The D-055 record itself stands; this is a time-boxed easing of its
enforcement.
