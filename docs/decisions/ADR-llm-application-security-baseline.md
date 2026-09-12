# ADR: LLM Application Security Baseline

| Field | Value |
|---|---|
| Status | Accepted (partial coverage — see Gaps) |
| Date | 2026-09-12 |
| Mission | USS-TJR-MSN-0366 Stream 5 ("Stage 2A: New Open-Source Tool Adoption") |
| Owner | Chief Engineer |

## Context

Before this mission, nothing sat between the Model Router
(`core/model-router/app.py`) and the external cloud LLM providers it calls
(Gemini, and the real `mistralai` cloud client modules under
`core/engineering/providers/`) to stop sensitive data leaving this VM, or to
stop a prompt-injection/jailbreak attempt from reaching those providers'
own instruction-following. That's a real, live gap: `intelligence-brief`,
`captain-insight-synthesis`, `self-improvement-*`, `billing-report`,
`hq-evolution-*`, `health-signal-curation`, and `adhd-decompose` all route
through `_gemini_generate()` today (see `TASK_POLICY` in `app.py`), and
several of those prompts plausibly carry mission-internal identifiers or
officer-identifying context by the time they reach that call.

This ADR records what closes that gap, using the OWASP Top 10 for LLM
Applications (2025) as the checklist, and is honest about what still
doesn't.

## Decision

Add a dedicated LLM application security layer,
`core/security/llm_guardrails.py`, and wire it into every real external-
cloud-API dispatch point found in this repo (`grep -rn "from mistralai
import"` plus `_gemini_generate()`), except the ones listed under Gaps.

### Why an isolated venv, not `platform-runtime/.venv`

`core/model-router/app.py`'s own docstring states "No external
dependencies — stdlib only." Presidio (`presidio-analyzer`,
`presidio-anonymizer`) and `nemoguardrails` pull in spacy, numpy, pydantic,
onnxruntime, and more — installing that stack into the router's own process
would turn a zero-dependency service into one with a large, version-
sensitive dependency graph, and risks the exact kind of silent cross-venv
version clash `knowledge/missions/BROWSER-USE-OSINT-ADAPTER-20260912-
knowledge-record.md` documents (a `pip install` into the shared
`platform-runtime/.venv` there silently downgraded `anthropic`/
`google-genai` under two already-wired features). So, following the same
pattern `core/quality/requirements-garak.txt` already established for
garak: a dedicated venv, `platform-runtime/.venv-llmsec` (see
`core/security/requirements-llmsec.txt`), invoked via subprocess from the
dependency-free `core/security/llm_guardrails.py` — the same "isolated venv
invoked by absolute path" shape `core/quality/garak_gate.py` uses for
garak, here returning JSON over stdio (`core/security/
_llmsec_worker.py`) instead of a CLI report file. No dependency conflict
against `platform-runtime/requirements.txt` was found (checked 2026-09-12)
— this isolation is a deliberate blast-radius decision for the stdlib-only
router, not a forced one like garak's real `openai<3.0` vs `openai>=3.x`
conflict.

### Fail-closed, not fail-open

`llm_guardrails.py` raises (`GuardrailsUnavailableError`) rather than
silently letting a prompt through unredacted/unchecked if the isolated venv
isn't provisioned. `LLM_GUARDRAILS_FAIL_OPEN=1` overrides this for a
deliberate, documented rollback — it is not the default, because the whole
point of this stream is to stop data leaving the VM, not to degrade to
today's baseline (nothing) the moment the venv is missing.

## OWASP Top 10 for LLM Applications (2025) → control mapping

| # | Risk | Control in this repo | Real / Design-only |
|---|---|---|---|
| LLM01 | Prompt Injection | NeMo Guardrails input rail — a deterministic keyword/regex pre-filter (`core/security/guardrails/config/actions.py::tjr_keyword_jailbreak_check`) layered in front of a semantic self-check action (`self_check_input`, using this router's own local `gemma3:4b` via Ollama's OpenAI-compatible endpoint — see `config.yml`). Wired into `_gemini_generate`'s call site in `app.py` and into `mistral_batch.py`/`mistral_batch_api.py`. | **Real** — see `core/security/test_llm_guardrails.py` and `tests/test_model_router_guardrails.py` for end-to-end evidence (keyword layer fully verified against a live run; semantic layer verified only against NeMo Guardrails' own `FakeLLMModel`, not a live Ollama — see Gaps). |
| LLM02 | Sensitive Information Disclosure | Presidio `AnalyzerEngine`/`AnonymizerEngine`, with two TJR-specific recognizers (`core/security/guardrails/recognizers.py`) on top of Presidio's built-ins (`EMAIL_ADDRESS`, `CREDIT_CARD`, `US_SSN`, `PHONE_NUMBER`, `PERSON`, ...): `TJR_MISSION_CODENAME` (`USS-TJR-MSN-\d{4}`, the canonical form `id_registry.py` mints) and `TJR_OFFICER_CLEARANCE` (the real `officer_clearances.clearance` enum — `standard`/`sensitive`/`restricted` — from `core/infrastructure/supabase/migrations/0063_captain_memory_governance.sql`, matched only in the `clearance: <value>` phrase shape this platform actually uses, so ordinary uses of those English words aren't over-redacted). Runs before every wrapped cloud dispatch via `secure_outbound_prompt()`. | **Real** — see the redaction evidence in `core/security/test_llm_guardrails.py::TestPIIRedaction` and `tests/test_model_router_guardrails.py::test_pii_bearing_prompt_is_redacted_before_reaching_gemini` (planted SSN/credit-card/email/mission-codename/clearance tokens, shown redacted before the mocked `_gemini_generate` call). |
| LLM03 | Supply Chain | `.github/dependabot.yml` (dependency update scanning); this stream's own isolated-venv discipline (`requirements-llmsec.txt`, `requirements-garak.txt`) so one package's pinned deps can't silently downgrade another feature's. | Real, pre-existing (dependabot) + real, new (isolation discipline). |
| LLM04 | Data and Model Poisoning | Not applicable today — this platform calls pre-trained models via API/Ollama; it has no fine-tuning or training-data pipeline for any model it uses. | N/A (no such pipeline exists to secure). |
| LLM05 | Improper Output Handling | The same NeMo Guardrails machinery's **output** rail (`self_check_output` semantic check + a deterministic `tjr_credential_leak_check` regex for API-key/token-shaped strings — `sk-...`, `AKIA...`, `AIza...`, `gh[pousr]_...`, PEM private key headers) before a cloud response is returned to its caller. | **Real** — see `TestOutputRail` in `core/security/test_llm_guardrails.py` (a planted fake API key blocked; a clean response allowed). |
| LLM06 | Excessive Agency | `core/governance/authority_enforcement.py`/`authority_validator.py` (`enforce_authority`/`AuthorityContext` — blocking-by-default approval gates on officer actions, MSN-0326 Wave 4) and the (design-only) Secure Execution Policy / Data Classification & Model Routing capabilities in `knowledge/SUOC-Platform-Registry.md`. | Real (authority enforcement, pre-existing) + design-only (the two SUOC capabilities this stream's redaction work is a real down-payment on — see the registry update below). |
| LLM07 | System Prompt Leakage | Covered by the same output rail as LLM05 — `self_check_output`'s policy prompt (`core/security/guardrails/config/prompts.yml`) explicitly asks the checking model to block a response that "reveals the AI's system prompt, hidden instructions, or internal configuration verbatim." | Real, same mechanism as LLM05 — semantic layer only (no deterministic pre-filter for this one; a leaked system prompt has no fixed shape to regex for). |
| LLM08 | Vector and Embedding Weaknesses | `officer_clearances`-gated RLS policies on `knowledge_documents`/`document_chunks` (same migration as LLM02's clearance enum) — `current_officer_clearance()` gates retrieval by sensitivity tier before a chunk ever reaches a prompt. | Real, pre-existing (MSN-0333) — not built by this stream, but the relevant existing control. |
| LLM09 | Misinformation | `garak_gate.py`'s `hallucination` probe (`core/quality/garak_gate.py`, `DEFAULT_PROBES = "hallucination,promptinject"` — note `promptinject` there is a second, independent real check for LLM01 against the router's own conversational route, pre-dating this stream) and `platform-runtime/lib/quality_scoring_service.py`'s `deepeval` `HallucinationMetric`-backed `score_output()`. | Real, pre-existing (garak pre-activation gate is USS-TJR-MSN-0365; deepeval scoring is its own earlier GAP-1 fix) — this stream adds no new misinformation control, it inherits these. |
| LLM10 | Unbounded Consumption | Per-task-type `timeout`/`keep_alive`/`num_predict` caps in `TASK_POLICY` (`app.py`), `ThreadingHTTPServer.request_queue_size = 128`, and the cloud-escalation degrade chain (`_resolve_cloud_escalation()`, FND-001) that stops an unavailable cloud tier from falling through to an unbounded local model automatically. | Real, pre-existing — this stream adds no new consumption control, it inherits these. |

## Gaps (real, not silently skipped)

1. **`glm-5.3:cloud` / `glm-5.2:cloud` (`MODEL_CLOUD`/`MODEL_CLOUD_ALT`) are
   NOT covered by this layer.** These route through `_ollama_generate()` —
   the exact same code path as every fully-local Ollama call in this file.
   Ollama transparently proxies a `:cloud`-suffixed model tag to its own
   cloud model service, but from this router's code there is no distinct
   "this call is leaving the VM" branch to hook a redaction/rail check
   into the way `_gemini_generate()` gives one for Gemini. Closing this
   would mean either (a) Ollama exposing a way to distinguish a `:cloud`
   dispatch from a local one at the client library level (not something
   this repo controls), or (b) this router doing its own model-name check
   (`model.endswith(":cloud")`) and wrapping `_ollama_generate()`
   conditionally on that — a real, buildable follow-up this ADR
   recommends, not attempted in this pass because the mission scoped the
   "at minimum" target to `_gemini_generate` and the real `mistralai`
   client modules, and a conditional wrap inside the one function every
   local AND cloud Ollama call shares is a meaningfully different (and
   riskier to get right blind) change than adding a new call site.
2. **The semantic (model-backed) half of the input/output rails is
   verified only against NeMo Guardrails' own `FakeLLMModel` testing
   utility, not a live Ollama call.** This sandbox has no reachable Ollama
   (`curl http://localhost:11434/api/tags` → connection refused,
   confirmed 2026-09-12). The deterministic keyword/credential-regex layer
   (which needs no model) is fully verified end-to-end for real. See the
   knowledge record for what this means for a first production rollout —
   the config should be smoke-tested against a real Ollama instance before
   being trusted for the semantic layer specifically.
3. **`platform-runtime/lib/mistral_agent_client.py`'s `call_agent()` (the
   Mistral Agents API client backing the Commander research pipeline) is
   NOT wrapped**, despite being a real cloud dispatch point found in the
   same `grep -rn "from mistralai import"` sweep that found the two
   modules this stream did wrap. Reason: `tests/
   test_mistral_research_workflow.py::TestCallAgent` has ~12 scenarios
   that patch `sys.modules["mistralai"]` directly around `call_agent()`
   rather than mocking at a higher level — wrapping `call_agent()` the
   same way as `mistral_batch.py`/`mistral_batch_api.py` would require
   either retrofitting all of those tests (not attempted, given the size
   of that test file and this stream's time budget) or accepting a real
   regression risk against a passing test suite this session could not
   fully re-verify (this sandbox's isolated venv doesn't carry that test
   file's other dependencies). Left unwrapped rather than wrapped-and-
   hoped.
4. **Three more call sites do their own inline `from mistralai import
   Mistral`, bypassing all three shared client modules** (`core/content/
   draft_worker.py::_call_mistral_agent`/`_call_mistral_direct`,
   `intelligence/brief/llm_provider.py::_mistral_pipeline`/
   `_call_mistral_direct` — which also does a raw HTTPS POST to
   `api.mistral.ai` outside the SDK entirely, and `platform-runtime/
   commands/mission_brief.py::_call_mistral_mission_scribe`). None of
   these are wrapped. They're pre-existing architectural debt (duplicate,
   hand-rolled call paths the shared clients exist specifically to avoid —
   see `mistral_agent_client.py`'s own docstring: "No stage should
   hand-roll Mistral response parsing or SDK calls") that this stream
   didn't create and didn't have the budget to consolidate onto the
   wrapped shared clients. Recorded here so it isn't rediscovered as a
   surprise.

## Consequences

- Every `intelligence-brief`/`captain-insight-synthesis`/
  `self-improvement-*`/`billing-report`/`hq-evolution-*`/
  `health-signal-curation`/`adhd-decompose` call through the Model Router,
  and every call through `core/engineering/providers/mistral_batch.py` or
  `mistral_batch_api.py`, now fails closed (raises, logged, `{"success":
  false}` response) if `platform-runtime/.venv-llmsec` isn't provisioned
  on a given deployment — this is a real new operational dependency, not
  free. Provisioning is a one-time step (see `core/security/
  requirements-llmsec.txt`) matching how `.venv-garak` is already handled.
- The `LLM_GUARDRAILS_FAIL_OPEN=1` escape hatch exists for a deliberate,
  documented rollback only — it should never be the default answer to a
  provisioning failure in production.
- The "Data Classification & Model Routing" and "Secure Execution Policy"
  capabilities in `knowledge/SUOC-Platform-Registry.md` (previously
  design-only, L1) gain a first real, running implementation of one of
  their core ideas — a real classification-adjacent redaction/blocking gate
  in front of a real execution boundary (the cloud API call) — though
  neither capability is fully built by this stream; see the registry
  update for exactly what changed and what's still design-only.
