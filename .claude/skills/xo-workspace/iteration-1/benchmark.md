# Skill Benchmark: xo

**Model**: claude-sonnet-5
**Date**: 2026-08-09T09:23:17Z
**Evals**: capacity-triage, stage-skip-resistance, gatekeeper-auth-merge (1 run each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 100% ± 0% | 78% ± 39% | +0.22 |
| Time | 42.6s ± 13.4s | 56.1s ± 34.7s | -13.5s |
| Tokens | 50439 ± 5324 | 51389 ± 10259 | -949 |

## Notes

- Eval 0 (capacity-triage) is the clear differentiator: the baseline defaults to a long, headed, numbered-list "helpful assistant" response even for a short, direct question - the skill's brevity/voice instruction is doing real work.
- Evals 1 (stage-skip) and 2 (gatekeeper-auth-merge) don't discriminate - a capable baseline reasons its way to the same verdicts unprompted, sometimes with extra findings (eval 1's baseline independently found a real ungated PATCH-route governance gap).
- With-skill runs were faster and used fewer tokens on average here - the short companion-mode answer pulls the average down, not a general rule.