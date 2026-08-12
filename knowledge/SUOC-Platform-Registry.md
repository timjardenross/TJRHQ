# SUOC Platform Registry

**This is a living document, not a report.** It is one of Starship's four canonical architecture artefacts (see [Canonical Architecture Artefacts](#canonical-architecture-artefacts)) and must always reflect the current engineering state of the Starship Unified Operating Core.

---

## Registry Metadata

| Field | Value |
|---|---|
| **Registry Version** | 2.12 |
| **Last Architecture Review** | 2026-08-12 (added REVS Content Generation Agents as a new capability — built, tested, and specialist-reviewed this session, previously missing from the Registry entirely per Chief Engineer's composition-first finding. No other capability's figures touched by this pass.) |
| **Previous Review** | 2026-07-17 (ad hoc CMDB extension — cross-referenced every "built not live" claim across ~25 missions against fresh git log + live Supabase row counts rather than trusting memory dates; added CMDB Status/Risk/Built-Deployed-Wired-Live/Category/Recommendation to every capability; added the non-capability Asset Registry and Prioritised Remediation Roadmap below. Source: `reports/LIVE-24-7-OPERATIONS-AUDIT-2026-07-17.md`, `reports/BUILT-VS-LIVE-CONSOLIDATED-REGISTRY-2026-07-17.md`) |
| **Platform Capability Count** | 32 (was 31; +1 for REVS Content Generation Agents) |
| **Non-Capability Assets Tracked** | 15 (see Asset Registry) |
| **Average Capability Maturity** | not recomputed this pass — one L2 addition to a 31-capability average shifts it negligibly; not worth a false-precision figure without redoing the full weighted calculation |
| **Average Engineering Confidence** | not recomputed this pass, same reasoning — REVS itself is 65% |
| **Capabilities by Maturity** | L1: 5 · L2: 19 · L3: 7 · L4: 1 · L5: 0 |

---

## SUOC Platform Principles

These are platform invariants. They rarely change, and every future engineering decision should be evaluated against them.

1. **One Operating Core.** Starship is one platform, not a federation of independently-evolving systems.
2. **Whole-of-System Thinking.** No component is complete until it can be discovered, linked, monitored, governed, queried, and evolved by the wider system (ADR-027).
3. **Reuse Before Rebuild.** Existing capability is extended before new capability is created (ADR-020).
4. **Borrow Architecture, Own the Platform.** External research and frameworks inform design; the Operating Core itself stays self-hosted, inspectable, and owned (MSN-0210H).
5. **One Canonical Implementation per Capability.** When duplicates are found, converge onto one — don't let two correct-looking mechanisms silently disagree.
6. **Explicit Governance.** Undefined authority/policy states are configuration errors to be surfaced, not silent defaults to be picked arbitrarily.
7. **Learn From Execution.** Confidence, quality, and outcome data feed back into the platform rather than being discarded after a single use.
8. **Platform Services Before Domain Services.** Domain services consume shared platform primitives rather than each inventing their own.
9. **Captain Intelligence Is Composed, Not Implemented.** The Captain Intelligence Core must remain an orchestration layer that consumes existing Platform Capabilities rather than creating new primitives (MSN-0301, Captain-affirmed).

---

## Captain Dashboard

**Column guide for the 5 CMDB fields added 2026-07-17:** *CMDB Status* — Active (live and doing real work) / Degraded (live but producing misleading or incomplete output) / Dormant (built+wired but zero real activity) / Design-Only (no implementation, by scope) / Broken (was live, has regressed). *Risk* — impact if left exactly as-is: Low/Medium/High. *B·D·W·L* — Built · Deployed · Wired · Live-data, each Y/N/~ (~ = partial); "Live-data" means real rows/traffic in the last verification pass, not a historical claim. *Category* — Operational Issue (should be running cleanly and isn't) / Architectural Debt (duplication, competing implementations, incomplete convergence) / Design-Stage (correctly not built yet) / Healthy (no debt worth naming). *Recommendation* — Fix Now / Fix Later / Replace / Retire / Leave As-Is, judged against today's architecture, not historical intent.

| Platform Capability | Current Status | Maturity | Confidence | Owner | CMDB Status | Risk | B·D·W·L | Category | Recommendation | Next Evolution |
|---|---|---|---|---|---|---|---|---|---|---|
| Governance | Fragmented, consolidation planned | L2 | 55% | Chief Engineer / Number One | Active (fragmented) | Medium | Y·Y·~·Y | Architectural Debt | Fix Later | ADR-registry consolidation (recommended, not yet run) |
| Permissions | One canonical mechanism, enforced by default, real callers dormant | L3 | 85% | Chief Engineer | Dormant | Medium | Y·Y·Y·N (0 audit rows, confirmed 2026-07-17) | Operational Issue | Fix Later | Re-verify approval-blocking if a real overlap case is ever authored |
| Audit | Operational, 2 real callers | L3 | 85% | Chief Engineer | Active (`audit_events`) / Dormant (`authority_audit_log`) | Low | Y·Y·~·~ | Operational Issue (partial) | Leave As-Is | Wire Notification's call log into `audit_events` |
| Notification | Validated standalone, zero production callers | L2 | 80% | Chief Engineer | Dormant | Low | Y·N·N·N | Architectural Debt | Fix Later | `command_bus.py` cutover (held) |
| Configuration | Implemented, zero adopters | L2 | 70% | Chief Engineer | Dormant | Low | Y·N·N·N | Architectural Debt | Fix Later — Retire if still zero adopters at next review | Migrate one real service to prove adoption |
| Model Router | Stable, canonical, widely used | **L4** | **99%** | Chief Engineer | Active | Low | Y·Y·Y·Y | Healthy | Leave As-Is | None planned — reference implementation |
| Knowledge | Sensitivity enforcement shipped: RPC-level SQL fix + RLS/officer_clearances + shared accessors, verified against real data | L3 | 84% | Knowledge domain | Active | Medium (disclosed PATCH auth gap) | Y·Y·Y·Y | Operational Issue (auth gap) / Architectural Debt (manual graph sync) | Fix Now (PATCH authorization gap — any authenticated caller can reclassify/archive any document) | Search readiness now safely buildable; add officer-management UI when a 2nd officer exists |
| Search | Fragmented (6 implementations) | L2 | 63% | TBD | Active (per-implementation) | Low-Medium | Y·Y·Y·Y | Architectural Debt | Fix Later | Wave 4 consolidation (mission not yet assigned) |
| Confidence | Activated, narrow scope, verified end-to-end | L3 | 78% | Chief Engineer | Degraded | Low | Y·Y·Y·N (`quality_scores`=0 rows since test cleanup, confirmed 2026-07-17) | Operational Issue | Fix Later — re-verify live-fire before assuming broken | Extend beyond research/comms into remaining decision domains |
| Task Engine | First real adopter live (vm-processing, dual-write) | L2 | 82% | Chief Engineer | Degraded | Medium | Y·Y·Y·N (`tasks`/`task_events`=0 rows, contradicts "live-verified", confirmed 2026-07-17) | Operational Issue | Fix Later — re-test dual-write in the real vm-processing environment | Observe production cycles; audit other modules for the same portability bug |
| Event Bus | 12 real emit-points live (was 3); `intelligence.signal.ranked` confirmed live (MSN-0343) | L2 | 85% | Chief Engineer | Active | Low | Y·Y·Y·Y (7,710 rows, confirmed 2026-07-17) | Healthy | Leave As-Is | Audit raw_client portability bug across remaining Wave 3 modules |
| Unified Memory | First real adopter live (Officer Context route) | L2 | 65% | Chief Engineer | Dormant (sole caller is itself dead code) | Low | Y·Y·~·N | Architectural Debt | Fix Later | MSN-0210D still blocks the temporal-knowledge route |
| Operational Pattern Library | 9 real patterns; first real consumer wired (XO `/patterns`, MSN-0343) — pending a credential-config fix before it's live-functional | L2 | 78% | Chief Engineer | Active (static) / Degraded (`/patterns`) | Low | Y·Y·~·~ | Operational Issue | Fix Later — confirm `/patterns` live post credential fix | Credential fix looks applied (`SUPABASE_SERVICE_ROLE_KEY` now present in XO env, 2026-07-17) — confirm `tg-xo.service` picked it up |
| Number One Execution Bridge | Operational, stable, single domain | L3 | 90% | Chief Engineer / Number One | Active | Low | Y·Y·Y·Y | Healthy | Leave As-Is | None planned |
| Execution Engine Interface | Designed only (no implementation, per scope) | L1 | 40% | Chief Engineer | Design-Only | N/A | Y(design)·N·N·N | Design-Stage | Leave As-Is | Awaits parallel Hermes evaluation outcome |
| Scheduling | Fragmented (5 apscheduler instances) | L2 | 65% | TBD | Active (per-instance) | Medium (real double-fire risk, disclosed) | Y·Y·Y·Y | Architectural Debt | Fix Later | Wave 4 consolidation (mission not yet assigned) |
| Relationship Model | Populated — first 13 real evidence-backed edges | L3 | 88% | Knowledge domain | Active (sparse) | Low | Y·Y·~·Y | Architectural Debt | Leave As-Is — extend opportunistically | Extend seed set to remaining ~14 capabilities |
| Content Intelligence | Operational, `source_ref` propagation fixed | L2–L3 | 70% | Communications domain | Active | Low | Y·Y·Y·Y | Architectural Debt (2 disjoint pipelines) | Fix Later | Retire `content_signals`; converge the 2 drafting pipelines |
| Health Intelligence | Operational, first Event Bus emitter live | L3 | 70% | Health domain | Active | Low | Y·Y·Y·Y | Architectural Debt | Fix Later | Untangle write/analysis ownership |
| Holistic Wellness Coaching | Live, escalation logic consolidated, first Event Bus emitter live | L2 | 55% | TBD | Degraded (dispatcher has no live trigger) | Medium (wellness escalation path, no assigned owner) | Y·Y·~·~ | Operational Issue | Fix Now — establish the dispatcher's real scheduling trigger | Establish a real scheduling trigger for the dispatcher |
| Operational Resilience Intelligence | Recovered from 4 real MSN-0338 failures (MSN-0339); continuous Attention Engine evaluation now live; MSN-0341 acceptance pending | L3 | 85% | Intelligence domain | Active | Low | Y·Y·Y·Y | Healthy | Leave As-Is | Await MSN-0341's formal operational-acceptance decision |
| Engineering Runtime | Operational, one major gap (`batch_coding.py`) | L2–L3 | 55% | Engineering domain / Chief Engineer | Active | Medium | Y·Y·Y·Y | Architectural Debt | Fix Later | Adopt Task Engine once its own live-fire is reverified |
| Secure Execution Policy | Designed only, gates the (also unbuilt) Execution Engine Interface | L1 | 30% | Chief Engineer | Design-Only | N/A | Y(design)·N·N·N | Design-Stage | Leave As-Is | Build once Data Classification + a 2nd engine exist |
| Data Classification & Model Routing | Designed only, 6-tier classification + routing-policy layer | L1 | 35% | Chief Engineer | Design-Only | N/A | Y(design)·N·N·N | Design-Stage | Leave As-Is | Build classification declaration mechanism first |
| Execution Runtime Registry | Designed only, reconciles 2 prior designs + real initial content (Native SUOC, Hermes) | L1 | 40% | Chief Engineer | Design-Only | N/A | Y(design)·N·N·N | Design-Stage | Leave As-Is | Build once a 2nd engine is genuinely piloted |
| Attention Engine | Now running continuously in production (MSN-0339, 10-min interval); real `interrupt_now` still 0-for-0 | L2 | 65% | Chief Engineer | Active | **High** (silent-alarm risk, tied to the real Telstra near-miss, named by 23/23 independent reviewers) | Y·Y·Y·~ | Operational Issue | **Fix Now** — build the drill/certification mechanism MSN-0347 flagged, don't wait for an organic firing | Observe a real `interrupt_now` firing against real data |
| Priority & Opportunity Engine | Built, validated against real data, value/opportunity/time_sensitivity all still 0 | L2 | 40% | Chief Engineer | Degraded | **High** (feeds the Decisions Inbox's "ranked" presentation — trust hazard per 23/23 reviewers) | Y·Y·Y·N (weighting hardcoded, confirmed unchanged 2026-07-17) | Operational Issue | **Fix Now** — most-cited unfixed blocker across MSN-0346/0347 | Weighting function deferred to Learning & Adaptation; needs Relationship Model + Content Intelligence maturity |
| Continuous Captain Brief Orchestration | Two real consumers now: LCARS UI (MSN-0315) + OI's scheduled interrupt-check job (MSN-0339 WP3) | L2 | 60% | Chief Engineer | Active | Low | Y·Y·Y·Y | Architectural Debt (3 unreconciled pipelines) | Fix Later | Formal Captain Brief Convergence review (MSN-0342/0343) vs. `captains_brief.py`/`captain_brief_evolution.py` |
| Captain Intelligence Core | Phase 5: wired into LCARS Captain's Chair (real consumer), 2 more real bugs fixed pre-launch, operational observation period begins | L2 | 80% | Chief Engineer | Active (correctly gated) | Low | Y·Y·Y·~ (2 rows/1 day, unchanged, confirmed 2026-07-17) | Healthy | Leave As-Is — Operational Observation Period governs this, not engineering | Observe only — no tuning before 20 real insight_outcomes rows across 10+ distinct days |
| Captain Experience Component Library | DO/VDO review complete — CC repaint found incomplete (real legibility regression), 6 remediation items found. MSN-0335: 7 dead pages + 1 duplicate chat UI retired, blocked-state engines consolidated | L2 | 65% | Chief Engineer | Active | Low-Medium (WCAG contrast failures) | Y·Y·Y·Y | Architectural Debt | Fix Later | Action consolidated remediation list before confidence reconsidered |
| Runtime Render Validation Framework | Maturity programme complete — standard validation platform for future Captain-facing interfaces | L2 | 78% | Chief Engineer | Active | Low | Y·Y·Y·Y | Healthy | Leave As-Is | Consumed by future adoptions (e.g. `lcars-portal`) as needed; not under active development absent a new capability gap |
| Capture Promotion Bridge | Built + validated end-to-end against real data; also gave the dormant Notebook triage engine its first-ever real trigger | L2 | 70% | Chief Engineer | Active | Low | Y·Y·Y·~ | Architectural Debt (1 parallel path remains) | Leave As-Is — let volume accumulate before deciding | Volume/edge-case validation over time before Notebook capture form retirement |

---

## Planned Platform Capabilities

Visible for tracking purposes; not yet active capabilities, no engineering has formally begun.

(Attention Engine, formerly listed here as "Relevance & Attention Engine," was promoted to a full capability record in MSN-0301 — see Capability Records below.)
- **Policy Engine** — a generalisation of the scattered policy-gate mechanisms that aren't officer-authority (content-sensitivity gates in `outcome_capture.py`, capacity-based mission-deferral rules in `capacity_gate.py`) into one place. No design work started. (Secure Execution Policy, below, is a related but narrower concept — execution-time gating specifically, not general policy.)

---

## Capability Maturity Levels

- **L1 — Planned:** architecture approved only.
- **L2 — Implemented:** capability exists but has limited adoption.
- **L3 — Operational:** capability is stable and used by one or more services.
- **L4 — Platform Standard:** canonical implementation used across the platform.
- **L5 — Optimising:** capability continuously improves itself through measurement, learning and engineering evolution.

**Engineering Confidence** is a separate axis from maturity. Maturity answers "how far has this spread?" Confidence answers "how sure are we this is stable, complete, and architecturally sound?" A capability can be low-maturity but high-confidence (a well-evidenced design not yet built), or higher-maturity but lower-confidence (spread further than its current soundness really supports).

---

## Capability Records

Every record follows the same field order: Capability Name, Description, Purpose, Engineering Confidence, Current Maturity, Current Status, Owner, Canonical Implementation, Consumers, Dependencies, Capability Relationships, Related ADRs, Related Missions, Technical Debt, Next Planned Evolution, Last Updated.

### Governance

- **Description:** the ADR/directive/decision registry ecosystem, plus the officer-authority YAML manifests as governance artefacts.
- **Purpose:** provide one durable, findable record of platform decisions and policy.
- **Engineering Confidence:** 55% — the individual registries are well-authored; the ecosystem as a whole is demonstrably fragmented (4 parallel ADR stores, a real ID collision), so confidence in *the capability*, not any one document, is moderate.
- **Current Maturity:** L2 — Implemented, fragmented.
- **Current Status:** 4 parallel ADR registries exist (`governance/ADR-*.md` frozen and abandoned, `knowledge/Architectural-Decisions.md`, `core/governance/architecture-decision-records/` — the actual current canonical one — and `architecture/decisions/`), plus a D-prefix collision between `governance/directives/` and `governance/decisions/`.
- **Owner:** Chief Engineer, reviewed by Number One.
- **Canonical Implementation:** `core/governance/architecture-decision-records/` (per its own internal `ADR-NAMESPACE-MAPPING.md`); `governance/authority/*.yaml` (policy manifests).
- **Consumers:** `authority_validator.py` (reads manifests); every mission that cites an ADR.
- **Dependencies:** none technical — human-authored markdown/YAML.
- **Capability Relationships:**
  - *Depends On:* none.
  - *Consumes:* none.
  - *Produces:* policy manifests (consumed by Permissions).
  - *Future Dependencies:* Policy Engine (planned) will likely extend this registry's authority-manifest pattern.
- **Related ADRs:** ADR-020 (Capability Reuse Before Capability Creation), ADR-027 (Whole-of-System Principle).
- **Related Missions:** Phase 0 Stabilisation, MSN-0210 (SUOC), MSN-0210F.
- **Technical Debt:** 4 ADR registries not consolidated; D-prefix collision unresolved.
- **Next Planned Evolution:** ADR-registry consolidation onto `core/governance/architecture-decision-records/` with deprecation pointers left in the other 3 (recommended in MSN-0210, not yet run as its own mission).
- **Last Updated:** 2026-07-05.

### Permissions

- **Description:** officer/action authority checking — who is allowed to do what.
- **Purpose:** one canonical gate for policy-sensitive actions across the platform.
- **Engineering Confidence:** 85% — MSN-0326 (5-wave implementation, all Captain-accepted, 2026-07-06) resolved the canonical semantics question, closed all 3 manifest gaps, made both explicit-only fail semantics and approval-blocking enforcement the platform default, and retired the second rival mechanism. Not 100%: no real manifest yet exercises the approval-blocking path (disclosed, tested via isolated logic instead), and adoption remains 2 real (dormant) call sites — the mechanism is now correct and unified, but not yet exercised by live traffic anywhere.
- **Current Maturity:** L3 — Implemented, one canonical mechanism, enforced by default, limited live adoption.
- **Current Status:** one canonical, manifest-driven authority mechanism. What were 2 independent, disagreeing mechanisms (this one fail-open, `officer_actions.py`'s `AUTHORITY_MAP` fail-safe, different action grains, never cross-checked) are now one data source, one loader, two legitimate query granularities. Both real call sites confirmed dormant throughout (Wave 1), so this is a correctness/architecture win, not yet a live-traffic-proven one.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/governance/authority_validator.py` (`can_officer`, `requires_approval`, `audit_authority_action`, `ManifestGapError`, `load_manifest`), `core/governance/authority_enforcement.py` (`enforce_authority`, `AuthorityContext`, `require_approval_blocking` now enforced by default), `slack-bot/lib/officers/officer_actions.py` (`get_officer_authority` now reads `mission_creation_authority` from the manifest via `load_manifest()`, `AUTHORITY_MAP` retired).
- **Consumers:** `core/coordination/execution_engine.py`, `slack-bot/command_memory_integration.py`, `slack-bot/lib/officers/officer_actions.py`.
- **Dependencies:** `governance/authority/*.yaml` manifests (all 13 officer domains now present), Supabase (`authority_audit_log`).
- **Capability Relationships:**
  - *Depends On:* Governance (manifests).
  - *Consumes:* Governance's policy manifests.
  - *Produces:* authority decisions (consumed by Execution Engine Interface, Audit).
  - *Future Dependencies:* Policy Engine (planned, may generalise this pattern beyond officer/action).
- **Related ADRs:** ADR-027.
- **Related Missions:** MSN-0210F (Phase 1 de-dup, Phase 2 opt-in enforcement), MSN-0210G (readiness review), MSN-0210L (found the 2nd rival mechanism), MSN-0325 (resolved canonical semantics decision, Option 3), **MSN-0326 (5-wave implementation programme, completed 2026-07-06 — call-site audit, manifest gaps filled, explicit-only fail semantics, approval-blocking enforcement, 2nd mechanism retired)**, MSN-0327 (reconciled a parallel-session governance-record discrepancy mid-programme, see Engineering Governance §).
- **Technical Debt (remaining, disclosed by MSN-0326 itself, not silently carried):** no real manifest yet pairs a self-authorized action with an approval requirement, so the approval-blocking mechanism (Wave 4) has never been exercised against live policy, only isolated logic tests — deliberately not manufactured (Wave 5's own architectural choice); `officer_actions.py`'s `_DEFAULT_AUTHORITY` (`NUMBER_ONE`) fallback preserved as an implicit default, not converged to explicit-only semantics (out of MSN-0326's authorized scope); both real call sites (`execution_engine.py`, `command_memory_integration.py`) have their own broad exception handlers that would silently swallow `ManifestGapError`/a blocking `AuthorityError` if either path is ever revived, without their own separate fix; not integrated into Telegram bots, Command Centre backend, or LCARS Portal beyond narrow fixes.
- **Next Planned Evolution:** none currently chartered. If a future manifest organically creates the first real allowed+requires-approval overlap, or either dormant call site is revived, re-verify Wave 3/4's mechanisms and the caller-side exception handling against that real case at that time (MSN-0326 Wave 5 §8 recommendation).
- **Last Updated:** 2026-07-06.

### Audit

- **Description:** structured "who did what, when, with what outcome" trail.
- **Purpose:** durable accountability record, replacing ad hoc logging into unrelated tables.
- **Engineering Confidence:** 85% — both tables are live-verified end-to-end with real writes, clean schema separation by design, non-blocking failure handling proven correct.
- **Current Maturity:** L3 — Operational.
- **Current Status:** two tables by design — `authority_audit_log` (permission-specific, wired but 0 rows as of last check) and `audit_events` (general-purpose, 2 real callers, live-verified).
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/platform/audit_service.py` (`record_audit_event`, general); `core/governance/authority_validator.py`'s `audit_authority_action` (permission-specific).
- **Consumers:** `slack-bot/lib/comms/pipeline.py` (Captain approval transitions), `core/coordination/telegram_build_executor.py` (build execution outcomes), `authority_validator.py` itself.
- **Dependencies:** Supabase (`audit_events` migration 0054, `authority_audit_log` migration 0053).
- **Capability Relationships:**
  - *Depends On:* none technical.
  - *Consumes:* events from Permissions, Content Intelligence approvals, Engineering Runtime outcomes.
  - *Produces:* durable audit records.
  - *Future Dependencies:* Notification (to persist its call log), Event Bus (potential future unification of audit-as-events).
- **Related ADRs:** ADR-027.
- **Related Missions:** MSN-0210E (table + redirect), MSN-0210F Phase 2 (wired into 2 approval flows).
- **Technical Debt:** notification activity not yet audited; the two tables are intentionally not consolidated but this should be revisited if a third audit-worthy category emerges.
- **Next Planned Evolution:** wire `notification_service.py`'s in-process call log into `audit_events`.
- **Last Updated:** 2026-07-05.

### Notification

- **Description:** send a message through a transport (Telegram, transitionally Slack) with real severity, retry, templates, and a call log.
- **Purpose:** one shared sending mechanism instead of 5+ independent ad hoc senders.
- **Engineering Confidence:** 80% — fully operationally validated (retry, real delivery, logging all confirmed working), the gap is adoption, not soundness.
- **Current Maturity:** L2 — Implemented, zero production adoption (standalone by design this wave).
- **Current Status:** fully built and operationally validated (retry behaviour, real delivery, logging all confirmed working end-to-end) but not called from any live path yet.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/platform/notification_service.py` (`notify()`).
- **Consumers:** none yet — `command_bus.py`'s own `_telegram`/`_slack` remain the live senders pending an explicit cutover decision.
- **Dependencies:** Telegram Bot API, Slack `chat.postMessage` (transitional), env vars (`TELEGRAM_BOT_TOKEN`, `SLACK_BOT_TOKEN`, etc.).
- **Capability Relationships:**
  - *Depends On:* Configuration (env vars — not yet via the actual service).
  - *Consumes:* nothing yet (standalone).
  - *Produces:* delivery results, an in-process call log.
  - *Future Dependencies:* Audit (to persist its log), Event Bus (future trigger source for notifications).
- **Related ADRs:** ADR-027.
- **Related Missions:** MSN-0210F Phase 1 (built), MSN-0210G (full operational validation incl. a real delivery test), MSN-0210H (Hermes discovery's unified-gateway pattern validates this design direction).
- **Technical Debt:** in-process call log not persisted to Audit; Slack transport is transitional pending Slack's platform-wide retirement; `command_bus.py` cutover explicitly held pending further readiness review.
- **Next Planned Evolution:** `command_bus.py` cutover — held per Captain instruction, no date set.
- **Last Updated:** 2026-07-05.

### Configuration

- **Description:** shared loader for genuinely cross-service environment variables.
- **Purpose:** stop the 9-copy config.py sprawl from growing further.
- **Engineering Confidence:** 70% — unit-verified correctness (alias normalisation, graceful `.env` layering), but zero real-world proof since nothing has adopted it yet.
- **Current Maturity:** L2 — Implemented, zero adopters.
- **Current Status:** built and unit-verified (alias normalisation, graceful `.env` layering) but no existing service has been migrated to use it — flagged as an at-risk capability.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/platform/configuration_service.py` (`get_shared_config`, `load_dotenv_files`, `validate_shared_config`).
- **Consumers:** none.
- **Dependencies:** `.env` files, `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` (incl. the `SUPABASE_KEY` alias)/`GEMINI_API_KEY`.
- **Capability Relationships:**
  - *Depends On:* none.
  - *Consumes:* `.env` files.
  - *Produces:* normalised shared configuration values.
  - *Future Dependencies:* none — this is foundational; other capabilities should depend on it, not the reverse.
- **Related ADRs:** ADR-027.
- **Related Missions:** MSN-0210F Phase 1 (built), MSN-0210G (flagged as an ADR-027 risk — built but not connected).
- **Technical Debt:** zero real adopters; risk of becoming dead code if this persists.
- **Next Planned Evolution:** migrate at least one real service's config loading onto this (candidate: `intelligence/config.py` or `telegram-bot/config.py`) to prove adoption before it's forgotten.
- **Last Updated:** 2026-07-05.

### Model Router

- **Description:** local-first LLM inference gateway with cloud fallback.
- **Purpose:** one place every domain calls for model inference instead of embedding its own routing logic.
- **Engineering Confidence:** 99% — long-running, widely-adopted, no significant issues found across every audit this cycle.
- **Current Maturity:** L4 — Platform Standard.
- **Current Status:** stable, canonical, already the reference pattern every other Platform Service in this registry is measured against.
- **Owner:** Chief Engineer / Engineering domain.
- **Canonical Implementation:** `core/model-router/app.py` (port 8891).
- **Consumers:** `telegram-bots/xo/`, `telegram-bots/engineer.DEPRECATED-2026-07-05/` (retired), `core/engineering/engineering_router.py`, Research Orchestrator, `core/infrastructure/vm-processing/`.
- **Dependencies:** Ollama (local models: gemma3:4b, mistral-small3.2:24b, nomic-embed-text, qwen2.5-coder:7b), cloud fallback (GLM-5.2/Kimi/Qwen via Ollama Cloud, Mistral, Gemini).
- **Capability Relationships:**
  - *Depends On:* none.
  - *Consumes:* nothing else in-platform (calls external Ollama/cloud providers).
  - *Produces:* inference results, consumed by Knowledge, Search, Engineering Runtime, Content Intelligence, Operational Resilience Intelligence.
  - *Future Dependencies:* none.
- **Related ADRs:** ADR-020 (embodies "reuse before create").
- **Related Missions:** referenced as the reuse anchor throughout Phase 0, MSN-0210, MSN-0210C, MSN-0210F, MSN-0210G.
- **Technical Debt:** none significant. `MODEL_CODE`'s default was corrected from an uninstalled model (`qwen3-coder:30b`) to the installed one (`qwen2.5-coder:7b`) in MSN-0210F Phase 1.
- **Next Planned Evolution:** none currently planned.
- **Last Updated:** 2026-07-05.

### Knowledge

- **Description:** the knowledge-graph hierarchy (`knowledge_nodes`/`edges`) and the RAG document store (`knowledge_documents`/`document_chunks`).
- **Purpose:** durable, navigable organisational knowledge, separate from working/recall memory.
- **Engineering Confidence:** 84% (was 72%) — **MSN-0333 shipped real enforcement** for the sensitivity gap MSN-0332 found: `match_document_chunks`/`keyword_search_documents` (the real authoritative point — every search consumer routes through these, confirmed including `specialist_aware_retrieval.py` transitively) now exclude sensitive/restricted at the SQL level; `officer_clearances` gives this platform its first real `auth.uid()`-keyed identity anchor (none existed anywhere before); RLS updated as session-path defense-in-depth; shared accessor modules fixed the remaining direct-query consumers. Every fix verified against real production data in both directions, not assumed from code review. Higher than the pre-finding 78% because the fix is a genuine improvement (real future-proofing that didn't exist before), not just a restoration. Held below 90%: graph population still manual, not event-driven; temporal-knowledge question still disconnected.
- **Current Maturity:** L3 — Operational, sensitivity now genuinely enforced, not just classified.
- **Current Status:** actively used, well-designed schema, but graph population is manual (not event-driven) and disconnected from the ghost temporal-knowledge tables. The `processing_documents` → `knowledge_documents` review/approval bridge is real and live, emits `knowledge.document_review_decided` (MSN-0330), supports batch decisions (MSN-0331), preserves fuller provenance (MSN-0332), enforces sensitivity classification at retrieval (MSN-0333), and now supports sustained review sessions — keyboard shortcuts, a real "reviewed today" counter, URL-persisted filters/page/selected document (MSN-0334, UX only — no review-decision or governance logic touched).
- **Owner:** Knowledge domain.
- **Canonical Implementation:** `core/knowledge_navigation/` (graph sync/navigator), `tools/supabase/ingest_knowledge.py` + `retrieve_knowledge.py` (RAG, sensitivity-filtered at the RPC level per migration 0063). Review/approval: `lcars-portal/src/lib/knowledgeLibraryDecide.ts` (MSN-0331), `lcars-portal/src/app/api/knowledge-library/documents/{[id]/decide,batch-decide}/route.ts`. Governance: `officer_clearances`/`current_officer_clearance()` (migration 0063), `tools/supabase/knowledge_sensitivity.py` + `lcars-portal/src/lib/knowledgeSensitivity.ts` (shared accessor modules).
- **Consumers:** navigation commands (`map`/`navigate`), Search, Relationship Model, `lcars-portal/src/app/(app)/knowledge-library/page.tsx` (the Captain's review/approval surface). **Correction, MSN-0333:** `core/intelligence/knowledge_utilisation.py` was previously listed here in error — it scans `knowledge/*.md` files on disk, a naming coincidence with the `knowledge_documents` table; it never actually touches Command Memory. Removed, not carried forward.
- **Dependencies:** Supabase (`knowledge_nodes`, `knowledge_edges`, `knowledge_documents`, `document_chunks`, `processing_documents`), Model Router (embeddings).
- **Capability Relationships:**
  - *Depends On:* Model Router.
  - *Consumes:* markdown source files, approved documents.
  - *Produces:* `knowledge_nodes`/`edges`, RAG chunks.
  - *Future Dependencies:* Event Bus (event-triggered sync), Unified Memory (Archival tier).
- **Related ADRs:** ADR-022 (Hierarchical Knowledge Navigation Layer).
- **Related Missions:** MSN-0210C (knowledge foundation review), MSN-0210 (chose `knowledge_nodes` as the Object Registry anchor), MSN-0205D (built the review/approval bridge), MSN-0330 (found real 850-document backlog, added `knowledge.document_review_decided` emitter), MSN-0331 (batch triage + pagination), MSN-0332 (Captain Memory Activation: flow map, provenance fix, found the sensitivity gap and search-readiness gap), **MSN-0333 (Captain Memory Security & Information Governance: shipped RPC-level sensitivity enforcement + `officer_clearances` identity anchor + shared accessor modules, verified against real data; also fixed an active near-miss third-party leak in `tools/notion/sync_knowledge_assets.py`, and corrected a false-positive consumer claim about `knowledge_utilisation.py`).**
- **Technical Debt:** graph sync is manual, not event-triggered; ghost `temporal_entities`/`facts`/`episodes` tables remain unresolved, with anon-executable `temporal_search_facts`/`temporal_search_episodes` RPCs flagged as an open security item across three prior missions — MSN-0210D still not scheduled. A fully-built, entirely dormant second research-orchestration codebase (`slack-bot/lib/research/`) has zero live callers. **MSN-0333, disclosed not fixed:** `lcars-portal/.../memory/[id]/route.ts`'s PATCH has no authorization check at all (any authenticated caller can reclassify/archive any document) — a real gap, out of this mission's retrieval-focused scope. `tools/supabase/retrieve_knowledge.py` still has zero live callers anywhere in the platform — sensitivity enforcement is now safe, but search itself still isn't reachable by the Captain through any real UI, only a manual CLI. Whether the Captain works through the 814-document review backlog is a usage question, not a code constraint.
- **Next Planned Evolution:** search readiness (wiring `retrieve_knowledge.py` into a real UI/chat surface) is now safely buildable, sensitivity enforcement no longer blocks it; a small officer-management UI once a second real officer is onboarded; event-triggered `knowledge_navigation` sync; decide the fate of the dormant `slack-bot/lib/research/` stack.
- **Last Updated:** 2026-07-07.

### Search

- **Description:** query interface over documents/memory/missions.
- **Purpose:** one shared search capability instead of 6 incompatible implementations.
- **Engineering Confidence:** 63% — each implementation individually works, but "Search" as a unified capability doesn't yet exist, and two incompatible embedding stacks would need reconciling.
- **Current Maturity:** L2 — Implemented (per-implementation), fragmented as a capability.
- **Current Status:** 6 real, working implementations exist independently — no consolidation has started.
- **Owner:** TBD.
- **Canonical Implementation (candidate, not yet consolidated):** `tools/supabase/retrieve_knowledge.py` (hybrid keyword+vector, the most complete of the 6).
- **Consumers:** varies per implementation (`research_memory_retrieval.py`, `semantic_retrieval.py`, `notebook_search.py`/`notebook_relationships.py`, `mission_registry.py`).
- **Dependencies:** Supabase pgvector, two distinct embedding-provider stacks (Mistral-primary vs. a separate stack in `semantic_retrieval.py`), Knowledge, Model Router.
- **Capability Relationships:**
  - *Depends On:* Knowledge, Model Router.
  - *Consumes:* `knowledge_documents`/`document_chunks`, `research_memory`.
  - *Produces:* search results.
  - *Future Dependencies:* none major beyond its own consolidation.
- **Related Missions:** MSN-0210 (discovery), `reports/SUOC-CONVERGENCE-PLAN-2026-07-05.md` Wave 4 action 15.
- **Technical Debt:** 6 incompatible implementations; two embedding-provider stacks would need reconciling before consolidation.
- **Next Planned Evolution:** Wave 4 consolidation. **Note:** an earlier draft (`SUOC-CONVERGENCE-PLAN-2026-07-05.md`) referenced a placeholder mission number for this that has since been reassigned to an unrelated mission (MSN-0210G is now the Platform Readiness Gate) — no real mission number is currently assigned to Search consolidation.
- **Last Updated:** 2026-07-05.

### Confidence

- **Description:** scoring the effectiveness/quality of a decision-outcome pair, feeding provider-quality trends and feedback signals.
- **Purpose:** one shared confidence/quality-scoring mechanism instead of a dormant, never-fired duplicate per domain.
- **Engineering Confidence:** 78% — proven end-to-end with a real test write reaching all 6 tables in the chain (`commander_decisions`→`decision_outcomes`→`decision_records`→`quality_scores`→`feedback_signals`→`provider_quality_history`), but adoption is currently narrow (2 domains) and the schema relationships took real debugging to get right, meaning similar future integrations need the same care, not a copy-paste.
- **Current Maturity:** L3 — Operational, narrow scope.
- **Current Status:** activated in MSN-0210E after discovering the "proven" reference pattern (`build_learning_loop.py`) was itself silently broken against the live schema (wrong FK target, wrong column names, wrong client type). Fixed and now wired into Research and Content domains.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `slack-bot/lib/quality_scoring_service.py`, `feedback_loops_service.py`, with the corrected wiring pattern in `slack-bot/lib/research_learning_loop.py`, `slack-bot/lib/comms/comms_learning_loop.py`, and the patched `slack-bot/lib/build_learning_loop.py`.
- **Consumers:** `research_command.py` (mission completion), `comms/pipeline.py` (Captain approval transitions), `telegram_build_executor.py` (build outcomes, via the original pattern).
- **Dependencies:** Supabase (`commander_decisions`, `decision_outcomes`, `decision_records`, `quality_scores`, `feedback_signals`, `provider_quality_history`).
- **Capability Relationships:**
  - *Depends On:* none technical (self-contained Supabase chain).
  - *Consumes:* decision/outcome events from Research, Content Intelligence, Engineering Runtime.
  - *Produces:* effectiveness scores, feedback signals, provider-quality trend data.
  - *Future Dependencies:* Event Bus (future unification of "decision made"/"outcome scored" as canonical events); Attention Engine (planned — may consume confidence scores as an input); Priority & Opportunity Engine (planned — risk dimension is computed from this capability's scores).
- **Related ADRs:** ADR-027 (the schema-mismatch discovery is a direct example of the failure pattern this ADR addresses).
- **Related Missions:** MSN-0210C §13 (design), MSN-0210E (activation), MSN-0210 §4/§16 (the `decisions` table overload this relieves), MSN-0301 (Learning & Adaptation design applies this capability to Captain-decision feedback specifically), MSN-0302 (Engineering-domain discovery found the FK fix's live-fire is unconfirmed, plus two new bugs — see Technical Debt), MSN-0305 (fixed the adaptive-routing bug, resolved the Confidence Naming Decision).
- **Technical Debt:** only wired into 2 of the platform's decision-making domains; `outcome_capture_service.py`/`learning_loop_service.py` (the original, still-unused `LearningLoopBridge` path) likely carry the same schema-mismatch bugs and remain unfixed, out of scope for this activation. **New, MSN-0302, fixed MSN-0305:** (1) the MSN-0210E FK fix is proven only by one synthetic test write (created then deleted same day) — no real, non-test `/build` event had flowed through the corrected chain as of this finding, still outstanding; (2) ~~`build_learning_loop.py`'s adaptive-routing consumer never published to module scope~~ **FIXED, MSN-0305** — `slack-bot/app.py::_init_learning_loop()` now explicitly sets `research_delegator.adaptive_routing_service` on that module's own namespace (`globals()` in `research_delegator.py` reads its own module globals, not `app.py`'s — the root cause), live-verified; (3) engineering-domain quality rows are permanently unattributed to any provider/model (`build_learning_loop.py` always calls `score_outcome(provider_name=None, model_name=None, provider_route="/build")`) — still outstanding; (4) a second, independent, dead capability-registration mechanism (`slack-bot/lib/delivery/data.py::register_capability()`) exists unflagged — still outstanding.
- **Confidence Naming Decision (MSN-0305, resolves the collision MSN-0302 flagged):** "confidence" means at least 3 genuinely distinct things on this platform, and only one of them should ever populate `core_events.confidence` or this capability's own tables. (1) **This capability's own concept** — epistemic trust in a specific decision/outcome/event, 0-100, the `quality_scores` chain. Canonical; keep using the bare word "confidence" for this and only this. (2) **Health/Wellness's `recovery_confidence`** — a pulse-completion/check-in-completion percentage, not a trust judgment at all; a misnomer inherited from its own table/view naming, not touched at the schema level this pass (out of scope), but **must never be mapped onto `core_events.confidence`** going forward — MSN-0305's own Wellness Coaching emitter (`engagement_dispatcher.py::_emit_and_return`) deliberately carries it under `linked_entities` as `recovery_pulse_completion:<value>` instead, as the first real enforcement of this decision. (3) **The Platform Registry's own Engineering Confidence field** (this record's own 78% above) — a meta-level "how sound is this capability" score, never appears in `core_events`, no collision risk. ORI's per-event classifier-computed confidence (`intelligence/classification/classifier.py`) is the one domain-level score that correctly matches sense (1) and should keep mapping directly.
- **Next Planned Evolution:** extend wiring to remaining decision domains (Health Intelligence, Operational Resilience Intelligence) as those domains' ownership questions resolve; confirm a real (non-test) event has flowed through the fixed chain; fix the provider/model attribution gap; decide the fate of the dead `register_capability()` mechanism; apply the Confidence Naming Decision to any future domain emitter (never map a domain-local "confidence"-named field onto `core_events.confidence` without checking it actually means epistemic trust first).
- **Last Updated:** 2026-07-05.

### Task Engine

- **Description:** shared durable-execution primitive — checkpointed, resumable background work.
- **Purpose:** replace 3 incompatible bespoke retry/resume implementations with one.
- **Engineering Confidence:** 82% — now has a real production adopter, live-verified in vm-processing's own venv (which lacks supabase-py — this surfaced and fixed a real portability bug: `transition_task`/`get_task*` depended on `raw_client`, silently no-opping wherever supabase-py isn't installed; all now use pure-REST `client.get()`/`client._patch()`).
- **Current Maturity:** L2 — Implemented, first real production adopter (dual-write, not yet sole source of truth).
- **Current Status:** `core/infrastructure/vm-processing/worker.py` now dual-writes into the Task Engine: `create_task()` in `scan()` (idempotency_key=`source_path`), `transition_task()` wired once at the single chokepoint `_patch_and_return()`, mapping vm-processing's 13 statuses onto the Task Engine's 6. Live-verified end-to-end using vm-processing's actual venv/config loader (not a convenient stand-in). `processing_documents` remains vm-processing's sole source of truth — this is a thin mirror, not a replacement.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/infrastructure/supabase/migrations/0056_task_engine.sql`, `core/platform/task_engine.py` (`create_task`, `transition_task`, `complete_task`, `get_task`, `get_task_by_idempotency_key`, `get_child_tasks`, `get_task_history`).
- **Consumers:** `core/infrastructure/vm-processing/worker.py` (dual-write, MSN-0210K).
- **Dependencies:** none.
- **Capability Relationships:**
  - *Depends On:* none.
  - *Consumes:* nothing yet.
  - *Produces:* task lifecycle records, consumed (candidate) by Unified Memory's Platform State route, Event Bus (future `task.*` emissions), Relationship Model (`task`/`event` node types added Wave 3).
  - *Future Dependencies:* Engineering Runtime (Wave 5 adoption for `batch_coding.py`), Execution Engine Interface (this mission's Workstream F design targets `task_id` as its integration point).
- **Related Missions:** MSN-0210C §8 (design), MSN-0210 §7 (canonical primitive), MSN-0210G (confirmed ready), MSN-0210H (decided to keep this in-house rather than adopt an external execution framework), MSN-0210J (built, Wave 3 Workstream A), MSN-0210K (first real adopter — vm-processing, Workstream A), MSN-0210L (designated the universal substrate for officer requests/delegation/handoff — design only, no new officer code migrated yet).
- **Technical Debt:** the 3 pre-existing `ResearchTask`/`WorkQueueItem` variants (`research_orchestration.py`, `slack-bot/lib/research/task_executor.py`, `core/coordination/number_one.py`) still not migrated — flagged as future consolidation candidates, not urgent. `event_bus.py`/`unified_memory.py`/`relationship_model.py` likely carry the same raw_client-dependency bug just fixed here — not yet audited/fixed for the other 3 modules.
- **Next Planned Evolution:** observe the dual-write in production over several real timer cycles before considering a second adopter; audit the other 3 Wave 3 modules for the same raw_client portability gap.
- **Last Updated:** 2026-07-05.

### Event Bus

- **Description:** canonical event emission/query (`core_events`).
- **Purpose:** one shared event vocabulary instead of five differently-shaped tables that don't talk to each other.
- **Engineering Confidence:** 85% (was 80%) — **MSN-0305 confirmed real production emission** of `intelligence.source.failed`. **MSN-0343 confirms the higher-volume `intelligence.signal.ranked` path is also live**: 401 real events observed 2026-07-08, closing the one gap this score was previously held back by.
- **Current Maturity:** L2 — Implemented, 12 real production emitters/emit-points (was 3 before MSN-0328).
- **Current Status:** `intelligence/persistence/intelligence_store.py` emits `intelligence.source.failed`/`intelligence.signal.ranked`/`intelligence.brief.generated`; `core/intelligence/readiness_history.py` emits `health.readiness.scored` (MSN-0305); `telegram-bots/recovery_officer/engagement_dispatcher.py` emits `wellness.escalation.dispatched` (MSN-0305). **MSN-0328 Wave 2 added 4 more**: mission lifecycle, delivery, strategy, comms. `core_events` also gained a `metrics` column (migration 0061), threaded end-to-end. **MSN-0328 Wave 3 added 3 snapshot-emit points**. **MSN-0329 Phase 4 added 2 more**: Knowledge, Research. **MSN-0330 Signal Expansion added 2 more**: `knowledge.document_review_decided` (LCARS Knowledge Library's approve/reject route — its own header comment already documented this as the sole write path into `knowledge_documents`; real production volume, 795 documents awaiting review as of 2026-07-07) and a new `platform-operations` domain (`platform.service_down`/`platform.service_recovered`, transition-only emission added to the already-live `command_bus.py` service monitor, proven duplicate-free via an isolated test before touching the live `command-bus.service` daemon; also closed a real gap where `model-router.service` — which Captain Intelligence's own Insight/Reasoning Engines depend on — wasn't being monitored at all). MSN-0330 also extended `lcars-portal/src/lib/core-events.ts`'s TS-side `publishEvent()` with `linkedDocuments`/`metrics` support, which it had claimed to mirror from Python's `publish_event()` but was actually missing. Calendar/Documents (Phase 4) and system-health-anomalies/readiness-band-change (MSN-0330) all investigated and found to have no clean, low-risk choke point — disclosed, not implemented. All emitters remain thin mirrors — each domain's own tables stay the source of truth.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/infrastructure/supabase/migrations/0055_core_events.sql`, `0060_core_events_lcars_write.sql` (RLS insert policy for the LCARS app's session client), `0061_core_events_metrics.sql`, `core/platform/event_bus.py` (`publish_event`, `poll_events`, `mark_event_status`). Poll-based, not push/message-broker — consistent with the rest of the platform (no message queue exists anywhere in the stack).
- **Consumers:** `intelligence/persistence/intelligence_store.py` (MSN-0210K), `core/intelligence/readiness_history.py` (MSN-0305), `telegram-bots/recovery_officer/engagement_dispatcher.py` (MSN-0305), `lcars-portal/src/lib/core-events.ts` + `slack-bot/commands/mission_lifecycle.py`, `core/coordination/telegram_build_executor.py`, `slack-bot/lib/notebook/notebook_route_executor.py`, `slack-bot/lib/comms/portfolio.py` (all MSN-0328 Wave 2).
- **Dependencies:** none.
- **Capability Relationships:**
  - *Depends On:* none.
  - *Consumes:* nothing yet.
  - *Produces:* the canonical event stream, consumed (candidate) by Unified Memory's Platform State route, Task Engine (future `task.*` events), Notification (potential future trigger source).
  - *Future Dependencies:* Unified Memory (Recall tier population), Attention Engine (MSN-0301 — polls this capability's stream as its primary input, now has 3 real domains to draw from).
- **Related Missions:** MSN-0210C §6/§21, MSN-0210 §9, MSN-0210G (confirmed ready), MSN-0210J (built, Wave 3 Workstream B), MSN-0210K (wiring built — Operational Resilience Intelligence, Workstream B), MSN-0301 (this capability's emission contract formalised as the "Domain Intelligence Framework"), MSN-0302 (found zero confirmed production events, Convergence Item 4), MSN-0304 (Convergence Review, confidence downgraded pending verification), MSN-0305 (Convergence Item 4 resolved positively — real production emission confirmed; 2 new emitters added — Wave 1), MSN-0328 Waves 2-3 (7 more real emitters + `metrics` extension + first render-side convergence), MSN-0329 Phase 4 (Knowledge, Research), **MSN-0330 (Signal Expansion — `knowledge.document_review_decided` + new `platform-operations` domain; 2 candidates investigated and disclosed as not-implementable this pass: system-health-anomalies (ghost `system_heartbeat` table, no real writer) and readiness-band-change (needs server-side scheduling to avoid client-side duplicate-emission risk)).**
- **Technical Debt:** the 6 pre-existing domain event tables (`commander_events`, `intelligence_events`, `audit_events`, `escalation_events`, `health_events`, `capability_events`) remain as-is by design — `core_events` is a thin index over them, not a replacement — 8 of ~9 real intelligence domains now emit (was 3 before MSN-0328). `poll_events`/`mark_event_status` share Task Engine's fixed raw_client-dependency bug — not yet audited/fixed here. The higher-volume `intelligence.signal.ranked` emission path wasn't observed completing in this session (process timeout) — only the failure path was confirmed live. 2 known secondary mission-status write paths (`command_memory_integration.py`, `improvement/validation.py`) not hooked, both on the confirmed-dormant Slack bot. None of the new emitters have been exercised against a live Supabase instance (no live DB access exists in this sandbox) — validated via synthetic events only throughout. **MSN-0328 Wave 3 finding:** not every consumer identified in Wave 2's discovery was actually duplicating briefing-assembly logic — Telegram's `/brief` and the scheduler's morning brief are legitimate direct reads of their own authoritative tables (`intelligence_briefs`, Context Assembly), not a competing recommendation engine the way Slack's `decision.py` was. Converging them onto the generic event-metrics path would either duplicate the same data in two places for no benefit, or lose real content (period ranges, event counts, blockers) the metrics field doesn't yet carry — left unconverted, disclosed, not forced.
- **Next Planned Evolution:** ~~observe a complete natural collection cycle to confirm `intelligence.signal.ranked` fires too~~ **CONFIRMED, MSN-0343 (2026-07-08)** — 401 real `intelligence.signal.ranked` events verified live in `core_events`. Audit/fix the same raw_client portability gap fixed in Task Engine remains open.
- **Last Updated:** 2026-07-08 (MSN-0343 — `intelligence.signal.ranked` confirmation was the last open item from this record's 2026-07-05 baseline).

### Unified Memory

- **Description:** one logical interface over Starship's existing memory stores, spanning 9 named memory types (Working, Command, Knowledge, Operational Patterns, Platform State, Officer Context, Decision History, Confidence History, Relationships).
- **Purpose:** map every existing memory-shaped table/file onto one shared `recall()` interface instead of each caller needing to know which of ~15 different stores holds a given kind of memory.
- **Engineering Confidence:** 65% — now has one real adopter on the Officer Context route, and that adoption surfaced and fixed a real gap (the route originally dropped 5 of `OfficerContext`'s 7 fields, including `has_context`, which the real caller actually depends on — now returns the full context). Other 8 routes remain as before: built, several individually proven, not all re-tested through this module.
- **Current Maturity:** L2 — Implemented, one real adopter (Officer Context route).
- **Current Status:** `slack-bot/lib/officers/daily_operations_cycle.py`'s `_step_research_scan` now calls `unified_memory.recall(MemoryType.OFFICER_CONTEXT, officer="research")` instead of `officer_context.retrieve_officer_context()` directly — the only real caller of that function anywhere in the repo. Output shape preserved (`has_context`/`relevant_memories` both present, now as dict keys instead of attributes). The ghost temporal-knowledge tables' scope question (MSN-0210D) remains open and unresolved; this interface still has no dedicated route for them.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/platform/unified_memory.py` (`MemoryType` enum, `recall()`). Routes: Working→`memory/*.md` files, Command→`decisions` table, Knowledge→`knowledge_documents`, Operational Patterns→`operational_patterns`, Platform State→Task Engine/Event Bus, Officer Context→`slack-bot`'s `officer_context.retrieve_officer_context()` (now returns the full 7-field context, fixed MSN-0210K), Decision History→`decision_records`, Confidence History→`quality_scores`, Relationships→`knowledge_edges`.
- **Consumers:** `slack-bot/lib/officers/daily_operations_cycle.py` (Officer Context route, MSN-0210K).
- **Dependencies:** Task Engine, Event Bus, Knowledge, Confidence, Relationship Model (each memory type's underlying store).
- **Capability Relationships:**
  - *Depends On:* Task Engine, Event Bus, Knowledge, Relationship Model.
  - *Consumes:* all 9 underlying stores listed above.
  - *Produces:* a single unified query surface.
  - *Future Dependencies:* MSN-0210D's resolution (would add/clarify a temporal-knowledge route).
- **Related Missions:** MSN-0210C §9/§10, MSN-0210, MSN-0210G, MSN-0210J (built, Wave 3 Workstream C), MSN-0210K (first real adopter — Officer Context route, Workstream C; fixed a field-loss gap the adoption surfaced), MSN-0210L (this module identified, on reflection, as the prior unadopted attempt at the canonical Context Assembly convergence problem — see the MSN-0210L architecture doc's Workstream F).
- **Technical Debt:** `temporal_entities`/`facts`/`episodes` tables still have zero owning code and remain outside this interface's scope; the other 8 routes remain individually not re-tested through this module this pass (Platform State was, via Task Engine/Event Bus's own live tests).
- **Next Planned Evolution:** MSN-0210D resolution, then a second real adopter migration for another memory type.
- **Last Updated:** 2026-07-05.

### Operational Pattern Library

- **Description:** a catalogue of reusable engineering patterns — both borrowed-from-external-research patterns and patterns extracted from Starship's own completed missions.
- **Purpose:** let Starship benefit from external agent-framework research without adopting any framework as the operating core, AND turn its own completed-mission experience into reusable platform knowledge rather than isolated mission history.
- **Engineering Confidence:** 78% — now has an explicit, documented (if manual) proposal process, and a 9th pattern proposed organically from this mission's own real work, not just batch-seeded once.
- **Current Maturity:** L2 — Implemented, 9 real patterns, still zero downstream consumers.
- **Current Status:** 9 patterns now (the original 8, plus "Dual-Write Production Adoption" proposed from MSN-0210K's own vm-processing/ORI migration experience). A deliberately-manual pattern-proposal process is now documented in `operational_pattern_library.py` (4-question criteria: is it repeatable, is it a process not a fact, can another engineer follow it without having lived the mission, does it genuinely differ from existing patterns) — explicitly NOT automated, since judging what's genuinely reusable needs human review at mission close-out. 3 patterns now linked into the Relationship Model graph (`pattern:dual-write-production-adoption` implemented by `capability:task-engine` and `capability:event-bus`).
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/infrastructure/supabase/migrations/0058_operational_pattern_library.sql`, `core/platform/operational_pattern_library.py` (`add_pattern`, `get_patterns`, `seed_initial_patterns`, `propose_dual_write_adoption_pattern`).
- **Consumers (candidate, not yet implemented):** XO bot (Ralph Loop-style post-tool-call reflection check for shell-control actions), Scheduling capability (cron safety rails), Notification capability (unified-gateway model, already validated by this pattern).
- **Dependencies:** none.
- **Capability Relationships:**
  - *Depends On:* none.
  - *Consumes:* mission history/findings (this session's own reports as the initial seed source, plus MSN-0210K's own dual-write adoption experience).
  - *Produces:* pattern guidance for other capabilities and future missions; now also produces graph-linkable pattern nodes via Relationship Model.
  - *Future Dependencies:* Scheduling (cron safety rails), Engineering Runtime (Hermes pilot vs. `batch_coding.py`), Execution Runtime Registry (planned).
- **Related ADRs:** none yet.
- **Related Missions:** MSN-0210H (external-research patterns), MSN-0210J (built, Wave 3 Workstream E — the 8 seed patterns), MSN-0210K (proposal process + 9th pattern + graph linkage, Workstream E).
- **Technical Debt:** zero downstream consumers yet; the candidate consumer integrations (XO bot reflection check, Scheduling safety rails, Notification gateway pattern) remain unimplemented; only 3 of 9 patterns are linked into the Relationship Model graph so far.
- **Next Planned Evolution:** first real consumer integration — candidate: the XO bot's Ralph Loop-style reflection check.
- **Last Updated:** 2026-07-05.

### Number One Execution Bridge

*(Renamed 2026-07-05 from "Execution Engine Interface" — a genuine name collision was found with Wave 3's new Execution Engine Interface capability below, which is a completely different concept (an external-execution-engine plugin protocol vs. this narrow internal mission-assignment bridge). Caught during Wave 3's registry update, per the platform's own "One Canonical Implementation per Capability" principle — two different things should never share one name.)*

- **Description:** the bridge between Number One's decisions and actual mission-assignment execution.
- **Purpose:** decisions and execution stay separated — Number One decides, this engine acts.
- **Engineering Confidence:** 90% — stable, recently behaviour-verified via an explicit 4-path test, clean single-domain scope.
- **Current Maturity:** L3 — Operational.
- **Current Status:** stable, single-domain use, recently de-duplicated to use the shared Permissions capability instead of reimplementing authority checks inline.
- **Owner:** Chief Engineer / Number One domain.
- **Canonical Implementation:** `core/coordination/execution_engine.py` (`NumberOneExecutionEngine`).
- **Consumers:** Number One's mission-approval flow (`on_mission_approved`).
- **Dependencies:** Permissions capability (`authority_enforcement.AuthorityContext`).
- **Capability Relationships:**
  - *Depends On:* Permissions.
  - *Consumes:* authority decisions.
  - *Produces:* mission-assignment actions.
  - *Future Dependencies:* Task Engine (future durable execution of its own actions).
- **Related ADRs:** ADR-0003.
- **Related Missions:** MSN-0210F Phase 1 (de-dup refactor, behaviour-preservation verified via 4-path test), MSN-0210J (renamed to resolve a naming collision).
- **Technical Debt:** none found.
- **Next Planned Evolution:** none currently planned beyond staying in sync with Permissions capability changes.
- **Last Updated:** 2026-07-05.

### Execution Engine Interface

- **Description:** the canonical protocol future execution engines (Hermes, LangGraph, OpenHands, or others) implement to plug into SUOC — `submit`/`poll_status`/`fetch_result`/`cancel`. This interface belongs to SUOC; execution engines are replaceable plugins behind it. Not to be confused with the Number One Execution Bridge above (a different, narrower, already-built capability).
- **Purpose:** let any future execution engine plug into the Task Engine/Event Bus/Audit/Relationship Model without SUOC redesign, and without those primitives needing to know which engine (if any) is running a given task.
- **Engineering Confidence:** 40% — a clear, minimal, well-reasoned design citing this mission's own real primitives as integration points, but zero implementation and zero real engine to validate against yet (Hermes evaluation is explicitly a separate, parallel, independent workstream).
- **Current Maturity:** L1 — Planned. Design only, per explicit mission scope (no implementation authorised this pass).
- **Current Status:** a 4-method Python `Protocol` designed (not built): `submit(task_id) -> handle`, `poll_status(handle) -> status`, `fetch_result(handle) -> dict`, `cancel(handle) -> bool`. Deliberately minimal — a larger design (e.g. multi-engine load balancing) would be scope creep with no second engine yet even under evaluation.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** none — design only, documented in `reports/USS-TJR-MSN-0210J-Execution-Engine-Interface-Design.md`.
- **Consumers:** none yet.
- **Dependencies:** Task Engine (the protocol's `task_id` parameter IS a Task Engine task), Event Bus (engine activity becomes `task.delegated`/`task.completed` events), Audit (delegation decisions get recorded).
- **Capability Relationships:**
  - *Depends On:* Task Engine, Event Bus, Audit.
  - *Consumes:* tasks created via the Task Engine.
  - *Produces:* nothing yet (design only).
  - *Future Dependencies:* Execution Runtime Registry (planned — would catalogue instances of this protocol once real engines exist), Operational Pattern Library (Hermes pilot patterns feed the first real implementation).
- **Related Missions:** MSN-0210H (the parallel Hermes evaluation this design explicitly did not depend on or couple to), MSN-0210J (designed, Wave 3 Workstream F), MSN-0210I (the Hermes evaluation concluded — Option 2, experimental sandbox only; no real engine to implement this protocol against yet).
- **Technical Debt:** none (not built).
- **Next Planned Evolution:** MSN-0210I concluded that neither available Hermes backend meets both the speed and safety bar for real Chief Engineer work on this VM (CPU-only hardware rules out fast local inference at the required ≥64K context; cloud inference is hard-blocked for sensitive Starship content pending a Data Classification & Model Routing capability that doesn't exist yet). This protocol therefore has no real engine to implement against for now — revisit once either the hardware constraint or the data-classification gap closes, not on a fixed schedule.
- **Last Updated:** 2026-07-05.

### Scheduling

- **Description:** recurring/timed job execution, in-process (apscheduler) and infra-level (systemd timers).
- **Purpose:** one shared scheduling abstraction instead of 5 independent in-process schedulers.
- **Engineering Confidence:** 65% — each of the 5 instances works individually in production; confidence in "Scheduling" as a unified capability is lower than any one instance's own reliability.
- **Current Maturity:** L2 — Implemented (per-instance), fragmented as a capability.
- **Current Status:** systemd timers correctly handle infra-level scheduling; 5 separate in-process `apscheduler` instances exist with no coordination.
- **Owner:** TBD.
- **Canonical Implementation:** none consolidated yet.
- **Consumers:** `telegram-bots/xo/app.py`, `slack-bot/recovery_scheduler.py`, `slack-bot/human_systems_scheduler.py`, `slack-bot/proactive_scheduler.py`, `intelligence/scheduler.py`.
- **Dependencies:** `apscheduler` (third-party), systemd.
- **Capability Relationships:**
  - *Depends On:* none currently unified.
  - *Consumes:* nothing shared.
  - *Produces:* triggered jobs.
  - *Future Dependencies:* Operational Pattern Library (cron safety rails).
- **Related Missions:** MSN-0210 (discovery), `SUOC-CONVERGENCE-PLAN-2026-07-05.md` Wave 4 action 13, MSN-0210H (Hermes' cron safety-rail patterns flagged as input to this consolidation).
- **Technical Debt:** 5 independent instances, real risk of two schedulers double-firing the same logical job.
- **Next Planned Evolution:** Wave 4 consolidation into one shared wrapper around the same library; mission number not yet assigned.
- **Last Updated:** 2026-07-05.

### Relationship Model

- **Description:** typed relationships between knowledge entities AND platform-runtime entities (missions, capabilities, officers, tasks, events, confidence, outcomes, learnings, patterns).
- **Purpose:** avoid building a second "relationship engine" when one already exists correctly — generalise it instead.
- **Engineering Confidence:** 88% — the underlying schema (ADR-022) has years of correct operation; the Wave 3 extension now has real evidence-backed content in it, not just a live-verified-but-empty schema.
- **Current Maturity:** L3 — Operational, generalised in Wave 3, now populated with real content in MSN-0210K.
- **Current Status:** first real relationship seed set created: 6 capability/officer nodes (Task Engine, Event Bus, Unified Memory, Relationship Model, Operational Pattern Library, Chief Engineer) plus the previously-missing `ADR-027` node (existed only in the markdown ADR log, never synced into the graph until now), linked by 13 evidence-backed edges — `governed_by` (each Wave 3 capability → the ADR that actually motivated it), `owns` (Chief Engineer → each of the 5 capabilities, per the Registry's own Owner field), `implements` (the new Dual-Write Production Adoption pattern → Task Engine and Event Bus, the two capabilities that actually used it this mission). Every edge cites its real evidence in `knowledge_edges.evidence`, not asserted without backing.
- **Owner:** Knowledge domain / Chief Engineer (schema extension).
- **Canonical Implementation:** `knowledge_nodes`/`knowledge_edges` (unchanged tables, widened constraints via `core/infrastructure/supabase/migrations/0057_relationship_model_extension.sql`), thin API `core/platform/relationship_model.py` (`ensure_node`, `add_relationship`, `get_relationships_for`) — additional to, not a replacement for, `core/knowledge_navigation/`'s richer traversal layer.
- **Consumers:** same as Knowledge, plus Operational Pattern Library (MSN-0210K, real pattern→capability links).
- **Dependencies:** same as Knowledge.
- **Capability Relationships:**
  - *Depends On:* Knowledge (same schema).
  - *Consumes:* same as Knowledge, plus platform-runtime entities from Task Engine/Event Bus/Operational Pattern Library.
  - *Produces:* same as Knowledge, plus platform-runtime relationship edges (13 real ones as of this mission).
  - *Future Dependencies:* Execution Engine Interface (a `task --executed_by--> engine` edge is a natural small extension once a real engine exists to link).
- **Related ADRs:** ADR-022, ADR-027 (now also a graph node, not just a markdown entry).
- **Related Missions:** MSN-0210 §7 (original decision), MSN-0210G §10 (reconfirmed pre-Wave-3), MSN-0210J (generalised, Wave 3 Workstream D), MSN-0210K (first real content — 7 nodes, 13 edges, Workstream D).
- **Technical Debt:** only 6 of the platform's ~20 capabilities have graph nodes so far; the other 14 capabilities and their real Owner/ADR/pattern relationships remain unlinked.
- **Next Planned Evolution:** extend the seed set to the remaining capabilities as each is next touched by a mission, rather than a second big-bang population pass.
- **Last Updated:** 2026-07-05.

### Content Intelligence

- **Description:** turns signals/research into content opportunities and drafts, with a Captain-gated approval pipeline.
- **Purpose:** structured content pipeline instead of ad hoc drafting.
- **Engineering Confidence:** 70% — `source_ref` propagation is now fixed and live-verified (full round-trip test: select → research-topic hint). Held back from higher by the still-open dead branch and the two-disjoint-pipeline structure.
- **Current Maturity:** L2–L3 — Operational, `source_ref` propagation fixed.
- **Current Status:** the real pipeline (`opportunities.py` → `comms_content` → `draft_worker.py`) works and is Captain-gated, but consists of **two disjoint producer/LLM pairs sharing one table** (MSN-0302 finding): the interactive path (`opportunities.py`, Gemini direct, ephemeral — drafts are shown in Slack but never persisted with body text) and the autonomous path (`draft_worker.py`, Mistral chain, the only path that persists `body`) never see each other's opportunities. `content_signals` is not fully dead as previously characterized — it is actively written (`intelligence/content_intelligence_service.py`) and read by the LCARS portal display, but remains disconnected from the Captain-gated drafting pipeline (`signal_source_id` bridge column unused), still not retired this pass. **MSN-0305:** `draft_worker.py`'s `fetch_pending()` now selects `source_ref` (was silently dropped — never in the SELECT clause) and `_build_research_topic()` includes it as a "Source reference" hint, live-verified with a real `comms_content` test row round-tripping the value correctly.
- **Owner:** Communications domain.
- **Canonical Implementation:** `slack-bot/lib/comms/opportunities.py`, `slack-bot/lib/comms/pipeline.py`, `core/content/draft_worker.py`.
- **Consumers:** Slack bot commands (`comms.py`, `brief.py`).
- **Dependencies:** Research Orchestrator, Command Memory tables, Model Router (drafting), Audit (approval logging), Confidence (approval scoring).
- **Capability Relationships:**
  - *Depends On:* Audit, Model Router, Confidence.
  - *Consumes:* `research_memory`, Command Memory tables.
  - *Produces:* `comms_content` drafts.
  - *Future Dependencies:* Event Bus (replacing `content_signals` as the opportunity-detection mechanism).
- **Related Missions:** MSN-0210C §15 (recommended retiring `content_signals`, not yet executed), MSN-0305 (fixed `source_ref` propagation, live-verified — Wave 0).
- **Technical Debt:** `content_signals` dead-end producer still not retired; the two-disjoint-pipeline structure (Gemini-interactive vs. Mistral-autonomous) unresolved.
- **Next Planned Evolution:** retire `content_signals` (fold its scoring logic into future Event Bus emission instead); converge the two drafting pipelines.
- **2026-07-17 note (`registry_staleness_check.py` flagged `draft_worker.py`):** wired `draft_worker.py` into `domain_heartbeats` (`content_intelligence` domain, part of the same day's live-ops audit) and repointed its dead crontab venv path — monitoring/scheduling-config changes only, not a change to Content Intelligence's own architecture or behaviour. Confirmed not material.
- **Last Updated:** 2026-07-17.

### REVS Content Generation Agents

- **Description:** turns a single design brief into 7 publication formats (article, poster, social, worksheet, presentation, podcast, video) via a 7-agent pipeline. Built for the "Recognise" product (chronic-pain/neurodivergent-audience content).
- **Purpose:** replace manual per-format content production with one brief → all 7 formats, for a content line whose audience needs (chronic pain, neurodivergence) make consistency and speed across formats valuable.
- **Engineering Confidence:** 65% — all 7 agents built, tested (21 pytest tests including a real ffmpeg integration test), and verified end-to-end against a real brief with two independent specialist reviews (Chief Engineer on the build, XO gatekeeping the actual outputs). Held back from higher by: no human sensitivity/clinical review gate before generation for audience-sensitive content (see Technical Debt), and by being new/single-brief-proven rather than battle-tested across the full 56-concept catalog it's meant for.
- **Current Maturity:** L2 — Operational for a single brief/operator, not yet proven at batch scale or with a content-review process around it.
- **Current Status:** live. CLI (`python -m src.main`) and a Telegram entry point (XO bot's `/revs_generate`, with a Confirm/Cancel step since it spends real Gemini API money per cold run) both work. No GPU on this VM, so image generation (Gemini `gemini-3-pro-image-preview`) and speech (Gemini `gemini-2.5-flash-preview-tts`) replace MISSION_BRIEF.md's original local Stable Diffusion / Coqui TTS plan; brief parsing is a deterministic Markdown-structure parser, not an LLM call. First XO gatekeeper pass returned a HOLD with 6 concrete defects (hallucinated placeholder text baked into AI-generated images, a headline-truncation bug, missing slide content, un-rendered Markdown, non-narration-ready podcast scripts, a CommonMark list-rendering bug) — all fixed and re-verified against real regenerated output before this entry was written.
- **Owner:** none formally assigned yet — built this session, not yet handed to a domain owner.
- **Canonical Implementation:** `services/revs-content-agents/` (own venv, own `requirements.txt` — deliberately isolated, same pattern as `telegram-bots/xo/.venv`, since its deps collide with the platform's other Python environments).
- **Consumers:** XO Telegram bot (`telegram-bots/xo/app.py::cmd_revs_generate`), direct CLI use.
- **Dependencies:** Gemini API (external, paid) for image/speech/text generation; no platform-internal dependencies — deliberately did not use the Local Model Router (brief parsing needs no LLM call) or a fresh Ollama pull (this VM already runs one for the rest of the platform, and REVS doesn't need a second).
- **Capability Relationships:**
  - *Depends On:* none shared with the rest of the platform.
  - *Consumes:* a Markdown design brief file.
  - *Produces:* 7 versioned output files per concept under `services/revs-content-agents/outputs/{concept_id}/v{N}/`, with an `asset_manifest.json` and a `runs.jsonl` history log.
  - *Future Dependencies:* none identified yet.
- **Related Missions:** none minted — built and hardened across one extended session, not tracked under a mission number.
- **Technical Debt:** no human sensitivity/clinical review gate before generation for audience-sensitive content. 2026-08-12: the sample brief's "Therapist (with framing notes)" claim (framing notes that didn't exist) was fixed to disclose plainly that they're not written yet, instead of silently overclaiming — but real therapist-facing framing content and any structural review gate are both still not built, deferred pending a decision on who actually staffs that review (Captain's call, not an engineering one). Docker/systemd packaging not built (runs via venv + CLI/Telegram only); no video captions/accessibility pass (an unchecked item in MISSION_BRIEF.md's own acceptance checklist); not yet run against more than one brief.
- **Next Planned Evolution:** decide who staffs therapist-facing content review, then write real framing-note content and/or a structural pre-generation review gate for audience-sensitive briefs; prove the pipeline at batch scale (`--input-dir`/`--parallel` exist but are untested beyond a single concept).
- **Last Updated:** 2026-08-12.

### Health Intelligence

- **Description:** capacity/readiness scoring and health check-in logging.
- **Purpose:** track Captain capacity and correlate it with mission activity.
- **Engineering Confidence:** 70% — now has a real Event Bus emitter, live-verified against real score computation (not synthetic data), the first concrete step off "split ownership" and onto shared primitives.
- **Current Maturity:** L3 — Operational, split ownership, first Event Bus emitter live.
- **Current Status:** analysis (`core/health/`) and writes (`slack-bot/commands/health_*.py`) are owned by two different packages — a real untangling is still needed before full Task Engine adoption. **MSN-0305:** `core/intelligence/readiness_history.py::persist_readiness_snapshot()` now emits `health.readiness.scored` to `core_events` (thin, non-blocking, alongside its existing `captain_readiness_history` upsert) — confirmed live via the `number-one-exporter.service` write path (polls every 300s). A separate Wellness Coaching bot still duplicates this domain's data-access logic rather than reusing it.
- **Owner:** Health domain.
- **Canonical Implementation:** `core/health/` (`capacity_score.py`, `readiness_score.py`, `weekly_synthesis.py`), `slack-bot/commands/health_check.py`/`health_event.py`/`recovery_pulse.py`, `core/intelligence/readiness_history.py` (now the Event Bus emission point).
- **Consumers:** Captain's daily/weekly briefs; Event Bus (new).
- **Dependencies:** Supabase (`health_daily_logs`, `health_events`, `recovery_pulses`, `health_insights`, `captain_readiness_history`).
- **Capability Relationships:**
  - *Depends On:* none shared yet.
  - *Consumes:* health check-in data.
  - *Produces:* capacity/readiness scores, briefs, `core_events` rows (new).
  - *Future Dependencies:* Task Engine (once ownership untangled), Attention Engine (this domain is now one of its real input sources).
- **Related Missions:** MSN-0210 §6 (domain review), MSN-0305 (first Event Bus emitter, live-verified — Wave 1).
- **Technical Debt:** write/analysis ownership split across two packages; Wellness Coaching (`telegram-bots/wellness_officer/`) duplicates data-access logic instead of reusing it; two independent LLM synthesis paths exist for the "weekly narrative" job, neither routes through Model Router; the "Medical Officer" LLM persona has no `governance/authority/` manifest. No native confidence value exists in this domain (readiness/capacity are already 0-100 scores, not a trust judgment) — `core_events.confidence` intentionally left null for this domain's emissions, per the Confidence Naming Decision (see the Confidence capability's record).
- **Next Planned Evolution:** untangle ownership — a prerequisite for full Task Engine adoption; extend the emitter to capacity-score-only updates if `persist_readiness_snapshot` isn't the sole write path.
- **Last Updated:** 2026-07-05.

### Holistic Wellness Coaching

*(New capability record, MSN-0302 — this domain is live, LLM-driven, and has real technical debt, but had no Registry entry at all before this pass, a direct instance of ADR-027's own whole-of-system test failing: undiscoverable in the one document meant to make it discoverable.)*

- **Description:** the coaching/behavioral layer distinct from raw health-metric scoring (Health Intelligence, above) — framework-based briefs (7 named care frameworks: Pain Reprocessing Therapy, Polyvagal Theory, ACT, Energy Portfolio Management, Operational Resilience, Spoon Theory, Antifragility), engagement/escalation dispatch, pattern reading.
- **Purpose:** translate raw health telemetry into behavioral coaching guidance and proactive engagement, not just scores.
- **Engineering Confidence:** 55% — the 3-copy escalation-logic duplication (a real silent-drift risk — the Slack copy used naive local system time instead of Brisbane time) is now fixed, and a real Event Bus emitter is live-verified. Still held back by the in-process officer coupling, Health Intelligence data-access duplication, and the dispatcher's missing automatic trigger.
- **Current Maturity:** L2 — Implemented, live, escalation logic consolidated, first Event Bus emitter live.
- **Current Status:** two live bot implementations (`telegram-bots/wellness_officer/` for briefs, `telegram-bots/recovery_officer/` for engagement/escalation dispatch) plus a third, non-integrated proactive-coaching mechanism (`human_systems_scheduler.py`'s wellness-adjacent jobs). `xo/app.py` directly imports both officer modules in-process — confirmed the clearest instance of one officer's code calling another's directly, anywhere in the codebase, not fixed this pass. **MSN-0305:** the 3 independent escalation-level copies are now one canonical function (`wellness_officer/intelligence.py::escalation_level()`); `recovery_officer/engagement_dispatcher.py` and `slack-bot/recovery_scheduler.py` both delegate to it — this also fixed a real divergence (the Slack copy computed "afternoon" from naive local system time, not Brisbane time, so it could silently disagree with the other two depending on server timezone). `engagement_dispatcher.py::run_dispatch_check()` now emits `wellness.escalation.dispatched` to `core_events` at every decision point, live-verified. The dispatcher itself still has **no live automatic trigger** — unchanged this pass.
- **Owner:** TBD (no domain owner currently assigned in governance).
- **Canonical Implementation:** `telegram-bots/wellness_officer/{intelligence,brief}.py` (now also the canonical `escalation_level()`), `telegram-bots/recovery_officer/engagement_dispatcher.py` (now also the Event Bus emission point).
- **Consumers:** `telegram-bots/xo/app.py` (in-process import, not a shared-primitive call); Event Bus (new).
- **Dependencies:** Health Intelligence's tables, read directly rather than via Health's own analysis layer (`health_daily_logs`, `recovery_pulses`, `health_insights`, `activity_logs`, `weight_logs`).
- **Capability Relationships:**
  - *Depends On:* none shared (duplicates Health Intelligence's data access instead of depending on it as a capability).
  - *Consumes:* Health Intelligence's raw tables directly.
  - *Produces:* coaching briefs, escalation messages, `core_events` rows (new).
  - *Future Dependencies:* Attention Engine (this domain is now a real input source), Confidence (framework/brief effectiveness feedback, currently only logged via `human_systems/memory.py`'s generic feedback taxonomy, not the platform Confidence chain), Audit (officer actions currently only `log.info()`-level, no durable record).
- **Related Missions:** MSN-0210L (found the in-process coupling and the dormant `daily_operations_cycle.py` Medical Officer step's overlap with this domain), MSN-0301 (named as a needed Event Bus emitter, no code found at the time), MSN-0302 (full domain discovery — this record), MSN-0305 (fixed the 3-copy escalation duplication including a real timezone divergence, wired the Event Bus emitter — Wave 1).
- **Technical Debt:** real duplication of Health Intelligence's data-access layer instead of consuming its scores; direct in-process coupling from `xo/app.py`; no live automatic trigger for the built dispatcher; no officer authority manifest. `core_events.confidence` intentionally left null for this domain's emissions (its `recovery_confidence` is a pulse-completion percentage, not an epistemic-trust score) — carried instead under `linked_entities` as `recovery_pulse_completion:<value>`, per the Confidence Naming Decision (see the Confidence capability's record).
- **Next Planned Evolution:** establish a real scheduling trigger for the dispatcher; decide data-ownership boundary with Health Intelligence; resolve the in-process officer coupling.
- **Last Updated:** 2026-07-05.

### Operational Resilience Intelligence

- **Description:** external sector-risk monitoring (ORI) — ingestion, classification, ranking, Captain's Brief generation. **One pipeline, not two:** "ANZ/Banking" and "Consultancy" are the same code path, not separate implementations — confirmed independently by two MSN-0302 discovery agents and by MSN-0301, same day. The pipeline is hardcoded banking/CPS230-scoped end to end (keyword tables, org lists, LLM system prompt); no consulting-sector config, keyword table, or source registration exists anywhere. If a genuine second audience exists, it is a presentation/distribution scoping question (`linked_entities`), not a second ingestion/classification/ranking system.
- **Purpose:** structured, ranked external intelligence instead of raw feed noise.
- **Engineering Confidence:** 85% — **MSN-0338 found this was overstated**: 4 compounding real failures (broken Telstra/NBN scraper content-validity, `notify()` with zero callers so `INTERRUPT_NOW` never reached the Captain, a live `risk_rating` schema bug silently zeroing signal counts in every brief, Attention Engine evaluation was manual-trigger-only). **MSN-0339 fixed all 4** (WP1–WP5, 2026-07-08) and put continuous Attention Engine evaluation into real production for the first time (see Attention Engine, Continuous Captain Brief Orchestration below). **MSN-0343 additionally fixed** a confirmed live classifier bug (GKE security bulletins misclassifying as `technology_outage` instead of `cyber` — plural/singular keyword mismatch). Held at 85% rather than raised further: MSN-0341's formal operational-acceptance decision is still pending a 48h observation window; treat this score as provisional until that closes.
- **Current Maturity:** L3 — Operational, now with continuous (not manual-only) Attention Engine evaluation.
- **Current Status:** working ingestion→classification→ranking→brief pipeline. Event Bus emission (`intelligence.signal.ranked`) **confirmed live** — 401 real events observed 2026-07-08 (was "zero confirmed" as of MSN-0302/0304). 129 sources registered (88 active) as of MSN-0302's live read, not re-verified since.
- **Owner:** Intelligence domain.
- **Canonical Implementation:** `intelligence/` (ingestion adapters, classification, ranking, `scheduler.py`, `captains_brief.py`), plus `core/platform/interrupt_dispatcher.py` and `core/platform/attention_engine.py`'s `continuous_attention_evaluation` job (MSN-0339 WP2/WP3).
- **Consumers:** Captain's Brief (Telegram, LCARS); Content Intelligence also reads `intelligence_events` (shared ingestion substrate, independent purpose); `core/platform/notification_service.py` (Telegram push, MSN-0339 WP2, real callers now exist).
- **Dependencies:** Supabase (`intelligence_events`, `intelligence_briefs`, `captains_daily_briefs`, `ori_source_documents`, `intelligence_source_registry`/`health`), Model Router, Attention Engine, Event Bus.
- **Capability Relationships:**
  - *Depends On:* Model Router, Attention Engine (MSN-0339, new).
  - *Consumes:* external RSS/GitHub sources.
  - *Produces:* `intelligence_briefs`, `captains_daily_briefs`, ranked signals, `core_events` (`intelligence.signal.ranked`, confirmed live).
  - *Future Dependencies:* none outstanding from the Wave 3 pilot — emission is now confirmed live, not just code-complete.
- **Related Missions:** MSN-0210C (reviewed, confirmed working), MSN-0210 §21 (chosen as the Event Bus pilot domain), MSN-0210K (Event Bus wiring landed), MSN-0302 (independently re-verified pipeline is unified across both named "domains"), **MSN-0338 (found 4 real compounding failures)**, **MSN-0339 (recovery programme, all 5 WPs delivered+live)**, **MSN-0340 (interim acceptance review — CONDITIONAL, observation window too early to certify)**, **MSN-0341 (formal operational-acceptance decision — pending, ~2026-07-10)**, **MSN-0343 (classifier GKE misclassification fix; Registry currency correction — this record was 3 missions stale)**.
- **Technical Debt:** (1) Telstra itself has no public unauthenticated feed — structurally uncollectible, disclosed not fixed. (2) The shared 129-source registry is contaminated with 26 sources tagged "wellness" — unrelated ingestion content feeding a banking-tuned classifier, likely belonging to Wellness Coaching or Health Intelligence instead — not re-verified since MSN-0302. (3) Two independent, uncoordinated schedulers still exist (`intelligence/scheduler.py` vs `platform-runtime/proactive_scheduler.py`) — deferred across MSN-0339/340, unresolved. (4) `executive_relevance` is `NULL` on every recent `intelligence_events` row checked — a populated-schema-but-empty-data gap.
- **Next Planned Evolution:** await MSN-0341's operational-acceptance decision; decide ownership/placement of the 26 wellness-tagged sources; the dual-scheduler consolidation (item 3) is a strong next-mission candidate per MSN-0342's roadmap.
- **Last Updated:** 2026-07-08 (MSN-0343).

### Engineering Runtime

- **Description:** the engineering-handoff execution path — mission context assembly, prompt building, model dispatch, evidence writing, and Mistral-batch delivery.
- **Purpose:** turn an approved engineering handoff into a real code change/PR.
- **Engineering Confidence:** 55% — `engineering_router.py` on its own would rate highly (clean separation, well-tested this cycle), but `batch_coding.py`'s complete lack of durable state pulls the capability's overall confidence down significantly.
- **Current Maturity:** L2–L3 — `engineering_router.py` operational and well-separated; `batch_coding.py` has a significant known gap.
- **Current Status:** `engineering_router.py` cleanly delegates model calls to Model Router and owns its own orchestration; `batch_coding.py` has zero DB-backed state (tracks progress via markdown-header stamping only) — the single biggest lift identified anywhere in the SUOC convergence work.
- **Owner:** Engineering domain / Chief Engineer.
- **Canonical Implementation:** `core/engineering/engineering_router.py`, `core/engineering/batch_coding.py`.
- **Consumers:** the `/build` flow, `core/coordination/telegram_build_executor.py`.
- **Dependencies:** Model Router capability, `work_queue.json`, GitHub (draft PRs), Audit (build outcome logging), Confidence (build outcome scoring, via `build_learning_loop.py`).
- **Capability Relationships:**
  - *Depends On:* Model Router, Audit, Confidence.
  - *Consumes:* `work_queue.json`, approved handoffs.
  - *Produces:* draft PRs, patch artifacts, build outcome records.
  - *Future Dependencies:* Task Engine (Wave 5, once built), Operational Pattern Library (Hermes pilot), Execution Engine Interface (this mission's Workstream F design names `batch_coding.py` as the one recommended pilot integration point), Execution Runtime Registry (planned — will likely catalogue any pilot executor this produces).
- **Related Missions:** MSN-0210 §6 (domain review), `SUOC-CONVERGENCE-PLAN-2026-07-05.md` Wave 5 action 16, MSN-0210H (Hermes discovery's recommended pilot targeted `batch_coding.py` specifically), MSN-0210J (Execution Engine Interface design references this capability as its integration target), MSN-0210I (the recommended pilot ran — against a synthetic doc, not `batch_coding.py` directly; concluded Option 2, experimental sandbox only, not a real integration).
- **Technical Debt:** `batch_coding.py` has no DB-backed state at all; coupled to `work_queue.json`'s file format.
- **Next Planned Evolution:** MSN-0210I ran the sunset-gated Hermes pilot and concluded it is not yet viable as a real execution runtime for this or any Chief-Engineer-facing capability on this VM — CPU-only hardware makes local (safe) inference impractically slow at Hermes' required ≥64K context, and cloud (fast) inference is hard-blocked for sensitive content pending the new Data Classification & Model Routing capability. `batch_coding.py` itself is untouched by this finding; still adopt the Task Engine once built (Wave 5, per the existing sequencing) rather than a Hermes-based executor.
- **Last Updated:** 2026-07-05.

### Secure Execution Policy

- **Description:** the single policy authority determining whether/how work may execute — gates the Execution Engine Interface's `submit()` before any task reaches an execution engine.
- **Purpose:** convert MSN-0210I's real, unexpected data-boundary block into an expected, pre-declared platform decision rather than a per-request surprise.
- **Engineering Confidence:** 30% — the design is coherent and traces directly to a real observed incident, but nothing is built, and it depends on Data Classification & Model Routing (also L1) to function.
- **Current Maturity:** L1 — Planned.
- **Current Status:** designed as a single function (`evaluate_execution(task_id, classification, target_engine_id) -> ExecutionDecision`), not a new service/daemon. Explicitly delegates approval *decisions* to the existing Permissions capability rather than inventing a second authority mechanism — Secure Execution Policy decides *whether an approval gate applies*, Permissions decides *who* can grant it.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** none yet. Design: `reports/USS-TJR-MSN-0210M-Secure-Execution-Policy-Architecture.md` Workstream A.
- **Consumers:** none yet — designed to gate the (also unbuilt) Execution Engine Interface.
- **Dependencies:** Data Classification & Model Routing, Permissions, Task Engine, Audit.
- **Capability Relationships:**
  - *Depends On:* Data Classification & Model Routing, Permissions, Task Engine.
  - *Consumes:* task classification, engine registry entries, authority decisions.
  - *Produces:* execution allow/deny decisions, logged via Audit.
  - *Future Dependencies:* Execution Engine Interface (this gates it once both exist).
- **Related Missions:** MSN-0210I (the incident that motivated this), MSN-0210M (designed, Workstream A).
- **Technical Debt:** none yet (not built).
- **Next Planned Evolution:** build once Data Classification & Model Routing and a real second execution engine both exist to make this more than a single-engine rule.
- **Last Updated:** 2026-07-05.

### Data Classification & Model Routing

- **Description:** a 6-tier data-sensitivity classification (Public/Internal/Confidential/Security Sensitive/Captain Only/Secrets) plus a policy layer generalising Model Router's routing beyond pure performance to include classification, provider trust, and engineering confidence.
- **Purpose:** determine which execution engines/model providers may process which artefacts, decided by SUOC before a request reaches any engine — closing the exact gap MSN-0210I's pilot hit as an unexpected runtime block.
- **Engineering Confidence:** 35% — the classification tiers and routing inputs are well-reasoned and directly evidence-driven, but classification is manual/declared only (no automatic detection), and 2 of 8 routing inputs (cost, availability) are acknowledged gaps, not solved.
- **Current Maturity:** L1 — Planned.
- **Current Status:** designed, not built. Classification is declared at the task-creation call site, matching how MSN-0210I's pilot manually recognised sensitive content — automatic classification is a deliberately deferred future enhancement, not attempted without real classification data to validate a heuristic against.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** none yet. Design: `reports/USS-TJR-MSN-0210M-Secure-Execution-Policy-Architecture.md` Workstreams B/C.
- **Consumers:** none yet — designed to be consulted by Secure Execution Policy and by Model Router.
- **Dependencies:** Model Router (routing sits above it, doesn't replace it), Execution Runtime Registry.
- **Capability Relationships:**
  - *Depends On:* Execution Runtime Registry (`allowed_classifications` field).
  - *Consumes:* task `input_context`'s declared classification.
  - *Produces:* routing/refusal decisions.
  - *Future Dependencies:* Secure Execution Policy (consumes this capability's output).
- **Related ADRs:** none yet.
- **Related Missions:** MSN-0210I (the finding that motivated this — originally logged as a one-line Planned Pipeline entry, now a full record), MSN-0210M (designed, Workstreams B/C).
- **Technical Debt:** cost and availability routing inputs identified as real gaps, not addressed; automatic classification not attempted.
- **Next Planned Evolution:** build the classification declaration mechanism first (cheapest, most load-bearing piece); routing-policy logic can follow once at least 2 engines are registered to route between.
- **Last Updated:** 2026-07-05.

### Execution Runtime Registry

- **Description:** the catalogue of execution engines (Native SUOC, Hermes, future LangGraph/OpenHands) distinct from the catalogue of invocations (which are just Task Engine tasks).
- **Purpose:** let execution engines become replaceable plugins behind the Execution Engine Interface without SUOC needing to change per engine.
- **Engineering Confidence:** 40% — the design reconciles two independently-produced prior designs (MSN-0210J's minimal Protocol, MSN-0210I's pilot-tested field list) into one coherent schema, with real initial content (Native SUOC, Hermes) already specified — but nothing is built, and only one engine has ever actually been piloted.
- **Current Maturity:** L1 — Planned.
- **Current Status:** designed across two missions — MSN-0210L (Workstream B) proposed the base schema; MSN-0210M (Workstream D) added 4 missing fields (`allowed_classifications`, `trust_level`, `current_owner`, `engineering_confidence`) and populated it with real values for Native SUOC (Active, full trust) and Hermes (Experimental, Public/Internal only, low trust — no cloud path approved for anything more sensitive per MSN-0210I §9.1/§12).
- **Owner:** Chief Engineer.
- **Canonical Implementation:** none yet. Design: `reports/USS-TJR-MSN-0210L-Execution-Engine-Registry-Architecture.md`, `reports/USS-TJR-MSN-0210M-Secure-Execution-Policy-Architecture.md` Workstream D.
- **Consumers:** none yet — designed to be queried by Secure Execution Policy and Model Routing Policy.
- **Dependencies:** Task Engine (invocations are tasks), Audit (delegation decisions).
- **Capability Relationships:**
  - *Depends On:* Task Engine.
  - *Consumes:* engine self-declarations (capabilities, allowed classifications).
  - *Produces:* the queryable catalogue Secure Execution Policy and Model Routing Policy both consult.
  - *Future Dependencies:* Execution Engine Interface (the Protocol this Registry catalogues implementations of).
- **Related Missions:** MSN-0210H (build-vs-borrow discovery), MSN-0210I (Hermes pilot, the one real engine registered), MSN-0210J (original Protocol design), MSN-0210L (Workstream B, base schema), MSN-0210M (Workstream D, expanded schema + initial content).
- **Technical Debt:** no `execution_engines` table exists yet — deliberately deferred until a second engine is genuinely piloted (one row for Hermes alone doesn't yet justify new schema over a static config entry).
- **Next Planned Evolution:** build once a second execution engine is piloted (LangGraph or OpenHands, per MSN-0210H's survey) — a single-engine registry isn't yet worth its own table.
- **Last Updated:** 2026-07-05.

### Attention Engine

*(Formerly listed in Planned Platform Capabilities as "Relevance & Attention Engine" since Registry v1.0 / MSN-0210C §14 — promoted to a full record in MSN-0301, and renamed to drop "Relevance," since document/search-relevance scoring is already Search's job. Same capability, not a duplicate.)*

- **Description:** scores whether a `core_events` row deserves the Captain's attention right now (interrupt / delay / summarise / aggregate / remember), distinct from Confidence (is this claim trustworthy) and Search (is this document topically relevant).
- **Purpose:** the routing layer of the Captain Cognitive Model — thin threshold/dedupe/route logic, not a scoring engine itself (scoring is distributed to whichever domain emits the event).
- **Engineering Confidence:** 65% (was 55%) — **MSN-0339 (2026-07-08) put this into real continuous production for the first time**: `continuous_attention_evaluation` job, registered on `intelligence-scheduler.service` via a 10-minute `IntervalTrigger`, calling the real `evaluate_batch()` path against real `core_events` — confirmed running continuously via journal, zero gaps, since 2026-07-08 07:02 CEST. Raised from 55% for genuine continuous live wiring (this record previously said "zero live production wiring/scheduling" — that was true when written 2026-07-05, false as of MSN-0339). Held below 75%+ because `interrupt_now` has **still never fired against real data** — 0-for-0 as of MSN-0343 — and 4 of 6 categories have no real-event evidence at all yet (see MSN-0342 Evolution Roadmap §1).
- **Current Maturity:** L2 → **L3 candidate** — genuinely running continuously in production (not just validated once), held at L2 pending a real `interrupt_now` firing against real data.
- **Current Status:** built as a pure, side-effect-free routing table (`evaluate_event`/`evaluate_batch`) over `core_events`-shaped dicts — no Supabase dependency, no I/O, matches its own design intent exactly ("applies thresholds, doesn't compute domain-specific scores"). MSN-0306 built this against synthetic fixtures; MSN-0307 validated it against real events; **MSN-0339 WP3 wired it into `intelligence-scheduler.service` as a real 10-minute continuous job** (via `core/platform/captain_brief_orchestrator.py::assemble_captain_brief_document()` → `core/platform/interrupt_dispatcher.py::dispatch_interrupt_now()`), closing MSN-0338's Gap #5 ("evaluate_batch() was only ever invoked from a manual LCARS/Slack '/brief' click"). Real-world firing is still thin: every cycle observed so far evaluates ~200 `core_events` rows (mostly a repeating, unrelated `health.readiness.scored` stream, not ORI signals) and finds 0 `interrupt_now` — not because the module is broken, but because nothing has yet crossed both the importance and confidence floors simultaneously.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/platform/attention_engine.py` (`AttentionCategory`, `AttentionThresholds`, `AttentionDecision`, `evaluate_event`, `evaluate_batch`). Design: `reports/USS-TJR-MSN-0301-Captain-Intelligence-Core-Architecture.md` Workstream B. Scheduling: `intelligence/scheduler.py::_attention_evaluation_job` (MSN-0339 WP3). Test harness: `tests/test_attention_engine.py`, `tests/test_attention_evaluation_job.py`, `tests/fixtures/synthetic_core_events.py`.
- **Consumers:** `intelligence/scheduler.py`'s `continuous_attention_evaluation` job (MSN-0339, real, scheduled, production) — `core/platform/captain_brief_contract.py`'s `assemble_captain_brief()` also consumes this module's output, still unwired to any live surface itself.
- **Dependencies:** Event Bus, Domain Intelligence Framework (the emission contract other domains would use).
- **Capability Relationships:**
  - *Depends On:* Event Bus.
  - *Consumes:* real `core_events` rows (9+ domains now emit, per MSN-0330), synthetic fixtures for test coverage.
  - *Produces:* interrupt/delay/summarise/aggregate/remember routing decisions.
  - *Future Dependencies:* Priority & Opportunity Engine (consumes this capability's output as one input), Captain Intelligence Core (composes this with Priority into one experience).
- **Related Missions:** MSN-0210C §14 (original design), MSN-0301 (formalised architecture, Workstream B), MSN-0306 (built the pure logic + test harness against synthetic data, Programme B), MSN-0307 (first real-data validation), MSN-0308 (recommendation adapter), **MSN-0339 WP3 (real continuous production scheduling — the actual "next planned evolution" this record previously called for)**, **MSN-0343 (Registry currency correction — this record was stale relative to MSN-0339 by 2 days; found and documented as part of the Captain Intelligence Convergence Programme)**.
- **Technical Debt:** `interrupt_now` remains unobserved against real data (0-for-0) — not a defect, just an unearned claim not yet made. The continuous job re-evaluates the same ~200-row `core_events` window every cycle rather than only new rows since the last cycle — cheap today, worth revisiting once event volume grows. 4 of 6 `AttentionCategory` values have zero real-event evidence.
- **Next Planned Evolution:** observe a real `interrupt_now` firing against real data; per MSN-0342's roadmap, this module is one of the two shared building blocks (with Priority & Opportunity Engine) blocking cross-domain reasoning — extend evaluation to domains beyond ORI's real emit volume.
- **Last Updated:** 2026-07-08 (MSN-0343).

### Priority & Opportunity Engine

- **Description:** a weighted multi-factor ranking across urgency, importance, strategic/personal/career/health/financial value, time-sensitivity, opportunity value, and risk — comparative ranking across multiple attention-worthy items, distinct from Attention Engine's binary/threshold interrupt decision.
- **Purpose:** answer "given several things that all deserve attention, which matters more, and why" with an evidence trail, not a gut-feel ordering.
- **Engineering Confidence:** 40% — **MSN-0307 ran this module against real events for the first time**: correctly ranked the 2 higher-importance real/constructed events above 16 null-importance ones (stable-sorted, tied at 0.00, order preserved), fully explainable, deterministic on re-run. Held below 60%+ because `value`/`opportunity`/`time_sensitivity` remain 0 for every real event today (Relationship Model too sparse, no Content Intelligence emitter) — confirmed with real data, not just reasoned about, that ranking today is driven entirely by importance/urgency/risk.
- **Current Maturity:** L2 — Implemented, first real-data validation pass complete (still zero live production wiring).
- **Current Status:** built as a pure scoring function (`score_event`/`rank_events`) over 6 weighted dimensions. Urgency/importance from `core_events` directly (time-sensitivity accepted as an optional input — no `core_events` column carries it today, a genuine gap this build surfaced and MSN-0307 confirmed still true with real data); value dimensions accepted as a `dict[str, int]` shaped like future Relationship Model edge output (MSN-0307 confirmed the 12-13 real edges that exist don't touch any domain in this validation); risk computed as the inverse of importance/confidence exactly as designed; opportunity value accepted as an optional input for Content Intelligence's scoring to eventually supply (no such emitter exists yet). `relevance` is present on real events but **not currently a scored dimension at all** (MSN-0307 finding — accepted on `AttentionDecision` but never consumed by `score_event()`), worth naming so a future reader doesn't assume it silently feeds priority.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/platform/priority_engine.py` (`PriorityWeights`, `PriorityInputs`, `PriorityScore`, `score_event`, `rank_events`). Design: `reports/USS-TJR-MSN-0301-Captain-Intelligence-Core-Architecture.md` Workstream C. Test harness: `tests/test_priority_engine.py`.
- **Consumers:** none in production — `core/platform/captain_brief_contract.py`'s `assemble_captain_brief()` consumes this module's output, itself also unwired to any live surface.
- **Dependencies:** Attention Engine (consumes its filtered output), Relationship Model, Confidence, Content Intelligence.
- **Capability Relationships:**
  - *Depends On:* Attention Engine, Relationship Model, Confidence.
  - *Consumes:* real `core_events` rows, relationship edges (too sparse to matter yet), confidence scores (none populated yet).
  - *Produces:* a ranked, explainable priority list (every score exposes its component breakdown).
  - *Future Dependencies:* Captain Intelligence Core (composes this with Attention Engine).
- **Related Missions:** MSN-0301 (designed, Workstream C), MSN-0306 (built the pure scoring model + test harness against synthetic data, Programme B), MSN-0307 (first real-data validation — confirmed value/opportunity/time_sensitivity all contribute 0 with real data today; found `relevance` isn't scored at all), MSN-0308 (added the `core_events.time_sensitivity` column — schema now exists, live-verified round-trip; assessed value/opportunity as blocked on separate future missions, not fixable here; confirmed `relevance` was never meant to be a 7th weighted dimension per the original design, not a gap).
- **Technical Debt:** the actual weighting function remains a documented placeholder, unlearned. `time_sensitivity` now has a real `core_events` column (MSN-0308) but zero domains populate it yet — schema readiness, not real data. `value`/`opportunity` remain blocked on Relationship Model maturity and a Content Intelligence opportunity emitter respectively, neither of which is this capability's own work to build.
- **Next Planned Evolution:** Blueprint Wave 3 — build/tune the real weighting function once at least 2 domains emit real (not synthetic) scored events to rank against; decide which domain first populates `time_sensitivity` now that the column exists.
- **Last Updated:** 2026-07-05.

### Continuous Captain Brief Orchestration

- **Description:** assembles the canonical `CaptainBriefDocument` — one UI-independent intelligence product (summary, priorities, recommendations, per-domain sections, warnings, next actions, metadata, confidence) that any future Captain Experience presents differently. The primary intelligence product of Starship, per the Captain Experience Programme's own framing.
- **Purpose:** decide "what should the Captain know right now," not collect more intelligence — a pure orchestration layer over already-built primitives.
- **Engineering Confidence:** 60% (was 50%) — live-verified against the 16 real Operational Resilience Intelligence events (single-domain case) and a disclosed multi-domain validation run; MSN-0315 added its first real UI consumer. **MSN-0339 WP3 (2026-07-08) added a second, genuinely scheduled real consumer**: `intelligence/scheduler.py`'s `continuous_attention_evaluation` job calls `assemble_captain_brief_document()` every 10 minutes as part of its interrupt-check chain — this record's own prior "no scheduler yet" gap is resolved, just not in the way originally envisioned (the scheduling arrived via the Operational Intelligence Recovery Programme, not a dedicated Captain Brief scheduling mission). Still held below 75%+: never run against genuinely organic multi-domain production data (ORI still dominates real volume), and the LCARS UI consumer still hasn't been exercised with a real authenticated session end-to-end.
- **Current Maturity:** L2 — Implemented, two real consumers now (one on-demand UI, one scheduled), still short of L3.
- **Current Status:** built as a pure composition (MSN-0313) over Event Bus, Attention Engine, Priority & Opportunity Engine, and the Recommendation adapter (MSN-0308) — zero lines changed in any of those modules. **MSN-0315:** first live UI consumer — `lcars-portal`'s `/captains-brief` page, via a subprocess bridge. **MSN-0339 WP3:** first live *scheduled* consumer — the OI continuous attention-evaluation job, called purely for its `AttentionDecision` output (not for full brief content/delivery, which stays `intelligence/captains_brief.py`'s job — a deliberately separate pipeline per MSN-0328 Wave 3's own finding, reaffirmed by MSN-0342/0343). `core/platform/captain_brief_evolution.py` (MSN-0329) also calls this function internally to build the LLM Understanding/Insight/Reasoning layer on top — a disclosed, harmless double-evaluation of `evaluate_batch()`, not a competing implementation.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/platform/captain_brief_orchestrator.py` (`CaptainBriefDocument`, `assemble_captain_brief_document`). Design: `reports/USS-TJR-MSN-0313-Captain-Brief-Orchestration-Completion.md`. Bridge (MSN-0315): `core/platform/captain_brief_cli.py`. Scheduled consumer (MSN-0339): `intelligence/scheduler.py::_attention_evaluation_job`.
- **Consumers:** `lcars-portal`'s `/captains-brief` page (MSN-0315, via `/api/captain-brief`); `core/platform/captain_brief_evolution.py` (MSN-0329, LCARS Captain's Chair); `intelligence/scheduler.py`'s continuous attention-evaluation job (MSN-0339 WP3, real, scheduled, production — new).
- **Dependencies:** Event Bus, Attention Engine, Priority & Opportunity Engine, Recommendation adapter (`captain_brief_contract.py`).
- **Capability Relationships:**
  - *Depends On:* Attention Engine, Priority & Opportunity Engine, Event Bus.
  - *Consumes:* real `core_events` rows (poll_events output), Attention/Priority Engine output, Recommendation objects.
  - *Produces:* one `CaptainBriefDocument` per assembly call, consumed by the LCARS `/captains-brief` page, `captain_brief_evolution.py`, and (interrupt-decisions only) MSN-0339's continuous job.
  - *Future Dependencies:* any further Captain Experience interface (mobile, voice, conversational, notifications, email) — all can consume this same object, per §6 of the completion dossier; Slack/Telegram are documented candidates but not yet wired for full-document consumption (Telegram's OI brief remains its own separate pipeline, by design).
- **Related Missions:** MSN-0313 (built + validated), MSN-0315 (first live UI consumer wired, Phase 1C), **MSN-0339 WP3 (first live scheduled consumer, via the OI Recovery Programme)**, **MSN-0342/0343 (Registry currency correction — this record's "no scheduler yet" gap was already resolved by MSN-0339 two days before this record was next read)**.
- **Technical Debt:** never run against genuinely organic multi-domain production data (ORI still dominates real volume); the LCARS UI consumer hasn't been exercised with a real authenticated session; the subprocess bridge spawns `python3` per request — fine at current load, revisit if scaling; `evaluate_batch()` is called twice per cycle by `captain_brief_evolution.py` (disclosed, harmless, not fixed — refactor risk exceeds the inefficiency it would remove).
- **Next Planned Evolution:** per MSN-0342/0343's Captain Brief Convergence finding — this module, `captain_brief_evolution.py`, and `intelligence/captains_brief.py` should be formally documented as one architecture (canonical base / reasoning layer / legitimate separate producer) rather than three independently-tracked capabilities; re-validate once Engineering/Research/Content Intelligence gain real emit volume.
- **Last Updated:** 2026-07-08 (MSN-0343).

### Captain Intelligence Core

- **Description:** the single decision-support layer sitting above every domain and below the Captain — composes the Captain Cognitive Model, Attention Engine, and Priority & Opportunity Engine into one coherent experience. Every future intelligence capability should ultimately serve this layer rather than communicating directly with the Captain.
- **Purpose:** shift Starship from "a collection of intelligence systems" to "one coherent decision-support layer" — the explicit Phase 2 objective.
- **Engineering Confidence:** 80% (was 78%) — **MSN-0329 Phase 5**: `assemble_evolved_captain_brief()` is now wired into a real production surface (LCARS Captain's Chair — a "Captain Intelligence" panel, real read + explicit on-demand real generation). Re-testing before this shipped found and fixed 2 more real bugs that would have silently broken the observation period: `_call_model_router()`'s default timeout was 30s in the actual (never-overridden) production call path (real synthesis needs 50-260s) — masked through Phase 3/4 by manual scripts that always passed an explicit override; and `captain_brief_evolution.py` had imported `insight_outcomes.record_insight()` in Phase 4 but never actually called it, so Phase 4's own claim of being "wired" was wrong — found by re-querying the real table and seeing the row count hadn't moved. Both fixed and re-verified (1→2 real rows on the next real run). Held below 85%: the pipeline now has a real consumer, but `insight_outcomes` still only has 2 real rows — an explicit, Captain-approved Operational Observation Period is now in effect (no tuning before 20 real rows across 10+ distinct days).
- **Current Maturity:** L2 → **L3 candidate** — real production consumer now exists (LCARS Captain's Chair). Held at L2 pending real operational history accumulating (2 rows today, need 20 across 10+ days per the Captain-approved threshold) before any tuning/confidence-scoring claim can be made.
- **Current Status:** designed as a composition, not a new mechanism — its "engine" is Attention Engine + Priority & Opportunity Engine + the Domain Intelligence Framework's emission contract, wired together. No new storage, no new service of its own. **MSN-0328 Wave 2 finding, still load-bearing:** 2 independently-real pipelines exist (this one, event-stream based; `core/context-assembly/context_service.py`, filesystem-corpus based) — Captain resolved: this one (Path A) is canonical, extended not replaced. **MSN-0328 Wave 3 finding, equally load-bearing:** not every named consumer was actually duplicating briefing-assembly logic. Slack's `decision.py` genuinely was (a capacity-aware recommendation engine competing with the Attention/Priority Engine's own purpose) — converged, by emitting its output into the canonical stream rather than being deleted (deleting it would have been a real regression; its scoring has no equivalent in the generic pipeline). Telegram's `/brief` and the scheduler's morning brief are NOT duplicating anything — they're direct reads of their own authoritative tables/services, and forcing them onto the generic metrics path would either duplicate data pointlessly or lose real content the metrics field doesn't carry yet (period ranges, event counts, blockers). Left unconverted, on purpose, disclosed plainly. Full detail: `reports/USS-TJR-MSN-0328-Wave2-Architecture-Map.md`, `reports/USS-TJR-MSN-0328-Wave3-Consumer-Convergence.md`.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** none yet as its own composition point. Design: `reports/USS-TJR-MSN-0301-Captain-Intelligence-Core-Architecture.md`. Its prerequisite (Event Bus/`captain_brief_orchestrator.py`) coverage: see Event Bus's own record above.
- **Consumers:** `slack-bot/commands/brief.py` + `lib/daily_brief.py` (MSN-0328 Wave 3, partial — 4 of ~9 sections), `lcars-portal/src/app/(app)/captains-brief/page.tsx` (MSN-0313/0315, since-inception; MSN-0328 added metrics rendering); **`lcars-portal/src/app/(app)/captains-chair/page.tsx`'s "Captain Intelligence" panel (MSN-0329 Phase 5, new — the first real production consumer of `assemble_evolved_captain_brief()`/the full Understanding/Insight/Reasoning pipeline; read via `/api/captain-intelligence/insights`, on-demand generation via `/api/captain-intelligence/generate`).**
- **Dependencies:** Attention Engine, Priority & Opportunity Engine, Event Bus, Unified Memory, Confidence, Relationship Model.
- **Capability Relationships:**
  - *Depends On:* Attention Engine, Priority & Opportunity Engine.
  - *Consumes:* every domain's `core_events` stream (via the Domain Intelligence Framework contract) — 12 real emit-points, not 3.
  - *Produces:* the Captain-facing decision-support surface — now genuinely consumed for part of Slack's `/brief`; a full Understanding/Insight/Reasoning pipeline exists (MSN-0329) but has no live caller yet; every insight/recommendation it does produce is now durably recorded in `insight_outcomes`.
  - *Future Dependencies:* Slack's own secondary path (`/captain-brief`, `/operating-picture`, via Context Assembly), Telegram's `/brief`, the scheduler — grandfathered per MSN-0329 Phase 0's Option C, not an open question.
- **Related Missions:** MSN-0301 (designed, whole mission), MSN-0328 Waves 2-3 (Event Bus coverage extended, first render convergence, Telegram/scheduler found legitimate), MSN-0329 Phases 0-4 (substrate decision, full pipeline built, first real production run, measurement foundation built), **MSN-0329 Phase 5 (wired into a real production consumer — LCARS Captain's Chair; 2 more real bugs found and fixed pre-launch; Operational Observation Period now in effect, Captain-approved evidence threshold: 20 real rows across 10+ distinct days before any tuning).**
- **Technical Debt:** `insight_outcomes` has 2 real rows (both from engineering validation, not yet organic Captain usage) — the Operational Observation Period's 20-row/10-day threshold governs when any tuning/confidence-scoring work may start; until then, report state honestly, change nothing. `core_events` still concentrated in one domain in practice — the newer emitters (missions/delivery/strategy/comms/knowledge/research) have zero real rows so far. Automation domain has no clean choke point — disclosed, not implemented. `model-router.service` is real infra shared with other live bots — restart deliberately, not casually. Context Assembly Foundation's captain-brief-specific consumers remain grandfathered per Option C. LCARS generate route's 290s client timeout assumes no shorter reverse-proxy/serverless timeout sits in front of it — not re-verified against this platform's actual deployment target this pass.
- **Next Planned Evolution:** none from engineering. Wait for real Captain's Chair usage to accumulate real `insight_outcomes` history; re-run the regression harness after any future prompt/threshold change (none planned until the evidence threshold is met); revisit Automation's domain coverage only if a specific real need arises.
- **Last Updated:** 2026-07-07.

### Captain Experience Component Library

*(New capability record, MSN-0315 — registered now per Captain direction, "once the implementation is real and operational," not before. Executes Phase 1 of `Missions/Active/CAPTAIN-EXPERIENCE-IMPLEMENTATION-ROADMAP.md`, reusing MSN-0310's ratified Design System v1.0, component inventory, accessibility standard, and governance model as-is.)*

- **Description:** 7 formalized shared UI components (Confidence Indicator, Data Source Indicator, Escalation Banner, Recommendation Card, Executive Summary, Approval Queue canonical contract, Mobile-Adapted Variant) replacing every genuine duplicate found across `lcars-portal`, built on the `state.*` design-token layer (Phase 1A), plus initial adoption onto Command Centre (token convergence) and a first live consumer for the previously-unconsumed `CaptainBriefDocument`.
- **Purpose:** one canonical implementation per shared UI concept instead of each surface reimplementing its own confidence bar / escalation banner / live-data indicator — SUOC Platform Principle #5 applied to the UI layer.
- **Engineering Confidence:** 65%, unchanged this update — the figure itself is a separate Captain governance decision ("held at this level, not raised," 2026-07-06) not revisited here. **Corrected 2026-07-06 (MSN-0328):** of the 4 real bugs the DO/VDO review found beyond self-reporting, 3 are confirmed fixed by `MSN-0315 Phase 1E` (commits `7ba0318b`, `bfd14345`, same day, before this correction) — `ApprovalQueue`'s raw department-tone classes now use `stateToneClasses` throughout (verified by direct read); `/captains-brief` now renders `warnings` in full (not a bare count) and renders `recommendations` (previously not rendered at all); its `EscalationBanner` now derives level from the worst warning's real `risk_score` (previously hardcoded to `level={3}`). **The 4th finding — Command Centre's ~40 unconverted hardcoded colours in `index.html` — was not re-verified this update; treat its "not complete" status below as last confirmed, not re-checked.**
- **Current Maturity:** L2 — Implemented, real interior adoption (7 `lcars-portal` migrations, Command Centre token convergence, one Captain Brief consumer). 3 of 4 DO/VDO remediation items now fixed and verified (see above); the Command Centre repaint item's status is unconfirmed as of this update.
- **Current Status:** all 7 Phase 1 components live in `lcars-portal/src/components/`. Command Centre's frontend token layer converged onto canonical light tokens; the repaint's completeness was **last found incomplete** by Visual Design Officer review (not re-checked this update — see Engineering Confidence note). `CaptainBriefDocument`'s live UI consumer (`/captains-brief`) now surfaces `warnings` and `recommendations` correctly (MSN-0315 Phase 1E, verified fixed). Slack/Telegram's existing state-representation conventions documented as canonical (no new code needed there).
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `lcars-portal/src/components/{ConfidenceIndicator,DataSourceIndicator,EscalationBanner,RecommendationCard,ExecutiveSummary,ApprovalQueue}.tsx`; `MobileCommandBar.tsx`/`LCARSBottomNav.tsx` (verified complementary responsive components, not merged — see Technical Debt); `lcars-portal/src/lib/departments.ts` (`stateToneClasses`); `lcars-portal/tailwind.config.ts` (`state.*` tokens, Phase 1A); `core/command-centre/frontend/tokens.css`; `core/platform/captain_brief_cli.py` + `lcars-portal/src/app/api/captain-brief/route.ts` + `lcars-portal/src/app/(app)/captains-brief/page.tsx`.
- **Consumers:** every `lcars-portal` panel migrated in Phase 1B (`RecoveryConfidencePanel`, `HumanSystemsPanel`, `WellnessInsightPanel`, `DeliveryPanel`, `ROSPanels`, `CommandStrip`, `MobileOperatingPicture`, `CaptainApprovalQueue`); Command Centre's `index.html`/`mission-registry.html` (token layer only); the new `/captains-brief` page. **MSN-0334:** `ApprovalQueue.tsx`'s canonical `ApprovalQueueItem` contract gained an optional `href` (a real navigation-continuity gap — approving/rejecting left no path back to the item's own record); `CaptainApprovalQueue` and `ProactiveSignals` (newly wired onto Captain's Chair for the first time — it existed with zero real callers anywhere) both populate it now.
- **Dependencies:** Design System v1.0 / accessibility standard / Design Governance Model (MSN-0310, ratified, reused as-is); Design Officer / Visual Design Officer runtime personas (MSN-0312, commissioned but not yet exercised as a review gate against this work).
- **Capability Relationships:**
  - *Depends On:* none technical — a UI-layer capability.
  - *Consumes:* Continuous Captain Brief Orchestration's `CaptainBriefDocument` (new, first consumer).
  - *Produces:* the canonical component set every future Captain-facing surface should consume; closes Continuous Captain Brief Orchestration's "no interface consumer yet" gap.
  - *Future Dependencies:* none identified.
- **Related ADRs:** ADR-027 (Whole-of-System Principle — components now discoverable/reused rather than silently re-forked).
- **Related Missions:** MSN-0303 (Experience Architecture Dossier, evidence base), MSN-0310 (Design System v1.0, component inventory, ratified — 3 of its inventory's cited file/duplicate references confirmed stale this pass, see Technical Debt), MSN-0312 (Design Officer/Visual Design Officer runtime commissioning), MSN-0313 (`CaptainBriefDocument`, now has its first consumer), MSN-0314 (branch reconciliation that ported the roadmap onto main), MSN-0315 (this mission — built the library).
- **Technical Debt:**
  1. ~~**Command Centre repaint incomplete (VDO finding, high priority)**~~ **FIXED, Phase 1E** — swept ~85 hardcoded literal colour occurrences (across ~20 distinct hexes, not just VDO's 5-hex spot-check sample) onto `var(--sf-*)` tokens; converted `.search-results-overlay`/`.notif-drawer` off hardcoded dark backgrounds onto `var(--sf-bg-panel)`; retired the starfield (mismatched on light theme, not replaced with a new asset — that's a VDO decision if wanted); added a new `--sf-accent` token (`#0C5A82`) since the old theme's `#00ccff` had no light-theme equivalent at all. Full before/after in `core/command-centre/frontend/docs/COMMAND-CENTRE-CONTRAST-MATRIX.md` and the Implementation Dossier's Phase 1E section. ~31 decorative `rgba(255,255,255,alpha)` border/hover overlays deliberately NOT swept (cosmetic dimness on light bg, not the illegible-text defect) — flagged as a smaller follow-up, not silently ignored.
  2. ~~**Command Centre "science" tab hex fails contrast (VDO finding)**~~ **FIXED, Phase 1E** — re-shaded `#0891B2` → `#06768D`; computed 4.24/4.63/3.67 against space/panel/card, clears ≥3:1 everywhere (was 2.96/3.23/2.56). Validated via `core/command-centre/frontend/docs/cc_contrast_check.py`.
  3. **Command Centre brand-identity colour collision (VDO finding, new):** the tab labelled "Engineering" is styled with `--sf-dept-ops` (red), not `engineering` (orange) — a real naming/colour mismatch against the Design System vocabulary. Related: `--sf-dept-science` (the new cyan) is attached to a tab literally labelled "Starfleet Records," while lcars-portal's own purple `science` hex is reused for CC's "Astrometrics" tab — a "science" naming collision across two colours.
  4. **`ApprovalQueue` design-system compliance regression (Design Officer finding, new):** approve/reject/flash use raw `border-status`/`border-operations` classes instead of `stateToneClasses('ok'/'crit')` — the exact department-colour-as-state pattern this same phase was built to eliminate, reintroduced in its 6th component. Tap targets on approve/reject are also undersized for a consequential mobile action.
  5. **`/captains-brief` hides fetched content (Design Officer finding, new):** `warnings` renders as a count only, no drill-down to the actual items; `recommendations` is fetched/typed but never rendered; `EscalationBanner`'s `level` is hardcoded to `3` regardless of real severity, undermining this mission's own severity-inversion fix one layer up. Five of six domain sections get a bare row treatment even when their items carry the same `priority_score`/`recommendation` data the `priorities` bucket gets full card treatment for.
  6. Nav label drift: the same route reads "Chair" on `MobileCommandBar` and "Situation" on `LCARSBottomNav` (Design Officer finding).
  7. All 6 ratified department `DEFAULT` colours still fail WCAG 3:1 contrast (Phase 1A finding, pre-existing) — Visual Design Officer's call, unresolved.
  8. Command Centre's own 5-tab department taxonomy does not biject onto `lcars-portal`'s 6 canonical department keys — flagged by both officers as a genuine future IA/brand convergence decision, not a one-off footnote.
  9. Slack Commander has two different confidence-rendering conventions in two different files (percentage tag vs. 10-cell emoji bar) — documented, not reconciled.
  10. **MSN-0335, resolved:** `/ai-console` (a live duplicate of Advisory Council's own role-based chat concept, predating its consolidation) retired — its one real unique capability, per-message model selection, ported into Advisory Council's `ConsultMode` first and confirmed genuinely wired before deletion.
  11. **MSN-0335, resolved:** 7 retired redirect-stub pages (advisory/chief-of-staff/executive-staff/xo/xo-brief/content/knowledge-base) deleted outright — each individually verified to have zero remaining references before removal.
  12. ~~**MSN-0335, open:** capture consolidation (`/captains-notebook` vs `/capture`) investigated but not implemented — found 3 real capture entry points (not 2: Slack's own `/note_capture.py` also writes `intelligence_notes`), a real working 7-module officer-triage backend on `intelligence_notes`, and no bridge to `captured_items`.~~ **PARTIALLY RESOLVED, MSN-0336 + MSN-0337** — promotion bridge built and validated end-to-end (MSN-0336); Slack's `/note_capture.py` entry point removed outright, Slack being fully retired (MSN-0337) — down to 2 real entry points (`/capture`, Notebook's own form). Notebook's own form intentionally not yet removed (see Capture Promotion Bridge record, Technical Debt) — needs organic-volume validation first, not a rushed removal against one test case.
  10. `MobileOperatingPicture`'s ad hoc escalations block still not migrated onto `EscalationBanner` (Design Officer finding) — same pattern this phase consolidated elsewhere, left outside this pass's scope.
  11. **MSN-0310 inventory corrections (found stale on inspection, independently re-confirmed by Design Officer review):** (a) its "two competing bottom-nav components" claim (§6) does not hold on the current codebase — `MobileCommandBar`/`LCARSBottomNav` are complementary, not duplicates (though they do share 2 of 5 destinations, one under different labels — see item 6); (b) its Executive Summary/Data Source Indicator inventory rows cited `DepartmentCard`/`LCARSHeader` as duplicate sites — neither reference matched current disk content. MSN-0310's inventory table itself should be corrected in a future pass rather than relied on as-is.
  12. ~~**Command Centre accessibility defects (found by MSN-0317's Runtime Render Validation pilot)**~~ **FIXED, MSN-0318** — 5 critical `select-name` violations (accessible-name fixes), the recurring `.chair-clear` contrast failure (`--sf-status-ok`→`--sf-status-ok-text`, one rule fixes all 7 instances), and structural `landmark-one-main`/`page-has-heading-one`/`region` gaps (added `<main>`/`<header>`/`<footer>`, `h1`). Verified via Runtime Render Validation: 26→0 accessibility violations, 0 visual regressions. Both Design Officer and Visual Design Officer independently reviewed and approved (with recommendations, no rework required).
  13. ~~**3 instances of the same DEFAULT-vs-`-text` token misuse pattern, found/confirmed via MSN-0319 Phase 2A's expanded scenario coverage**~~ **FIXED, MSN-0319 Phase 2B** — `renderORBrief()`'s RED branch (`index.html:1584`) and GREEN/else branch (`index.html:1585`), and `.blocker-section-title.critical` (`index.html:235`), all moved from their DEFAULT token (`--sf-status-crit`/`-ok`) to the corresponding `-text` variant. Verified via Runtime Render Validation: 0 accessibility violations across all 14 scenarios (was 3), 0 visual regressions after baseline update (diff images confirmed only the remediated text changed colour, nothing else, before updating). Reviewed adjacent same-cycle code for the same pattern (`renderStrategicWatchlist()`, `.blocker-section-title`'s `.high`/`.normal` siblings) — none found. Along the way, corrected an inaccuracy in the original MSN-0318 finding: the Visual Design Officer's companion citation of `loadCommandBlockers()` (`index.html:2336`) was dead code, never called — the live path, `renderCmdBlockers()` (`index.html:1487`), already carried MSN-0318's `.chair-clear` fix.
  14. **2 recommendations surfaced during item 13's remediation, explicitly not fixed (documented, not scope-expanded):** (a) `statusColour()`'s readiness-label bug (`index.html:1007-1013`) — same DEFAULT-vs-`-text` root cause, pre-existing, first disclosed in MSN-0315's 5th Joint Review, outside Phase 2A's approved coverage; (b) `loadCommandBlockers()`/`renderCommandDashboard()` (`index.html:2321` onward) are confirmed entirely dead code (the latter's only caller is the former) — a code-hygiene/dead-code-removal candidate, not an accessibility defect.
- **Next Planned Evolution:** item 13 above (2-site fast-follow, same pattern as the already-fixed item 12) is the next concrete Command Centre action; item 3 (brand-identity colour collision) and items 4-10 remain the rest of the original consolidated remediation list before Registry confidence is reconsidered further.
- **Last Updated:** 2026-07-06.

### Capture Promotion Bridge

*(New capability record — MSN-0336, 2026-07-07.)*

- **Description:** promotes `mission`/`decision`/`research`/`reference`-classified `captured_items` into `intelligence_notes` for officer triage, and gives the existing Notebook triage engine (7 real modules, previously never invoked) its first real trigger anywhere in the platform.
- **Purpose:** connect Quick Capture (`/capture`, the platform's genuinely low-friction entry point) to the Notebook officer-triage pipeline, without duplicating either — MSN-0335's own disclosed blocker to real capture consolidation.
- **Engineering Confidence:** 70% — validated end-to-end against one real production item (research classification, confidence 0.9): the full pipeline ran for the first time ever, `CAPTURED → OFFICER_REVIEW → NUMBER_ONE_REVIEW → READY_FOR_ROUTING`, zero errors, correct provenance, correctly stopped at the human-approval gate. Held below 80%: one real success is a genuine proof of concept, not proof of production readiness at volume — no `mission`-classified promotion tested yet, no concurrent-promotion edge case tested.
- **Current Maturity:** L2 — implemented, live, one real validated case.
- **Current Status:** `core/capture/enrichment_worker.py::_promote_to_intelligence_note()` runs inside the existing, already-live `capture-enrichment.timer` (confirmed active, every 15 minutes) — no new systemd unit created. `_advance_notebook_pipeline()` calls the pre-existing, unmodified `run_notebook_pipeline()` afterward. Migration 0067 added `intelligence_notes.metadata` (the table had no provenance column at all before this). `_NEVER_AUTO_ROUTE` narrowed from `{mission, decision, research, unclassified}` to `{unclassified}`.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `core/capture/enrichment_worker.py` (`_promote_to_intelligence_note`, `_advance_notebook_pipeline`), `core/infrastructure/supabase/migrations/0067_intelligence_notes_metadata.sql`.
- **Consumers:** none yet directly — this is the connecting layer between two existing consumers (Quick Capture, Notebook's own triage UI), not a new Captain-facing surface itself.
- **Dependencies:** the existing Notebook triage engine (`slack-bot/lib/notebook/notebook_router.py` and its own dependencies — confirmed zero Slack-specific imports, portable to any process), the real `supabase` Python client (available in `slack-bot/.venv`, the same venv `capture-enrichment.service` already runs under).
- **Capability Relationships:**
  - *Depends On:* the pre-existing capture enrichment worker (extended, not replaced) and Notebook triage engine (unmodified).
  - *Consumes:* `captured_items` rows with a promotable classification.
  - *Produces:* real `intelligence_notes` rows entering officer triage.
  - *Future Dependencies:* full capture consolidation (retiring Notebook's own capture form) once the volume/parity work below is done.
- **Related Missions:** MSN-0335 (found the gap, deliberately did not rush a fix), MSN-0336 (found the triage engine had zero real callers before writing any bridge code, built the bridge, wired the real trigger, validated end-to-end against real production data), **MSN-0337 (retired Slack's `/note-capture` entry point outright since Slack itself is fully retired; also renamed the shared `slack-bot/` runtime directory to `platform-runtime/` after finding 7 of 8 real services depending on it have nothing to do with Slack).**
- **Technical Debt:** Slack's `/note-capture` entry point removed outright (MSN-0337, Slack fully retired). Notebook's own web form still writes directly to `intelligence_notes`, bypassing this bridge — one remaining parallel path into the same pipeline, not yet reconciled; kept deliberately (see MSN-0337) until organic usage volume, not just one test case, proves the bridge stable. Only the `research → knowledge` triage outcome has been exercised for real; `mission`/`decision`/`reference` promotions are implemented but not yet validated against real data.
- **Next Planned Evolution:** let real captures accumulate through this path over a longer real period; validate a `mission`-classified promotion; then revisit whether Notebook's own capture form can retire in favour of this bridge being the sole path in.
- **Last Updated:** 2026-07-07.

### Runtime Render Validation Framework

*(New capability record, MSN-0317 — registered as a permanent Platform Capability per Captain commissioning decision 2026-07-06, following a feasibility spike (MSN-0316) and a Phase 1 pilot. Motivated by MSN-0315's 5th Joint Review finding real defects hiding in runtime-constructed JS presentation logic outside `tools/css_token_guard.py`'s static-text coverage — but scoped and built as a platform-wide capability, not an MSN-0315-specific fix.)*

- **Description:** a reusable rendered-UI validation capability — launches a real headless browser (Playwright/Chromium), renders a real application page, and checks what the browser actually computed: accessibility (`axe-core`), computed CSS variable resolution, runtime-generated styling, and pixel-level visual regression against committed baselines. Supports 5 distinct application states — **default, loading, empty, populated, and error** — via a generic mocked-runtime-validation mechanism (Playwright route interception, no live backend required). Sits as a new layer in the validation pipeline (see the adopted sequence under Engineering Governance below), between existing engineering tests and human Design Officer / Visual Design Officer review.
- **Purpose:** catch the defect class no static-text tool can see by design — a style assembled at runtime by JS, a CSS variable that resolves to nothing despite being defined in source, a visual regression no contrast calculation would ever flag, or a defect that only manifests in a specific application/data state — without replacing any existing validation layer.
- **Engineering Confidence:** 78% — this is a measurement of demonstrated capability maturity, not a subjective assessment: the framework has now been exercised through a complete detect → remediate → re-validate cycle on findings it found itself (Phase 2A found/confirmed 3 real defects across 5 application states; Phase 2B remediated all 3 and re-verified 0 violations across all 14 scenarios, 0 visual regressions, each diff image manually inspected before trusting it). Held at 78% rather than higher because it still has a single pilot target (Command Centre only), the mocked API responses are hand-authored against source-read contracts rather than validated against a live backend (schema drift would go undetected), and pixel-exact (not tolerance-tuned) visual comparison remains untested across environments.
- **Current Maturity:** L2 — Implemented. **Runtime Validation maturity programme complete** (MSN-0316 feasibility → MSN-0317 framework build → MSN-0318 first remediation cycle → MSN-0319 scenario coverage expansion + second remediation cycle). One real pilot target (Command Centre); framework itself deliberately generic and target-agnostic (`src/` carries zero Command-Centre-specific logic). Per Captain decision 2026-07-06, now treated as a **stable platform capability that future applications consume**, not one under continuous active development, absent a newly identified capability gap.
- **Current Status:** `tools/runtime-validation/` — core framework (`renderer.js`, `accessibility.js`, `computedStyle.js`, `visualRegression.js`, `report.js`, `validator.js`) plus one pilot target (`targets/command-centre.js`, 14 scenarios: 7 default-render tab scenarios + 7 API-driven state scenarios covering loading/empty/populated/error conditions via route mocking). Not wired into CI, no gates, no automatic blocking — run manually, read a report, by design.
- **Owner:** Chief Engineer.
- **Canonical Implementation:** `tools/runtime-validation/src/` (framework), `tools/runtime-validation/targets/command-centre.js` (pilot target), `tools/runtime-validation/bin/validate.js` (CLI entry point).
- **Consumers:** none yet in an automated sense — run on-demand; its first real evidentiary use was this pilot's own commissioning dossier (`reports/USS-TJR-MSN-0317-Commissioning-Dossier.md`).
- **Dependencies:** Playwright (bundled Chromium), `@axe-core/playwright`, `pixelmatch`/`pngjs`. No dependency on any other Platform Capability — a standalone validation layer by design, consistent with how `tools/css_token_guard.py` also has none.
- **Capability Relationships:**
  - *Depends On:* none technical.
  - *Consumes:* nothing from another capability — operates directly on rendered application output.
  - *Produces:* structured accessibility/visual-regression/CSS-resolution reports, intended as future evidence input to Design Officer / Visual Design Officer review and commissioning dossiers.
  - *Future Dependencies:* Captain Experience Component Library (a natural second target once `lcars-portal` adoption, Phase 2, is chartered).
- **Related ADRs:** ADR-027 (Whole-of-System Principle — a validation gap disclosed repeatedly across 5 MSN-0315 rounds is now a discoverable, owned, permanent capability rather than a recurring unverified assumption).
- **Related Missions:** MSN-0315 (5th Joint Review — the originating evidence), MSN-0316 (feasibility spike, GO), MSN-0317 (this mission — built the framework and the Command Centre pilot), MSN-0318 (first real remediation cycle using this framework — 26→0 accessibility violations, both officer reviews converged Approved with Recommendations, no Rework Required), MSN-0319 (Wave 2 — Phase 2A scenario coverage expansion found/confirmed 3 real findings; Phase 2B remediated all 3, verified 0 violations across all 14 scenarios, 0 visual regressions).
- **Technical Debt:** visual regression is pixel-exact with no anti-aliasing/cross-environment tolerance tuning yet; `computedStyle.js` confirms a CSS variable resolves to *some* value, not yet a *specific expected* value (a target's own scenario can add that assertion, the primitive doesn't yet); single pilot target (Command Centre only) — `lcars-portal` adoption not yet attempted and structurally different (requires a running server, not a `file://` load); mocked API responses are hand-authored against source-read contracts, not validated against a live backend (schema drift would go undetected). All findings the pilot and Wave 2 coverage expansion produced (2 critical `select-name` violations + landmark/heading structure, MSN-0318; `renderORBrief()` RED/GREEN branches + `.blocker-section-title.critical`, MSN-0319) have been remediated and re-verified — see Captain Experience Component Library's Technical Debt items 12-13 for the closed record.
- **Next Planned Evolution:** Runtime Validation maturity programme complete per Captain decision 2026-07-06 — the framework is now **the standard validation platform for all future Captain-facing interfaces**, treated as stable rather than under continuous active development. Phase 2C (`lcars-portal` adoption) and Phase 2D (CI/CD governance decision) remain separately gated, chartered only if a future application adoption or a newly identified capability gap warrants it. Strategic priority shifts to product maturity — `Missions/Active/USS-TJR-MSN-0321-LCARS-Portal-Rationalisation-Programme.md` — which is expected to consume this capability, not evolve it.
- **Last Updated:** 2026-07-06.

---

## Asset Registry (Non-Capability Items)

**Added 2026-07-17.** The 31 Platform Capabilities above answer "what architectural capability exists." This section answers a different question: "what concrete deployable thing — a service, a script, a table, a feature — is actually running, and is it healthy right now." An item belongs here instead of above when it isn't itself a Platform Capability: a specific systemd service, a specific dead-end table, a specific regressed feature. Where an asset IS the concrete implementation of one of the 31 capabilities (e.g. `core/platform/task_engine.py` implementing Task Engine), it is not re-listed here — see that capability's own record instead. This section exists to stop exactly the pattern the 2026-07-17 audits found: real things running (or not running) in production with no living record anywhere.

Same column definitions as the Captain Dashboard above.

| Asset | Type | CMDB Status | Risk | B·D·W·L | Category | Recommendation | Note |
|---|---|---|---|---|---|---|---|
| `draft_worker` cron (content-draft pipeline) | Scheduled job | Active | Low | Y·Y·Y·Y | Operational Issue (was) | **Fixed 2026-07-17** | Crontab pointed at a deleted venv path for 10 days (~480 failed runs), silent. Repointed + heartbeat-wired same day. |
| Command Centre `ApiError` arg-order bug | Code defect | — (fixed) | — | — | Operational Issue (was) | **Fixed 2026-07-17** | Constructor arg order was backwards at ~32/34 call sites — every validation-error 400/404/502/503 path crashed instead of responding. `e6c8f8b8`. |
| verification-engine + dead-man's-switch | Platform service pair | Active | Low | Y·Y·~·Y | Operational Issue (was) | **Deployed 2026-07-17** — Fix Later to finish | Built weeks ago (`28dac4f9`,`d930b299`), never installed as a systemd unit until 2026-07-17. Only 6 of 29 registered domains actually heartbeat; 23 still silent. |
| Supabase RLS/SECURITY DEFINER gaps (views, functions, search_path, duplicate index, initplan) | DB security/perf | — (fixed) | — | — | Operational Issue (was) | **Fixed 2026-07-17** | 9 SECURITY DEFINER views, 6 mutable-search-path funcs, 1 duplicate index, 4 initplan perf issues, 3 anon-exposed definer functions — all fixed and advisor-verified clear. |
| `rls_policy_always_true` (29 policies) | DB security posture | Active (unreviewed) | Medium | Y·Y·Y·Y | Architectural Debt | Fix Later | Only 2 real `auth.users` rows (both the Captain) so no live multi-tenant hole today — but whether public signup is open (the actual risk lever) is unverified with tools available. Check that first, then decide whether 29 policies need tightening. |
| `vector` extension installed in `public` schema | DB hygiene | Active | Low | Y·Y·Y·Y | Architectural Debt | Fix Later | Moving schemas risks breaking unqualified embedding queries — needs an app-level check first, not a blind migration. |
| `auth_leaked_password_protection` disabled | DB security config | Off | Low | N/A | Operational Issue | **Fix Now** | Dashboard/Management-API toggle, zero downside, not reachable via the SQL tools used this session. |
| `advisory_sessions` public RLS + unauthenticated route | Live security exposure | — (fixed) | — | — | Operational Issue (was) | **Fixed 2026-07-18** | RLS was role=public/qual=true on SELECT+INSERT, route used a bare anon-key client with zero session check — anyone holding the (public, ships-in-bundle) anon key could read every advisory transcript and write arbitrary rows. Confirmed live-exploitable, not theoretical. Found via `WORKBENCH-REVIEW.md` (below), closed same session. `67d88b4b`. |
| `health_daily_logs` `anon_read` policy | Live security exposure | — (fixed) | — | — | Operational Issue (was) | **Fixed 2026-07-18** | Anon could read all medical daily logs directly via RLS regardless of app-level auth — found during the advisory_sessions verification, not by the source review. Dropped; `auth_read`/`auth_write` already cover the real use case. |
| `WORKBENCH-REVIEW.md` / `claude/executive-staff-model-36k492` | Merged branch | Active | — (was Medium) | Y·Y·Y·Y | Operational Issue (was) | **Merged 2026-07-18** | 25 commits, 3 real new workbenches (Knowledge, Mission, Captain's Brief) now live on main. Merged twice concurrently — this session's own merge (`beed5310`, superseded/unpushed) raced against another session's GitHub PR #103 (`073a6195`); PR #103's own conflict resolution silently reverted 2 real fixes (`_run_advisory`'s markdown formatting, health-classifier's audit-log filter) and left 3 of 4 `debrief_engine` import sites unguarded against a module confirmed not to exist (only `cmd_voice_note` had been fixed, 2026-07-12). Both restored + all 4 sites guarded in a corrective commit (`d0e6233a`) after resetting to origin's merge and diffing it against this session's own resolution to isolate exactly what changed. No live incident — `tg-xo.service`'s running process predates both merges. `self-improvement-findings/page.tsx` did NOT conflict; main's fix (`59d8e610`) survived cleanly. |
| `WORKBENCH-REVIEW.md` 5.1 items 2/4/5/6 | Security + reliability | — (fixed) | — | — | Operational Issue (was) | **Fixed 2026-07-18** | 11 routes had zero auth beyond `middleware.ts`'s page-level redirect (bypassable by direct API hit), incl. `captain-intelligence/generate` (free trigger for a real 50-260s LLM run) — new shared `requireSession()` in `lib/supabase-server.ts`, applied to all 11. `/api/advisory`'s TLS `rejectUnauthorized:false` scoped to actual localhost only (H6). 3 routes stopped masking real read failures as HTTP 200 (H4) — the one failure mode a resilience-monitoring tool can't afford — 3 client pages now render a visible error banner instead of silently trusting an error body as data. **Corrected the review's own H7 claim** that `api/wellness` is dead — it has 2 real callers (`/medical`, `/recovery-brief`); found the real bug instead (selected a nonexistent `insight_date` column, confirmed against live schema, silently 400ing every call for both callers) and fixed it. `content/pipeline`'s redundant GET removed, confirmed zero callers. `59bf3ccb`. |
| `WORKBENCH-REVIEW.md` 5.1 item 3 (C4/H2) | Security + governance | — (fixed) | — | — | Operational Issue (was) | **Fixed 2026-07-18** | C4: 4 named health writes (check-in/pulse/log-activity/readiness-session) moved off direct browser Supabase calls onto 5 new governed routes under `/api/human-systems/*`. **Found a second live RLS leak while scoping this**: `physical_readiness_checkins`/`physical_workout_sessions`/`physical_workout_exercise_logs` were role=`public` (anon-writable), same class as `advisory_sessions` — closed via migration before building the routes. H2: audit `actor`/`decided_by` bound to `session.user.email` instead of a client-supplied body field, across all 4 mission routes + knowledge-library decide. **Found a real 3+-week-silent audit-failure bug while doing this**: `mission_state_transitions` has RLS enabled with zero anon/authenticated policies — every mission route's own audit insert via the plain SSR client was silently denied (swallowed catch hid it); real table sat at 18 rows, none newer than 2026-06-27, despite real approvals/rejections since. Fixed via the existing `createSupabaseServiceRoleClient()` pattern `core-events.ts` already documents for 3 other domains. 3 more direct-write call sites (captains-log, readiness/start, readiness/history) not named by the review — RLS-correct after this pass's fix, not yet converted to governed routes, logged as Fix Later. `7862830c`. |
| `WORKBENCH-REVIEW.md` 5.2 items 7/8 (H3, H11) | Reliability + data integrity | — (fixed) | — | — | Operational Issue (was) | **Fixed 2026-07-18** | H3: all 6 mission call sites (`approve`/`reject`/`submit`/`handoff`/`[id]` GET+PATCH) switched from `.ilike('%'+id+'%').limit(1)` to `.eq('mission_id', id)` — confirmed first that every real in-app caller already passes the full canonical ID, no partial-match caller exists. H11: `intelligence-workbench`'s health-mode query was hardcoding `source_articles`/`committed_to_memory`/`committed_at`/`reviewed_at` to null/false regardless of real (confirmed live) data in those columns — now selected and passed through; `readiness_score` (`overall_note ? 1 : 0` presented as an index) removed outright rather than kept, no real formula exists to replace it; the `audit` trail both brief detail pages fetched and silently discarded since built is now rendered on both. `c915f40a`. |
| `WORKBENCH-REVIEW.md` 5.2 item 9 (H10 + timeouts/optimism) | Reliability | — (fixed/verified) | — | — | Operational Issue (was) | **Fixed 2026-07-18 (9a/9b); 9c investigated, no fix needed** | 9a/H10: `self-improvement-findings` polled every 5s regardless of tab visibility with console.error-only failures — now pauses on `document.hidden`, refreshes on return, real error banner. 9b/Medium: `api/capture/[id]`'s 2 Command-Centre proxy fetches had zero timeout — added `AbortSignal.timeout(15s)` matching `captain-brief/route.ts`'s convention, plus a 20s client-side ceiling on `CaptureRow.tsx`'s enrich trigger. `advisory/route.ts` checked and already had real timeouts on both its paths, not touched. 9c: read the actual Command Centre backend handlers (`route`/`enrich`/`promote-mission`) `CaptureRow.tsx` calls — all 3 are fully synchronous, every DB write completes before the HTTP response sends, no fire-and-forget/async-after-response pattern anywhere. The review's "eventually-failing server states still show success" concern doesn't apply to this backend's actual design — `res.ok` already means fully settled, not just accepted. Confirmed via source read, not assumed; no reconciliation mechanism built since there's nothing for it to reconcile. `709a0859`. |
| `WORKBENCH-REVIEW.md` 5.2 item 10 (H9/H12, Shell + DomainToggle) | Architectural debt | — (fixed) | — | — | Architectural Debt (was) | **Fixed 2026-07-18 — Phase A + Phase B, both complete** | **Phase A** (`2fb1b79a`): 6 `_components/Shell.tsx` forks confirmed byte-identical except `homeHref`/`homeAriaLabel`/`tagline`/default-eyebrow — consolidated into `src/components/ui/WorkbenchShell.tsx`. `riskClass`/`RiskPill` extracted to `src/components/ui/RiskPill.tsx`. Found a real live bug while merging: 3 workbenches (Mission, Comms, Self-Improvement Findings) reached into intelligence-workbench's own folder and silently inherited its `homeHref`/tagline — TJR logo on all 3 linked to the wrong workbench. Fixed. **Phase B** (`22c9d729`): 6 `role="tablist"` DomainToggle forks + comms-workbench's own `role="radiogroup"` (zero keyboard handler — real WCAG regression) + intelligence-workbench's inline no-role-at-all version, all consolidated into `src/components/ui/DomainToggle.tsx` — a real WAI-ARIA APG tablist with roving tabindex + Arrow/Home/End keyboard nav, which none of the 7 priors had. Added the legacy-LCARS-token lint guard the review asked for; running it surfaced 19 real pre-existing violations in 3 knowledge-workbench files — fixed all 19 (semantic mapping to `wb-ok`/`wb-crit`/`wb-warn`/`wb-sage`) rather than ship a guard that breaks the next person's build. All 31 consumer files across both phases verified via `tsc`+`eslint`+full `next build`. |
| `WORKBENCH-REVIEW.md` 5.2 item 11 (test coverage) | Reliability / regression protection | — (fixed) | — | — | Architectural Debt (was) | **Fixed 2026-07-18 — closes the roadmap** | Route tests (401 gate, actor bound to `session.user.email` not the request body, success/error paths) for the 4 representative governed-write patterns from items 3/7/8: `missions/[id]/approve`, `human-systems/check-in`, `advisory-sessions` (GET+POST), `knowledge-library/documents/[id]/decide` — no prior test in this repo imported an API `route.ts` module directly, this establishes the pattern (`vi.mock('@/lib/supabase-server', ...)`). Component coverage for item 10's `WorkbenchShell`/`DomainToggle`: axe a11y checks added to the existing `a11y.test.tsx` harness, plus a dedicated `DomainToggle.test.tsx` exercising the real roving-tabindex + Arrow/Home/End keyboard behaviour — axe alone verifies markup shape, not that the keys actually move focus/selection, and none of the 7 prior forks had this behaviour to begin with. 393/393 tests pass, `tsc`+`next build` clean. `402364af`. **Closes WORKBENCH-REVIEW.md's entire 5.1 Immediate + 5.2 Near-term roadmap.** |
| `brief_qa_agent.py` (automated `data_qa` gate for Intelligence Workbench) | Feature | **Built, not deployed** | Low | Y·Y·N·N | Operational Issue | **Fix Now — decide on `--live` + cron** | Reframed from `INTELLIGENCE-WORKBENCH-AGENT-IMPLEMENTATION.md` (`claude/executive-staff-model-36k492`), which proposed a parallel scoring table + a new Telegram bot + a checklist against fields that don't exist on `intelligence_briefs` (`status='pending_qc'`, `summary`, `priorities`, `domain_signals`, `insights`) and a migration referencing a nonexistent `id` column — none of it would have run against real data. Rebuilt to compose with `intelligence/workflow/service.py`'s existing `set_qa_gate('data_qa', ...)`, the one gate already documented as automatable — no new table, no new bot. Live dry-run (read-only) against the real 24 `IN_REVIEW` briefs surfaced 12 missing `executive_snapshot`/`bottom_line` outright (real data-quality gap) and, before shipping, a real bug in the agent itself (still averaging in a broken sub-check from reused prior-art logic) — fixed + regression-tested. `e1f9d485`, attested. CLI defaults to `--dry-run`; nothing mutates live `approval_status` until `--live` is explicitly passed and no cron is installed — both are separate decisions, not done by default. |
| Concurrent-session push races on `main` | Governance process | Active (recurring) | Medium | N/A | Architectural Debt | Fix Later | Confirmed twice tonight — a `git push` rejected mid-session because another Claude Code session merged the same branch via GitHub PR seconds earlier. No branch-protection/PR-required policy exists on `main`; multiple sessions push directly and concurrently by design (per this platform's own direct-to-main delivery pattern). Works today because each conflict happens to be caught and reconciled by whichever session notices — not because it can't silently lose a fix. Worth a real decision (PR-required + review, or an explicit "check origin before merge-heavy work" convention) before the next race is missed rather than caught. |
| context-service / self-improvement-dashboard on Flask dev server | Infra hygiene | Active | Low | Y·Y·Y·Y | Architectural Debt | Fix Later | "Do not use in production" warning; firewalled (UFW) + fail-closed auth today, so not currently exploitable. |
| Mission-ID minting drift (`id_registry.py` counter) | Governance process | Active (drifted) | Low | Y·Y·Y·~ | Architectural Debt | Fix Later — 4th recurrence, fix the root cause | Counter at MSN-339, real usage at MSN-347. No enforcement against hand-picked numbers; every prior fix has been a manual reconciliation, not a structural fix. |
| **XO Voice Daily Debrief** (`debrief_engine.py`) | Feature | **Broken** | Medium | Y(was)·Y(was)·N·N | Operational Issue | **Fix Now — triage** | Never committed to git; source file no longer exists anywhere in the working tree, only a stale `.pyc` survives. Live `app.py` catches the `ImportError` and silently degrades to plain quick-capture. `debrief_sessions` has exactly 1 row, dated the day it was built (2026-07-07). Triage first (is the code recoverable from a transcript/backup?) before deciding Fix vs. Retire. |
| `temporal_entities`/`facts`/`episodes` (ghost tables) | Orphaned data | Dormant | Low (access tightened 2026-07-17) | Data-only·N·N·Y(data) | Historical Artefact | Fix Later — run the never-executed MSN-0210D provenance investigation once, then Retire or formally adopt | 88/118/78 real rows, zero owning application code anywhere, provenance unknown (contradicts ADR-022's "planned only" claim). Anon RPC access to the associated search functions revoked 2026-07-17; the orphan status itself is unresolved. |
| `content_signals` as an active producer | Dead-end pipeline | Active (but feeds nothing) | Low | Y·Y·N·Y | Historical Artefact | Retire (as a producer; keep the scoring logic) | Real working code, scores real data, but nothing downstream ever converts a row into a content opportunity — the real pipeline (`opportunities.py`) doesn't know it exists. Recommended for retirement since MSN-0210C (2026-07-05), not yet executed. |
| Officer 8-step daily cycle (`daily_operations_cycle.py`) | Dead code | Dormant | Low | Y·N·N·N | Historical Artefact | Retire (or formally adopt if a real owner is chartered) | Fully built, zero live callers anywhere in the repo, confirmed twice (MSN-0210L, and again by this pass's inference — nothing new calls it). |
| `LearningLoopBridge` / `outcome_capture_service.py` path | Dead code | Dormant | Low | Y·N·N·N | Historical Artefact | Retire | Superseded by the fixed `research_learning_loop.py`/`comms_learning_loop.py` path (the live half of the Confidence capability). This original path was never revived and has zero callers, confirmed 2026-07-17. |
| 4 parallel ADR registries | Governance duplication | Active (all 4) | Low | Y·Y·~·Y | Architectural Debt | Fix Later | One (`core/governance/architecture-decision-records/`) is the real canonical one per its own internal mapping doc; the other 3 have no deprecation notice pointing to it. |
| D-prefix collision (`governance/directives/` vs `governance/decisions/`) | Governance duplication | Active (both) | Low | Y·Y·Y·Y | Architectural Debt | Fix Later | Two unrelated registries share the same `D-0NN` identifier prefix. |

## Prioritised Remediation Roadmap

Every Fix Now / Fix Later / Replace / Retire item from both registries above, grouped by urgency. This is the action list; the tables above are the record.

### Fix Now (do next — small blast radius, or already causing real harm)
1. **Priority & Opportunity Engine weighting** — hardcoded placeholder feeding the Decisions Inbox's "ranked" presentation. Named by 23/23 independent reviewers (MSN-0346) as the single highest-leverage fix on the platform. Everything downstream of "is this ranking trustworthy" depends on this.
2. **Attention Engine — prove `interrupt_now`** — never fired in production, tied directly to a real near-miss (MSN-0338's Telstra outage). Build the drill/certification mechanism MSN-0347 already specified rather than waiting for an organic firing that may never come.
3. **XO Voice Daily Debrief — triage** — silently regressed to fully dead. Cheap first step (check recoverability), then either rebuild-and-commit-this-time or formally retire it — the current state (silent degrade, nobody notified) is the worst of both options.
4. **Knowledge's PATCH authorization gap** — any authenticated caller can reclassify/archive any document. Disclosed by MSN-0333, not fixed. Small, contained fix.
5. **Wellness dispatcher's missing live trigger** — an escalation-detection system with no owner and no schedule calling it. Health/wellness-adjacent, worth treating as more urgent than its "Medium" risk rating alone suggests.
6. **`auth_leaked_password_protection`** — one dashboard toggle, zero downside.
7. ~~**`advisory_sessions` public RLS + unauthenticated route**~~ **FIXED 2026-07-18** — see Asset Registry.
8. ~~**`health_daily_logs` `anon_read` policy**~~ **FIXED 2026-07-18** — see Asset Registry.

### Fix Later (real, scoped, not urgent)
Convert the 3 remaining direct-browser-write call sites (`captains-log`, `readiness/start`, `readiness/history`) to governed routes matching the pattern `/api/human-systems/*` now establishes — RLS-correct after 2026-07-18's fix, just not yet consistent with the rest of the workbench. Also audit `processing_documents`/`processing_chunks`' `anon_read` policies (found live 2026-07-18 while scoping item 3, not in this pass's fix scope — the knowledge-review pipeline is readable by anon before Captain review). · Decide a real policy for concurrent-session push races on `main` (PR-required + review, or an explicit convention) before the next race is missed rather than caught — see Asset Registry. · `registry_staleness_check.py` (run 2026-07-17 as part of this pass) found **12 pre-existing stale records** — implementation files with commits more recent than their record's own Last Updated date, none touched by this pass: Audit (`authority_validator.py`), Notification, Model Router, Unified Memory, Number One Execution Bridge, Content Intelligence *(fixed by this pass, see its record)*, Engineering Runtime (2 files), Captain Experience Component Library (4 files). Not investigated this session — each needs its own check for whether the underlying commit was material before the record can be trusted current. · Wire the remaining 23 silent `domain_heartbeats` domains · re-verify Task Engine's and Confidence's live-fire (both show 0 rows despite "live-verified"/"activated" framing) · ADR-registry consolidation (4→1) · D-prefix collision rename · Scheduling consolidation (5 apscheduler instances, real double-fire risk) · Search consolidation (6 implementations) · `command_bus.py`→`notification_service.py` cutover · Content Intelligence's 2 disjoint drafting pipelines · Health Intelligence ownership untangling · Engineering Runtime's `batch_coding.py` durable-state gap · Captain Experience Component Library's consolidated remediation list (WCAG contrast, brand-colour collision, nav-label drift) · 29 `rls_policy_always_true` policies (check signup-config first) · `vector` extension schema move · mission-ID minting's structural fix (collision-check against a live scan instead of a standalone counter) · `temporal_*` ghost-tables provenance investigation (MSN-0210D, never run) · Configuration capability adoption (or retire it if still zero adopters at the next annual review) · 3 Captain Brief pipelines' formal Convergence Review (MSN-0342/0343, recommended, not run).

### Replace
None identified this pass — no capability was found where the right call is "throw out and rebuild" rather than fix, retire, or leave alone.

### Retire
`content_signals` as an active producer (keep the scoring logic, fold into Event Bus) · officer 8-step `daily_operations_cycle.py` (zero live callers, ever) · `LearningLoopBridge`/`outcome_capture_service.py` path (superseded by the live Confidence chain) · `temporal_*` ghost tables (pending the provenance investigation above — retire if unrecoverable, adopt if not).

### Leave As-Is
Model Router, Event Bus, Operational Resilience Intelligence, Number One Execution Bridge, Runtime Render Validation Framework, Captain Intelligence Core (correctly gated by the Operational Observation Period), the 3 Design-Stage-only capabilities (Secure Execution Policy, Data Classification & Model Routing, Execution Runtime Registry — each correctly waiting on a real prerequisite, not neglected), Relationship Model and Capture Promotion Bridge (both correctly extending opportunistically rather than needing a push).

---

## Engineering Governance

This document is a mandatory engineering release gate, not guidance. **No engineering mission may be considered complete until the Platform Registry has been reviewed and updated where required.**

Every engineering mission must:

1. Review the Platform Registry.
2. Determine whether the mission changes any Platform Capability.
3. Update affected capability records.
4. Record maturity changes.
5. Record confidence changes.
6. Record new consumers.
7. Record capability relationship changes.
8. Record technical debt removed or introduced.
9. Record future evolution.
10. Run `python3 tools/registry_sync_check.py` and confirm it passes (MSN-0308) — a Registry edit is not complete until the Captain Dashboard and every detailed record it touched agree with each other.
11. Run `python3 tools/registry_staleness_check.py` (MSN-0343) — confirms no capability's own implementation files have a more recent commit than its record's Last Updated date. This catches a class of drift item 10 cannot: a record that's internally consistent (dashboard matches detail) but stale against what the code actually does now.

**Engineering Principle (MSN-0308, Captain-affirmed):** Verification takes precedence over assumptions. Removing unnecessary work is as valuable as writing correct code. MSN-0308's Confidence Pilot workstream found a prior mission's own claim ("ORI's confidence pass-through is broken") was itself wrong — the code was already correct; the real cause was environmental (no collection cycle had completed). No code was written to "fix" something that wasn't broken. That is a successful engineering outcome, not a missed task.

**Extension (MSN-0316/0317, Captain-affirmed 2026-07-06):** the same principle applies to *environmental* claims, not just code claims. "No headless browser available in this sandbox" was disclosed as an unresolved limitation across all 5 MSN-0315 review rounds — never once tested, just repeated. MSN-0316's feasibility spike retired it with a single direct experiment. **Engineering assumptions about platform constraints should be treated as hypotheses until verified through experimentation**, not accepted as fact by repetition. A disclosed environment limitation carried across multiple missions without a documented verification attempt is itself a signal worth spiking, not a fact to keep working around.

**Validation Layers Are Complementary (MSN-0317, Captain-affirmed 2026-07-06):** the Runtime Render Validation Framework's pilot found genuine production accessibility defects (critical unlabeled-`<select>` violations, structural landmark issues) that neither `tools/css_token_guard.py` nor 5 rounds of manual Design Officer / Visual Design Officer review had caught — not because those layers failed, but because each validation layer can only structurally detect certain classes of defect. Each layer in the sequence below exists because the layer before it has a real, principled coverage boundary, not because it's more thorough in general. Future capability-investment decisions should identify *which* class of defect a proposed layer closes, not treat "more validation" as generically better.

**Standard Engineering Validation Sequence (adopted 2026-07-06, applies to all future Captain-facing applications):**

```
Static Guards
      ↓
Unit / Integration Tests
      ↓
Runtime Render Validation
      ↓
Design Officer Review
      ↓
Visual Design Officer Review
      ↓
Commissioning
```

Each stage is complementary, not redundant — no stage replaces the one before or after it. Static Guards (e.g. `tools/css_token_guard.py`) catch literal source-text defects cheaply, before a build even happens. Unit/Integration Tests catch logical/type errors. Runtime Render Validation (this capability) catches what only exists after a browser renders — the exact gap evidenced above. Design Officer Review then Visual Design Officer Review (now explicitly sequential, not combined) apply human judgment neither preceding stage can replace. Commissioning is the gate all of the above feed into, not a stage of its own.

**Recommended Metric (MSN-0317 follow-up, for the engineering roadmap, not yet built):** a **Defect Detection Effectiveness** metric — classify every found defect by which stage of the sequence above first detected it (Static Guard / Unit-Integration Test / Runtime Validation / Design Officer / Visual Design Officer / Captain Review / Production). Over time this turns "which validation layers are worth investing in further" from anecdote into an evidence-based decision — e.g. MSN-0317's pilot alone would classify as: 2 critical `select-name` + structural landmark findings → Runtime Validation (first detection, 5 prior manual rounds missed them); the `statusBadge()` JS-concatenation bug → also Runtime Validation, independently corroborated by both officers in MSN-0315's 5th round when given the same evidence. No implementation of this metric exists yet — recorded here as a roadmap recommendation only.

**A Clean Scan Means "Clean For What Was Exercised" (MSN-0318, Captain-affirmed 2026-07-06):** MSN-0318 remediated all 7 defects MSN-0317's pilot disclosed, verified by a 26→0 accessibility-violation Runtime Validation result — and the Visual Design Officer's independent review of that same remediation still found 2 more live instances of the identical defect class (`loadCommandBlockers()`, `renderORBrief()`), invisible to every one of the pilot's 7 scenarios because both only render on specific live-API data states no scenario drives the page into. Both facts are true at once: the remediation was accurately verified for its disclosed scope, and the underlying defect class was not eradicated file-wide. **A clean runtime scan means "clean for the scenarios exercised," not "globally clean across every possible data state."** Every future mission citing a Runtime Render Validation result should state the scan's actual coverage boundary (which scenarios, which data states) rather than let a violation count of zero imply more than it verified.

**Verify Independent Review Findings Against Live Code Before Treating Them as Fact (MSN-0319, Captain-affirmed 2026-07-06):** MSN-0319 Phase 2A's own verification of the Visual Design Officer's MSN-0318 finding found half of it — `loadCommandBlockers()` — was dead code, never called, while the other half — `renderORBrief()` — was confirmed real. **Independent review findings are valuable inputs, but they should always be verified against the current implementation before becoming engineering assumptions**, particularly where legacy compatibility code remains present (here, a function whose own guard-flag comment said "kept for compatibility" was still assumed live until someone actually grepped for its callers). This is not a criticism of the reviewing officer — it is why a Chief Engineer's own independent re-verification step exists at all in this platform's review process, and why it caught something a design-level review reasonably would not.

**Wave/Stage Authorization Must Live in the Shared Artefact, Not a Private Transcript (MSN-0327, Captain-affirmed 2026-07-06):** two engineering sessions ran concurrently on this repository, coordinating only through shared git commits and mission files. One session recorded a "governance deviation" — that MSN-0326 Wave 2 began without explicit Captain authorization — based on the git-commit timestamps alone, since it had no visibility into the *other* session's transcript, where that authorization had in fact already been given. The record was corrected (process-visibility issue, not an unauthorized action), but the underlying platform lesson stands independent of this one incident: **any wave/stage authorization for a multi-session or multi-agent programme must be written into the shared mission file itself at the moment it happens** — "authorized: yes/no, by whom, when" — not left implicit in whichever session's conversation happened to receive it. A concurrent session judging solely from commit proximity will reach a reasonable but wrong conclusion every time this isn't done.

**Disclose Real Limitations Rather Than Engineer Around Them or Manufacture Test Cases (MSN-0326, Captain-affirmed 2026-07-06):** across all 5 waves of the Authority & Governance Convergence implementation, every real limitation found was named on the record rather than quietly worked around: Wave 3/4 disclosed that both real (dormant) authority call sites have their own broad exception handlers that would silently swallow the new `ManifestGapError`/blocking `AuthorityError`; Wave 4 disclosed that its entire blocking mechanism has never been exercised by any real manifest (validated via isolated logic tests instead, stated plainly as such); Wave 5 was explicitly asked to check whether migrating a legacy authority map would finally create that missing real test case, found it would not (by the chosen migration design), and disclosed that trade-off rather than either hiding it or artificially engineering an overlap into the manifest schema just to exercise an otherwise-unproven mechanism. **A validated mechanism with a disclosed gap is more valuable than an apparently-fully-tested one whose test case was manufactured to close the gap on paper.**

No Platform Capability should evolve without this document being updated.

## Mission Close-out Requirement

Before any mission can be considered complete:

- [ ] Platform Registry reviewed.
- [ ] Platform Registry updated if required.
- [ ] Maturity changes recorded.
- [ ] Confidence changes recorded.
- [ ] New capabilities added.
- [ ] Deprecated capabilities marked.
- [ ] Capability relationships updated.
- [ ] Platform ownership verified.
- [ ] `tools/registry_sync_check.py` run and passing (MSN-0308 — standard validation step, not optional).
- [ ] `tools/registry_staleness_check.py` run and any capability this mission touched is either updated or explicitly confirmed unchanged (MSN-0343 — catches drift `registry_sync_check.py` can't: a record internally consistent but stale against git history, the way Attention Engine and Continuous Captain Brief Orchestration drifted for 2 days after MSN-0339 before anyone noticed).

## Annual Architecture Review

Once per year (or on an equivalent milestone cadence for a platform this young), conduct a full Platform Registry review:

- remove obsolete capabilities.
- merge duplicated capabilities.
- reassess maturity for every record.
- reassess engineering confidence for every record.
- validate ownership.
- confirm roadmap alignment against the current SUOC Transition Architecture.

This keeps the registry accurate as Starship evolves, rather than accurate only at the moment each capability was added.

## Canonical Architecture Artefacts

**Three constitutional documents sit above every artefact below** — they define *why* Starship exists, *how it thinks*, and *how the Captain operates*, in that order of precedence:

- **FD-0001 — Starship North Star** (`knowledge/foundation/FD-0001-Starship-North-Star.md`) — *why* Starship exists. The Three Pillars, the Mission Test.
- **Captain Intelligence Blueprint v1.0** (`reports/USS-TJR-MSN-0304-Captain-Intelligence-Blueprint-v1.0.md`) — *how Starship thinks*. The Cognitive Model, Attention Engine, Priority & Opportunity Engine.
- **Captain Operating Model** (`reports/USS-TJR-MSN-0322-Captain-Operating-Model.md`, promoted 2026-07-06, MSN-0322) — *how the Captain operates*. Responsibilities by cadence, the decision-ownership framework, the attention management model, department interaction — the day-to-day expression of the two documents above.

The four artefacts below define *how the platform is built* and *what it's building* — they do not restate the constitutional documents' purpose, and the constitutional documents do not restate their technical detail:

- **Architectural Decision Records** — why decisions were made (`core/governance/architecture-decision-records/`, `knowledge/Architectural-Decisions.md`).
- **SUOC Transition Architecture** — where the platform is going (`reports/USS-TJR-MSN-0210-SUOC-Transition-Architecture.md`).
- **SUOC Platform Registry** — what currently exists (this document).
- **Mission Registry** — what engineering is changing, mission by mission.

Every engineer should begin with the three constitutional documents for purpose/thinking/operation, then these four documents for architecture, before reviewing historical mission reports. **Constitutional check for future missions:** per the Captain Operating Model's own Operating Model Test (mirroring FD-0001's Mission Test) — which section of the Captain Operating Model does this mission strengthen? If it cannot answer that, its purpose should be challenged before engineering begins.

## Long-term Objective

This document is the authoritative engineering inventory for SUOC. Rather than reading dozens of missions to understand Starship's architecture, an engineer should be able to open this document and immediately understand: what capabilities exist, their maturity, their engineering confidence, their ownership, their dependencies and relationships, and what is planned next. It should evolve continuously as the platform matures, not be regenerated from scratch each time.
