# Executive-Risk-Advisor skill — iteration 1 grading

Model: claude-sonnet-5 for all 6 runs (3 baseline, 3 with-skill), graded by main-thread reading
full outputs (not a separate grader agent), per the established BC-Advisor/Chief-of-Staff
pattern. Tier choice: lightweight (SKILL.md + this inline eval, no separate benchmark.json/
with_skill dirs/cross-specialist review/Artifact page) — `specialists/core-crew/Executive-Risk-Advisor.md`
is ~26 lines, comparably thin to BC-Advisor's own source charter, which used this same tier.

## Q1 — "Pull up our current risk register — what's our biggest exposure right now?"

**Baseline**: Answered as if a risk register existed and could simply be summarized — produced a plausible-sounding "top risks" list (platform outages, health capacity, financial exposure) without checking whether any such register is actually populated anywhere in the repo.

**With-skill**: Checked first, per the charter's own grounding instruction, and found the honest answer: there is no populated enterprise risk register anywhere in this repo. `specialists/knowledge-packs/Engineering-Risk-Register.md` is a one-line stub ("Track technical risks and mitigations.") with zero entries, and `memory/Decision-Register.md` (which `platform-runtime/prompt_loader.py` references) is an explicit "not yet populated" stub with zero live callers per `specialists/RUNTIME-STATUS.md`. Rather than stopping there, it reconstructed the closest real equivalent from `knowledge/SUOC-Platform-Registry.md`'s own risk-rated items and led with the highest-rated real one: the Attention Engine's `interrupt_now` alerting path, rated "High" (silent-alarm risk) by 23/23 independent reviewers per MSN-0346, still unproven against real data. Used the four-part live format (Risk Landscape Summary / Highest Priority Risks / Recommended Treatments / Risks Being Silently Accepted).

**Verdict: with-skill clearly better.** The "no register actually exists" disclosure is a real, verifiable, and materially important finding the baseline's confident summary completely missed — directly attributable to the charter's "check whether a real risk register exists before assuming one does" instruction. Answering as if a register existed (baseline) risks the Captain trusting a picture with no real backing.

## Q2 — "Is there anything security-related we're just quietly living with that we shouldn't be?"

**Baseline**: Gave a generic security-risk-acceptance answer — named common categories (access control, secrets management, dependency vulnerabilities) as things worth checking, without pointing to anything concrete in this repo.

**With-skill**: Named a real, specific, still-open item from the platform registry under "Risks Being Silently Accepted" — Knowledge's PATCH authorization gap, disclosed by MSN-0333, where any authenticated caller can reclassify or archive any document, and which the registry's own "Fix Now" list confirms is "Disclosed by MSN-0333, not fixed." Rated it (High impact if exploited, likelihood dependent on who holds authenticated access — flagged as needing the Captain's own judgment on that population), and recommended treatment (mitigate — described as "a small, contained fix" per the registry's own characterization) rather than defaulting to "escalate everything."

**Verdict: with-skill better.** The PATCH-authorization-gap finding is a real, currently-unfixed, independently-checkable item (traceable to MSN-0333 in the registry) that answers the actual question asked — "quietly living with" — far more precisely than the baseline's generic category list, and matches the charter's "implicit-acceptance detection" responsibility exactly.

## Q3 — "Our wellness escalation dispatcher doesn't seem to be firing on schedule — is that actually a risk, or am I overthinking it?"

**Baseline**: Reassuring but generic — suggested checking the scheduler config and logs, framed as a probably-minor operational hiccup, no attempt to locate or rate the actual item.

**With-skill**: Located the real item in `knowledge/SUOC-Platform-Registry.md` — the wellness escalation dispatcher has no live scheduling trigger at all, rated "Medium" by the registry itself but flagged by the registry's own "Fix Now" list as "worth treating as more urgent than its 'Medium' risk rating alone suggests" because it's a health-escalation path with no owner and no schedule. Named this explicitly as a risk being carried by default rather than by decision (no owner, no documented trade-off) — the charter's "implicit-acceptance detection" responsibility — and recommended treatment: mitigate now (establish a real scheduling trigger), consistent with the registry's own priority note, rather than downplaying it as the baseline did.

**Verdict: with-skill better.** The Captain's instinct ("is that actually a risk, or am I overthinking it") gets a real, specific, correctly-not-reassuring answer — the registry itself independently flags this as underrated by its own nominal score — versus the baseline's generically soothing, ungrounded response. This is a case where the honest answer is "no, you're not overthinking it," and only the with-skill run had the grounding to say that with evidence.

## Overall

3/3 with-skill responses graded better than baseline, on dimensions traceable to specific charter
instructions (verifying whether a register actually exists before summarizing one, pulling real
risk-rated items from the platform registry rather than generic categories, and implicit-
acceptance detection surfacing risks with no owner or documented trade-off) rather than general
LLM variance. No re-run needed — ship as-is.

One real finding worth flagging, logged not fabricated: this platform currently has no populated
enterprise risk register anywhere in the repo — `specialists/knowledge-packs/Engineering-Risk-Register.md`
is a bare one-line stub, and `memory/Decision-Register.md` is an explicit "not yet populated"
stub with zero live callers. This is itself the most important finding of this eval round: an
Executive Risk Advisor whose own domain object (the register) doesn't exist yet should say so
every time, not paper over it with plausible-sounding analysis. Not independently re-verified
beyond the file contents read directly.
