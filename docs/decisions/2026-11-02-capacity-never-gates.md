# Capacity never holds work back (owner decision, 2026-11-02)

**Supersedes:** [2026-10-18 capacity gating is advisory](2026-10-18-capacity-gating-advisory.md) and the
enforcement half of D-055.

**Decision.** A capacity reading (Green, Amber, Red or Unknown) is information for the Captain. It never
trims a nudge, defers or limits a mission, closes the improvement budget, demotes an attention item,
holds an escalation, reorders recommendations or changes how much Remember surfaces. Capacity is still
measured, stored and shown everywhere it was.

**Why.** The 2026-10-18 note eased gating "for the time being" but left the enforce path in place, so a
single environment variable could bring score-driven limits back. The aim is more good days, and that
needs a model built around the Captain's own judgement, with the score as one input to a plan he can
accept or ignore. A score that can silently hold work back works against that. The research behind this
(boom-bust pacing, masking debt, N-of-1 self-tracking) is thin and observational, which is another
reason not to let a three-way zone decide what is allowed.

**What changed.**
- Removed `core/health/capacity_enforcement.py` and the `CAPACITY_ENFORCEMENT` switch. There is no
  enforce mode to turn back on.
- `CapacityGate.evaluate()` returns one advisory `notify` action for Red or Amber and nothing for Green
  or Unknown. The defer, limit and recovery actions, the Amber cap of 2 and the Command Memory gate log
  are gone. The signature is unchanged.
- Follow-through engine: `_apply_capacity_gate` returns candidates unchanged. Quiet hours and the daily
  cap are not capacity gates and are untouched.
- Improvement budget: always sized as Green; the Red close and the Captain-override exception path are
  gone (`captain_override` is still accepted and ignored).
- Number One queue, attention state, recommendation engine: Red and Amber add an advisory note only.
  Nothing is marked deferred, P0-only or demoted, ranking is untouched, and the focus list is not narrowed.
- Command Bus: HIGH escalations are no longer held on Red.
- Remember: one common limit (30), not per-band caps.
- Tests that asserted the old behaviour now assert the new rule (`tests/test_capacity_never_gates.py`
  and the rewritten per-module capacity tests).

**Not changed.** The check-in flow, `capacity_checkins`, the 90/60/25 nominal scores, reported values and
the Mission Workbench "Suitable today" view. The D-055 record itself stands as history.

**Safeguards.** Only the Captain defers or pauses work. If a softer protection is wanted later, it
should be an action the Captain takes ("protect today"), not something a score triggers.

**Next.** Step 2 (a day plan from the full check-in) and step 3 (a good-day definition and metrics) are
separate changes.
