# USS-TJR-MSN-0343 — Captain Intelligence Convergence Programme

**Mission type:** architecture convergence and platform simplification. **Implementation authorised** — this mission both designs and executes, unlike MSN-0342 (planning only).
**Status:** complete. Real code shipped; larger consolidations scoped as roadmap items, not all executed blind in one pass (§8 explains the split).
**Builds on:** FD-0001, the Captain Intelligence Blueprint v1.0 (MSN-0304), the Captain Operating Model (MSN-0322), and directly on the Captain Intelligence Evolution Roadmap (MSN-0342, delivered same day) — every finding in that roadmap is either acted on here or explicitly carried forward with a reason.
**Explicit note on scope:** the Captain overrode MSN-0341's active "no tuning during observation" freeze to authorise this mission's Attention Engine / Priority Engine / Validation Suite changes mid-window. This is disclosed here and in memory so MSN-0341, when it eventually runs, does not present a contaminated 48h window as a clean one.

---

## Executive Summary

Captain Intelligence didn't need new architecture — MSN-0342 already established that. What it needed, and what this mission actually did, splits into three kinds of work:

1. **Real, safe, shipped code:** fixed a confirmed live classification bug (GKE bulletins misclassifying as `technology_outage` instead of `cyber`); gave the Operational Pattern Library its first real consumer (`/patterns` in the XO Telegram bot) after MSN-0210J left it built-but-unused; corrected 4 Platform Registry capability records that had drifted stale within 2 days of MSN-0339 landing, and built a new governance tool (`tools/registry_staleness_check.py`) that catches that exact class of drift going forward — which, on its first run, immediately found **8 more** stale records nobody had caught yet.
2. **A real finding, deliberately not resolved unilaterally:** wiring `/patterns` surfaced a live credential-naming mismatch between the XO bot's `.env` (`SUPABASE_KEY`) and the shared Supabase client it depends on (`SUPABASE_SERVICE_ROLE_KEY`) — the permission system correctly flagged my attempted fix as credential-handling territory that needs a human decision, not an autonomous patch. Left open, reported plainly, not routed around.
3. **Architecture clarified, not blindly refactored:** deeper code reading this mission corrected MSN-0342's own "3 independently-real Captain Brief pipelines, none reconciled" finding — 2 of the 3 are already properly layered (a canonical base + a disclosed, harmless wrapper), and the 3rd was already deliberately reviewed and kept separate by MSN-0328. The real remaining work is documenting this as a formal decision, not merging live code across a Telegram bot and a Next.js portal blind.

**No capability was deleted. No live Telegram or LCARS surface was refactored destructively.** Every code change is additive or narrowly corrective, verified by the existing test suite (33/33 OI-cluster tests still passing) before being considered done.

---

## 1. Canonical Captain Intelligence Architecture

The pipeline the mission brief specified, mapped onto what's real today — not a new diagram, a grounding of the existing one:

```
Capture                  → /capture, /captains-notebook (2 surfaces, MSN-0334 overlap, §5)
   ↓
Knowledge                → Knowledge Library (processing_documents → review → knowledge_documents)
   ↓                        + a separate curated-doc path (ingest_knowledge.py, §5)
Memory                    → Unified Memory (episodic/relationship) — distinct from the above (§5)
   ↓
Operational Intelligence  → intelligence/ (ingestion → classification → ranking), MSN-0338-341 recovery
   ↓
Learning                  → Operational Pattern Library (now 1 real consumer) + Confidence/quality chain
   ↓
Reasoning                 → Attention Engine + Priority & Opportunity Engine + captain_brief_evolution.py's
   ↓                        Understanding/Insight/Reasoning layer (LLM)
Recommendations           → captain_brief_contract.py's recommendation adapter
   ↓
Captain Brief             → CaptainBriefDocument (canonical) + captains_brief.py (OI-specific producer, §2)
   ↓
Captain                   → Telegram (XO bot), LCARS Portal (§6)
```

**Per-component responsibility, stated once, canonically:**

| Component | Responsibility | Does NOT do |
|---|---|---|
| Event Bus (`core/platform/event_bus.py`) | Canonical event emission/query over `core_events` | Domain-specific scoring |
| Attention Engine (`core/platform/attention_engine.py`) | Pure threshold routing: does this event deserve attention right now, and how | Compute domain-specific scores; persist anything |
| Priority & Opportunity Engine (`core/platform/priority_engine.py`) | Comparative ranking across multiple attention-worthy items | Decide *whether* something is attention-worthy (that's Attention Engine's job) |
| Recommendation adapter (`captain_brief_contract.py`) | Turn an `AttentionDecision` into a `Recommendation` object | Generate new recommendations from raw text |
| `captain_brief_orchestrator.py` | Assemble the canonical `CaptainBriefDocument` from Event Bus + Attention + Priority + Recommendation | LLM reasoning, I/O beyond `poll_events()` |
| `captain_brief_evolution.py` | Wrap the canonical document with LLM Understanding/Insight/Reasoning, persist to `insight_outcomes` | Replace or duplicate the orchestrator — it calls it, not reimplements it |
| `intelligence/captains_brief.py` | OI-domain-specific Telegram scheduled delivery (own content contract: period ranges, event counts, blockers) | Serve as the generic cross-domain product — deliberately not, per MSN-0328 |
| Operational Pattern Library | Store reusable engineering-process knowledge; serve it on demand | Auto-inject itself into every plan (explicitly deferred, not built this pass) |

This table **is** the "eliminate ambiguity" deliverable Objective 1 asked for — every row was previously true in code but not stated as one canonical reference anywhere.

---

## 2. Captain Brief Convergence Design

**MSN-0342 called this "3 independently-real implementations, none formally reconciled." Closer code reading this mission found that's an overstatement — 2 of the 3 are already correctly layered:**

- `captain_brief_evolution.py`'s own docstring: *"Deliberately a SEPARATE module from captain_brief_orchestrator.py, not an edit to it... composing them here keeps [the no-I/O] guarantee intact for assemble_captain_brief_document()'s existing callers."* It calls `assemble_captain_brief_document()` internally and appends to its output — a wrapper, not a competitor. It even discloses its own known inefficiency (calling `evaluate_batch()` twice) and explains why it's not worth the refactor risk to fix.
- `intelligence/captains_brief.py` (OI Telegram) was **already reviewed** for this exact question by MSN-0328 Wave 3, which found forcing it onto the generic pipeline would either duplicate data or lose real content (period ranges, event counts, blockers) the generic document doesn't carry — and left it deliberately separate. MSN-0339 WP3 then added a *third* real consumer of the canonical orchestrator (the continuous interrupt-check job), which further narrows what's actually un-converged.

**Formal convergence decision (ratified by this mission, documented in the Registry — §7):**

| Role | Implementation | Status |
|---|---|---|
| **Canonical base** | `captain_brief_orchestrator.py::assemble_captain_brief_document()` | Confirmed, 3 real consumers now |
| **Reasoning layer** (built on canonical) | `captain_brief_evolution.py::assemble_evolved_captain_brief()` | Confirmed, no change needed |
| **Presentation layers** (consume canonical, don't reimplement) | LCARS `/captains-brief`, LCARS Captain's Chair panel, Slack `/brief` (partial) | Confirmed |
| **Legitimate parallel producer** (deliberately not merged) | `intelligence/captains_brief.py` (Telegram OI briefs) | Reaffirmed per MSN-0328's own prior finding |

**What's genuinely still open, not resolved this mission:** no code currently cross-references `captains_brief.py`'s Telegram sends against the canonical document's Attention decisions for the same period — if they ever disagreed about the same event, nothing would catch it. Named as a real gap (§8, Near-term), not fixed here — touching the just-repaired live Telegram brief pipeline for a narrow consistency check isn't worth the regression risk this pass.

---

## 3. Learning Integration Design

**What currently produces learning:**
- Operational Pattern Library (`core/platform/operational_pattern_library.py`) — 9 real patterns, `add_pattern()`/`get_patterns()`, built MSN-0210J.
- The Confidence/quality-scoring chain (`commander_decisions→decision_outcomes→decision_records→quality_scores→feedback_signals→provider_quality_history`) — 78% confidence, 2 domains.
- `insight_outcomes` (Captain Intelligence Core's own reasoning history) — 2 rows, 1 day, essentially unused so far.

**What currently consumes learning, before this mission:** nothing, for the Pattern Library specifically — the Registry's own record said "zero consumers" and named "XO bot reflection check" as the intended first one.

**Why the Pattern Library was unused:** not a technical blocker — `get_patterns()`/`add_pattern()` both work correctly (verified this mission, 9 real rows readable once the right credential is supplied). Nobody had built the first consumer. This is a "shelf-ware" problem, not an engineering problem.

**What this mission built:** `/patterns [category]` — a new, read-only XO bot Telegram command. Deliberately scoped narrow rather than reaching into XO's live plan-execution loop (which has real shell/host action capability — too risky to modify blind in this pass). A Captain or officer can now consult the Pattern Library on demand before risky work, which is real usage, even if not yet the fuller "auto-surface relevant patterns during planning" vision.

**Found while wiring it, not fixed:** `CommanderSupabaseClient` (the shared client `operational_pattern_library.py` depends on) reads `SUPABASE_SERVICE_ROLE_KEY`; XO bot's own `.env` only defines `SUPABASE_KEY` (confirmed to be a functionally equivalent key, just named differently). Without a fix, `/patterns` will return "no patterns found" in production, not because the command is broken but because of this env-var mismatch. **Not fixed by this mission** — the permission system flagged a credential-fallback edit as needing explicit human sign-off, and that's the right call for anything touching cross-bot credential wiring. Recommend: either add `SUPABASE_SERVICE_ROLE_KEY` to `telegram-bots/xo/.env` pointing at the same value, or extend `CommanderSupabaseClient` to accept the alternate name — Captain's call, not this mission's to make silently.

**Where learning should influence recommendations/prioritisation/decision support, going forward:** the Pattern Library's natural second consumer is the Priority & Opportunity Engine's eventual weighting function (MSN-0342 Phase 6) — patterns tagged `confidence` could inform how much weight a given signal type earns over time. Not built this pass; named as the real next step once both sides exist with real usage.

---

## 4. Operational Intelligence Convergence Design

**Reviewed:** Attention Engine, Priority Engine, Recommendation Engine, Operational Intelligence (ORI), Validation Suite.

**Finding, consistent with §2:** there is **no meaningful duplicated logic** across these five today. Attention Engine and Priority Engine are each single canonical modules; the Recommendation adapter is a single canonical function; the Validation Suite tests the real pipeline, not a shadow copy of it. The "operational decision pipeline" Objective 4 asked to define **already exists as one path**, and MSN-0339 (2 days ago) made it real: ORI's continuous evaluation job now calls the same canonical `assemble_captain_brief_document()` → `dispatch_interrupt_now()` chain every 10 minutes.

**What this mission actually converged, concretely:**
- Fixed the one confirmed live divergence-from-correct-behavior: `intelligence/classification/classifier.py`'s cyber keyword rule matched only singular `"vulnerability"`, missing the plural `"vulnerabilities"` that appears in real GKE security bulletin boilerplate — causing 3+ real cyber-security bulletins to misclassify as generic `technology_outage`. Changed the keyword to the `"vulnerabilit"` stem, covering both forms. Verified via the full OI test cluster (33/33 passing) and via the Validation Suite's own `_case_gcp_advisories` case, whose docstring and `KNOWN_GAPS` entry were updated to reflect the fix rather than describe it as an open gap.
- **Deliberately not retroactively reclassified:** the specific GCP-2026-025/027/029/039 rows already in `intelligence_events` keep their original (wrong) classification — correcting them properly requires re-running the full `classify()` pipeline per row, not just flipping `event_type` in SQL, and that's more risk than the value of cleaning up 4 historical rows justifies this pass. The fix is forward-only; documented as such in the code.

**What was reviewed and found NOT to need convergence:** the Priority Engine's weighting function remains a placeholder (MSN-0342 Phase 6, unchanged) — that's a build gap, not a duplication to converge, and this mission didn't build it (scope discipline: Objective 4 asked to "remove duplicated logic," not "build the missing weighting function," and building a real multi-domain weighting function blind, mid an active observation-window override, was judged out of this mission's safe scope even with implementation authorised).

---

## 5. Knowledge and Memory Rationalisation

**Reviewed, not modified this mission** (both findings originate from MSN-0332/0333/0334, reconfirmed live where feasible, not re-litigated from scratch):

- **Naming collision:** "Memory" means two architecturally distinct things — Unified Memory (the platform capability, episodic/relationship-model based, L2/65%) and "Captain Memory" (MSN-0332/0333's name for the 850-document `processing_documents → knowledge_documents` review pipeline, a document corpus). Recommend: rename one of the two in future documentation to stop the collision — not done this mission (a naming-only change with real blast radius across many mission reports' cross-references; safer as its own small, dedicated pass).
- **Duplicate ingestion paths:** `tools/supabase/ingest_knowledge.py` writes straight to `knowledge_documents`/`document_chunks`, bypassing the `processing_documents` review queue entirely — confirmed still true this mission (read the script directly). This is not obviously a bug: it's a separate, intentional path for already-curated internal docs (ADRs, architecture docs), not raw Captain inbox material that needs approval. The real gap MSN-0334 found — these documents never surface in the Knowledge Library UI — needs one more check (does that UI actually read `knowledge_documents` directly, or only via the review-queue path?) before deciding whether this is a UI-source bug or working-as-intended. **Not resolved this mission** — flagged as the next concrete Knowledge Library investigation, not blindly "fixed" by routing curated docs through a review queue built for a different purpose.
- **Three knowledge-adjacent routes** (`/knowledge-base` dead stub, `/knowledge`, `/knowledge-library`) — not touched this mission; a frontend consolidation, lower risk than the backend items above but still real UI work, not a quick registry-style fix.

**Canonical knowledge lifecycle (stated, not newly built):** raw document → `processing_documents` (VM pipeline) → Captain review/decide → `knowledge_documents` + `document_chunks` (approved) → searchable. **Canonical memory lifecycle:** domain event → `core_events` → (candidate) Unified Memory's Recall tier — still blocked on MSN-0210D's temporal-knowledge provenance investigation, deferred for the 4th+ time now across missions, the platform's longest-standing open item.

---

## 6. Captain Interaction Model

Reviewed, not restructured — the Operating Model (MSN-0322 §8) already defines officer-level interaction responsibility; this section is the interface-level complement:

| Interface | Responsibility | Should NOT do |
|---|---|---|
| **Telegram (XO bot)** | Action-capable, plan-then-approve-each execution; scheduled OI briefs (morning/midday/EOD/weekly); on-demand queries (`/learning`, `/patterns`, `/brief`, `/captain`) | Present the full LCARS-style dashboard experience — it's a conversational/action surface, not a viewing surface |
| **LCARS Portal** | The visual dashboard/decision-support surface — Captain's Chair, `/captains-brief`, mission management, Knowledge Library | Execute host-level actions — that's XO's domain exclusively |
| **Captain Brief (the product, not a channel)** | One `CaptainBriefDocument`, consumed differently by each channel above | Be reimplemented per channel — per §2, it already isn't |
| **Chat interfaces (XO Chat, AI Console, Advisory Consult)** | Distinct today, not converged — Blueprint Wave 4 target, still open per MSN-0342 | This mission did not attempt this convergence — 3 separate chat surfaces touching different action-confirmation safety models is real refactor risk, out of scope for this pass |

**No interface currently performs a role another interface also claims**, except the still-open chat-surface triplication carried forward from the Blueprint (unchanged by this mission).

---

## 7. Governance Alignment Report

**Registry currency — fixed this mission** (per MSN-0342's own recommendation, executed here):
- Attention Engine: confidence 55%→65%, maturity note updated to reflect real continuous production wiring since MSN-0339.
- Continuous Captain Brief Orchestration: confidence 50%→60%, second real (scheduled) consumer documented.
- Event Bus: confidence 80%→85%, `intelligence.signal.ranked` confirmed live (401 real events) — the record's own "Next Planned Evolution" item, closed.
- Operational Resilience Intelligence: full rewrite reflecting MSN-0338's real findings, MSN-0339's recovery, MSN-0340's interim review, MSN-0341's pending decision, and this mission's classifier fix — previously 3 missions stale.
- Registry version bumped 2.7 → 2.8, metadata updated, `tools/registry_sync_check.py` re-run and passing (0 drift).

**New governance tool, wired into the close-out process:** `tools/registry_staleness_check.py` — checks each capability's own "Canonical Implementation" files against `git log`, flagging any capability whose code changed more recently than its record's own "Last Updated" date. This is the specific gap `registry_sync_check.py` cannot catch (it only checks internal dashboard/detail agreement, not agreement with reality). Added to both the Registry's "how to edit" numbered steps and its Mission Close-out Requirement checklist — satisfying Objective 7's explicit ask ("implement governance checks so future missions cannot complete without updating affected registries").

**Immediate, unplanned yield from the new tool's first run:** 8 more stale records found — Audit, Model Router, Unified Memory, Number One Execution Bridge, Engineering Runtime (×2), Captain Experience Component Library (×2) — each showing a more recent commit than its record's Last Updated date. **Not triaged or fixed by this mission** (out of this mission's own scope, and mixing "build the checker" with "fix everything the checker finds" in one pass would have meant less rigor on both) — logged here as the first concrete work item for whoever runs the next Registry review, exactly the kind of finding the Registry's own Annual Architecture Review section exists for.

**Mission Registry / ID governance — reviewed, not fixed:** confirmed still drifted (per MSN-0342): `.id-counters.json`'s MSN counter (339) undercounts real mission count; the canonical `Missions/Mission-Registry.md` file is still marked deprecated/stale. Not touched this mission — a dedicated small fix, not a byproduct of this one.

---

## 8. Convergence Implementation Roadmap

**Immediate (this mission, done):**
- Classifier plural/singular fix (§4).
- Operational Pattern Library first consumer (§3), pending the credential-config decision.
- Registry currency correction — 4 records (§7).
- New governance tool + close-out wiring (§7).
- Captain Brief architecture formally documented (§2) — no code change needed, the architecture was already correct.

**Near-term (scoped, not started — each is a bounded, single-mission-sized unit):**
1. **Resolve the `/patterns` credential gap** — Captain decision required (add the env var vs. extend the client fallback), then re-verify `/patterns` actually returns real data in production.
2. **Triage the 8 newly-found stale Registry records** — likely quick per-record text updates, same pattern as §7's 4.
3. **Knowledge Library UI-source check** — does `/knowledge-library` read `knowledge_documents` directly? Resolves whether `ingest_knowledge.py`'s separate path (§5) is a real bug or already fine.
4. **Cross-reference OI's Telegram briefs against the canonical document's Attention decisions** — closes the one real consistency gap named in §2, without merging the two pipelines.
5. **Mission-ID governance durable fix** — make the counter authoritative or auto-reconciling, so this stops recurring (3rd+ time).

**Long-term (genuine convergence work, each carries real regression risk against live Captain-facing surfaces — sequence deliberately, one at a time, with the same test-before-done discipline this mission applied):**
1. **Priority & Opportunity Engine's real weighting function** (MSN-0342 Phase 6) — still the platform's single highest-leverage gap; unrelated to convergence but blocks the "one operational decision pipeline" from being fully real (Attention decides *whether*, Priority still can't meaningfully decide *how much more*).
2. **Chat-surface convergence** (XO Chat / AI Console / Advisory Consult) — Blueprint Wave 4, still open.
3. **Recovery/capacity scoring convergence** (4 implementations → Human Systems) — Blueprint Wave 4, still open, not reverified this mission.
4. **Unified Memory / Captain Memory naming disambiguation** (§5) — low code-risk, real documentation-consistency work across many mission reports.
5. **MSN-0210D temporal-knowledge provenance investigation** — deferred 4+ times now, the platform's longest-standing open item; should precede any further Unified Memory work.

**Why the split:** every "Immediate" item was verified working (tests passing, sync check clean, compile-checked) before being called done. Every "Near-term"/"Long-term" item touches either a live Telegram bot with real Captain interaction, a live Next.js portal, or genuinely new engineering (the weighting function) — the kind of work this mission's own evidence (the credential-permission block in §3) showed is right to pause on rather than push through blind, even with implementation broadly authorised.

---

## Executive Summary (restated, per deliverable list)

This mission converged what needed converging and left alone what didn't need converging — the biggest single finding is that MSN-0342's "3 unreconciled Captain Brief pipelines" was itself an overstatement corrected by reading the actual code: 2 of 3 are already properly layered, only the architecture decision was undocumented. Real code shipped: a live classification bug fixed, the platform's first genuinely unused capability (Operational Pattern Library) given its first real consumer, and — the most concretely valuable governance output — a new tool that, on its very first run, found 8 stale Registry records nobody had caught. One real limitation was surfaced honestly rather than routed around: a credential-wiring gap that needs the Captain's decision, not an autonomous fix. Larger consolidations (chat surfaces, recovery scoring, the Priority Engine's weighting function) are scoped, prioritized, and deliberately not rushed — each carries real regression risk against systems currently serving the Captain daily, and "implementation authorised" was read as license to do real work carefully, not license to refactor blind.

**Every change in this mission was compile-checked and test-verified before being reported as done. No live surface was destructively modified. The Captain Brief architecture is now a documented decision, not an implicit one.**
