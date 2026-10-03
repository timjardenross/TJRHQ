---
status: "accepted"
date: 2026-10-03
decision-makers: Captain TJR
consulted: none recorded — designed and implemented with Claude Code in-session, reviewed via PR
informed: all officers; owners of platform-runtime/lib/resilience/, telegram-bots/, knowledge/regulatory-corpus/
---

# Operational Resilience Advisor: grounded regulatory crosswalk (clause corpus + deterministic validation)

| Field | Value |
|---|---|
| Status | Accepted (implemented) |
| Date | 2026-10-03 |
| Implemented in | PR timjardenross/TJRHQ#334, merge commit `a150944`; change flags in the follow-up PR on branch `claude/exciting-ride-i3nsoz` |
| Owner | Operational Resilience Advisor (USS-TJR-OR-001) / Chief Engineer |

## Context and Problem Statement

The Captain asked for a "Regulatory Framework Crosswalk Agent": map one
operational resilience requirement across APRA CPS 230, BCBS, ISO 22301,
DORA and US guidance. The inspiration was a third-party practitioner guide
(Remver's "Business Resilience AI Agents"). The agent in that guide is a long
system prompt and nothing else. Its quality gate is an instruction to the
model: never fabricate a citation.

For regulatory work that isn't good enough. An invented paragraph number in a
crosswalk is a real liability: someone relies on it, a reviewer can't find it,
and the whole output loses credibility. A prompt can ask the model not to
fabricate. It can't make sure the model doesn't.

How do we build a crosswalk advisor whose citations are checked against
source text, not just against the model's good intentions?

## Decision Drivers

* **No unverifiable citations.** A clause reference has to resolve to
  something we actually hold, or be shown as unconfirmed.
* **Reuse before creation (ADR-020).** An OR-Advisor charter already existed,
  unregistered, at `specialists/core-crew/OR-Advisor.md`.
* **Licensing.** ISO standards are paid and proprietary. BIS documents are
  copyright. Third-party prompts are someone else's work.
* **No new provider or dependency** where the existing Model Router will do.
* **Sensitive input.** Users may paste customer identifiers. Some requests
  (regulator responses, legal advice) are out of scope for any AI drafting aid.
* **Traceability.** Every output should be traceable to the prompt version,
  knowledge packs and corpus that produced it, along with the human review
  decision.

## Considered Options

* **A. Prompt-only agent** (the guide's approach): a long persona prompt with
  a "never fabricate" quality gate.
* **B. Grounded pipeline**: a clause-level corpus, deterministic validation
  in code, one repair attempt, and the output withheld if it still fails.
* **C. Claude API tool-use loop**: the model calls corpus look-up tools
  itself.
* **D. New standalone specialist** in place of the existing OR-Advisor.

## Decision Outcome

Chosen option: **B, built on the existing OR-Advisor and the platform's
existing model stack.** It's the only option that enforces the citation
rule in code instead of asking for it. The eight decisions below make up
the build.

1. **Upgrade the existing charter; don't add a new specialist.**
   `specialists/core-crew/OR-Advisor.md` is now registered as
   `SPECIALISTS["or_advisor"]` in `platform-runtime/prompt_loader.py` and as
   #13 in `specialists/SPECIALIST-INVENTORY.md`. Its knowledge packs
   (`specialists/knowledge-packs/Operational-Resilience-Advisor-Knowledge.md`,
   `Regulatory-Crosswalk-Framework.md`) are written in our own words. The
   third-party prompt was not copied. The Claude Code skill
   `.claude/skills/resilience-crosswalk/` loads the same charter and packs.
   *Rejected:* option D, which would duplicate a capability (ADR-020).
2. **A clause-level corpus as the only source of citable text.**
   `knowledge/regulatory-corpus/*.json` has one file per framework. Each
   clause has a stable ID and a `text_status` of `verbatim`, `summary` or
   `heading_only`. Text only ever enters through
   `platform-runtime/lib/resilience/ingest.py`, from an official source
   document, with SHA-256 provenance. Nothing is typed from memory. As
   merged, the corpus holds framework metadata plus the 7 BCBS d516
   principle headings (`heading_only`). The authoring session had no
   network access to the regulators. APRA CPS 230 is the primary framework
   (`role: primary`), since the Captain works in an Australian/APRA context.
   BCBS, ISO, EU and US frameworks are international or comparative.
3. **A licensing guard in the ingester.** ISO 22301 is marked
   `licence: proprietary`, and `ingest.py` refuses proprietary frameworks
   unless `--licensed` is passed. BIS/BCBS text is limited to headings and
   short, attributed excerpts (see `knowledge/regulatory-corpus/README.md`).
4. **Deterministic enforcement in code.**
   `platform-runtime/lib/resilience/validator.py` and `schema.py` treat the
   following as errors: an unknown framework, a clause ID that isn't in the
   corpus, a clause ID that belongs to a different framework, and HIGH
   confidence with no clause. The pipeline (`pipeline.py`) allows one repair
   attempt (`MAX_REPAIRS = 1`). If the draft still fails, the output is
   withheld. HIGH confidence is downgraded to MEDIUM unless the cited clause
   is held `verbatim`. The verification checklist is built in code
   (`build_verification`), so the model isn't relied on to remember it.
   *Rejected:* option A, which leaves the quality gate as a request the model
   may ignore.
5. **Use the existing model stack.** The default generate function calls
   `llm.try_generate_response`, which goes through the Model Router. No new
   provider or dependency was added. The pipeline is provider-agnostic: the
   generate function is injectable, which is also how the tests run it.
   *Deferred:* option C. Revisit it if the local model can't reliably
   produce schema-valid JSON once real clause text is loaded.
6. **Screen input deterministically before any model call.**
   `guardrails.py` refuses input containing email addresses, Luhn-valid
   card numbers, BSB/account numbers or TFN-like 9-digit IDs. It also
   refuses requests to draft regulator responses, remediation plans for
   supervisory findings, legal advice or official positions. This is a cheap
   local check that runs before, and separately from, the outbound-prompt
   guardrails in ADR-032 (`core/security/llm_guardrails.py`).
7. **Keep an append-only audit trail with human review.** `audit.py` writes
   JSONL records to `data/resilience-crosswalk/audit.jsonl` (gitignored).
   Run records capture the prompt version, knowledge-pack hash and corpus
   fingerprint. Review records capture the Captain's accepted, edited or
   rejected decision. The advisor is framed as a research and drafting aid,
   not a decision model (SR 11-7-style framing): a human reviews every
   output.
8. **A Telegram front-end with no action capability.**
   `telegram-bots/resiliencebot/` (`@resiliencetjr_bot`, deployed by
   `deploy/tg-resiliencebot.service`) runs crosswalks for a Captain-only
   allowlist. It takes no host or shell actions. XO remains the only
   action-capable bot. The XO-only policy limits which bot can take actions,
   not how many bots exist (see `USS-TJR-Control/README.md`).

### Consequences

* Good, because a fabricated or cross-framework clause ID can't reach the
  Captain. It is repaired once or withheld.
* Good, because confidence ratings are tied to what we actually hold, not
  to the model's own judgement.
* Good, because licensing is enforced at the single entry point for text.
* Good, because the audit log makes any crosswalk reproducible and
  reviewable after the fact.
* Bad, honestly: until CPS 230 text is ingested, nearly every citation
  renders "reference not confirmed", and BCBS d516 mappings are capped at
  MEDIUM. The pipeline works, but its output is mostly a checklist of
  things to verify until the corpus is filled.
* Bad, because ingestion has an ongoing cost. Each framework and each
  revision has to be downloaded, extracted and re-ingested by hand.
* Bad, because the `apra`/`bcbs` parsers are heuristic. Every ingest needs a
  human to review the diff before it's committed.
* Neutral, because one more Telegram bot means one more systemd unit and
  Infisical folder (`/bots/resiliencebot`) to keep running.

### Confirmation

* `platform-runtime/tests/test_resilience_crosswalk.py` covers the validator,
  the repair-then-withhold path, the HIGH→MEDIUM downgrade, the input screen
  (refusing before any model call), audit records and the ingester's
  proprietary-licence refusal, using an injected generate function.
* `telegram-bots/resiliencebot/test_resiliencebot.py` covers the bot
  front-end.
* `cd platform-runtime && python -m lib.resilience.cli coverage` reports what
  the corpus holds for each framework.

## Pros and Cons of the Options

### A. Prompt-only agent

* Good, because it's quick to build and needs no corpus.
* Bad, because the quality gate depends on the model obeying it. That's the
  failure mode this ADR exists to remove.
* Bad, because nothing records which clause text a citation was based on.

### B. Grounded pipeline (chosen)

* Good, because citations are checked against held text in code.
* Good, because it reuses the existing charter, prompt loader and Model
  Router.
* Bad, because its usefulness is bounded by corpus coverage, which is thin
  today.

### C. Claude API tool-use loop

* Good, because the model could look up clauses itself, which may give
  better recall on large corpora.
* Bad, because it adds a new provider path and a new external-cloud
  dispatch point that ADR-032 would have to cover.
* Neutral, because the validator would still be needed, since tool use
  doesn't stop the model citing something it never looked up.

### D. New standalone specialist

* Bad, because it duplicates the existing OR-Advisor charter (ADR-020) and
  would add a third description of the specialist roster to keep in sync.

## More Information

* Applies ADR-020 (capability reuse before capability creation).
* Relates to ADR-032 (LLM application security baseline). The input screen
  here is a separate, domain-specific pre-check. It doesn't replace ADR-032's
  outbound guardrails, and it doesn't add to ADR-032's coverage list,
  because generation goes through the existing Model Router.
* Relates to ADR-024 (resilience intelligence convergence). Regulatory
  change flags reuse the existing intelligence pipeline rather than a new
  collector: a daily `resilience_change_scan` job in the existing
  `intelligence/scheduler.py` (no new scheduler instance) matches recent
  APRA/BIS events against each framework's `watch` rules in the corpus files
  and records flags in `data/resilience-crosswalk/change_flags.jsonl`
  (`platform-runtime/lib/resilience/change_flags.py`). Open flags add a
  validator note and a verification item to any crosswalk touching that
  framework; they never block one. The job's heartbeat domain is registered
  by migration 0228, following migration 0171's lesson that unregistered
  heartbeats silently 409. Frameworks with no feed (EU, US, ISO) aren't
  watched, and `/coverage` says so.
* Open items:
  1. ~~Ingest CPS 230~~ — done 2026-10-03: 60 paragraphs, verbatim, from APRA's PDF (SHA-256 in
     the corpus file). Next: DORA, then BCBS d516 text.
  2. Apply migration 0228 on Supabase so the change-scan heartbeat lands.
     Add feeds for the unwatched issuers (EU, US) if those frameworks matter.
  3. Golden-crosswalk evals and guardrail red-team evals against a real
     model.
  4. A possible model-escalation decision (revisit option C) once real text
     is loaded and schema-valid JSON rates are known.
