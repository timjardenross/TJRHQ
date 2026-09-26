# Skill Benchmark: chief-engineer

**Model**: claude-sonnet-5
**Date**: 2026-08-09T07:33:04Z
**Evals**: notification-sender-dup-check, advisory-workbench-review, mission-id-drift-governance (1 run each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 100% ± 0% | 78% ± 19% | +0.22 |
| Time | 205.9s ± 68.6s | 146.7s ± 66.5s | +59.2s |
| Tokens | 78197 ± 4195 | 74433 ± 26137 | +3763 |

## Notes

- Eval 0 (notification dup-check) doesn't discriminate: both configs investigate the repo thoroughly and land on the same composition-first conclusion.
- Eval 2 (MSN drift) is the clearest differentiator: without the skill, the model prescribes unilateral action on a governance/process change; with the skill, it explicitly escalates that piece to Captain/Chief of Staff per its own Escalation section. This is the skill's real value-add.
- Eval 1 (advisory-workbench review): the baseline actually surfaced a sharper bug (18-officer vs 5-person specialist registry mismatch) that the with-skill run missed in favor of a test-coverage focus. Worth watching whether structure/escalation focus trades off against investigation depth.
- With-skill runs took ~40% longer on average - expected cost of the fuller persona/format, not a red flag given the pass-rate gain.