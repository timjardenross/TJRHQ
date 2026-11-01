# Open-Source Capability Search — 2026-09-12

**Method**: Full internal capability-map rebuild against `knowledge/SUOC-Platform-Registry.md` (v2.14, all 34 capabilities, reviewed same day) + 8 parallel GitHub OSINT sweeps across agent orchestration, memory/knowledge graphs, search/RAG, LLM observability & AI security, voice (TTS/STT), workflow scheduling, OSINT/scraping, autonomous coding agents, and LCARS/dashboard UI. License, activity (`pushed_at`/`updated_at`), and star counts were pulled live via the GitHub API per-item; anything not tool-verified is marked "unverified." Ranked by substance (architecture fit, license, real activity, integration effort), not stars — several 10k-80k★ repos below are explicitly flagged as likely star-inflated and excluded.

**Supersedes**: this refreshes and extends `OSS-Gap-Solutions-2026-08-23.md` and `NVIDIA-OSS-Assessment-2026-08-23.md` (three weeks old). Do not re-run those recommendations — several have already shipped (see below).

---

## 1. Executive Capability-Gap Assessment

TJR HQ ("Starship"/SUOC) is a mature, self-audited platform — 34 tracked capabilities, an internal Registry that is itself a mandatory release gate, and an active self-improvement loop. That maturity means most of the *obvious* OSS gaps from three weeks ago are already closed: **in just the last 24 hours the platform independently shipped Meilisearch hybrid search, benchmarked and rejected ParadeDB (AGPL — this research corroborates that call), evaluated and adopted Kokoro TTS over Chatterbox for narration, added ragas for RAG evaluation, and wired Presidio + NeMo Guardrails for PII/LLM01 blocking.** This search validates several of those calls independently (Kokoro's CPU-friendliness, ParadeDB's AGPL license) without having seen the internal decision docs first — a good sign the platform's own judgment is sound.

What's left breaks into four real categories:

1. **Genuinely missing capabilities** — no code exists at all. Speech-to-text (Telegram is voice-output-only), a durable/observable task-execution substrate (5 fragmented APScheduler instances with a real double-fire risk), and a working Research Orchestration pipeline (fully built, zero callers) are the three biggest. Each has a strong, low-risk OSS answer.
2. **Dormant code, not dormant capability** — Graphiti (temporal KG) and 8 of 9 Unified Memory paths have real code and zero callers. The gap is wiring, not tooling; no new OSS purchase is needed here, just finishing the integration already started.
3. **One-caller / shadow-mode tooling** — garak has never run against the live Model Router; `score_output()` has one shadow-mode caller. The fix is operational (run it), but `deepteam` and `promptfoo` extend the same investment into an actual CI gate for near-zero additional integration cost.
4. **A live internal disagreement worth surfacing**: the Registry frames the 5-way scheduler fragmentation as "internal consolidation, not an OSS gap," and an earlier OSS audit rejected Rocketry on that basis. That conclusion is *half* right — a scheduler swap doesn't help — but this research found **Procrastinate/pgqueuer are not schedulers, they're the missing Postgres-native durable-execution primitive** (real dedup via `SKIP LOCKED`, a real job ledger) that Wave-4 would otherwise hand-build. Recommend the Registry's own framing be revisited on this specific point.

No fabricated capabilities: every gap cited above is sourced directly from the Registry's own CMDB status/technical-debt fields, not inferred.

---

## 2. TJR HQ → Open-Source Capability Map

| TJR HQ Capability (Registry status) | Already-adopted OSS | Real gap? | Best external answer |
|---|---|---|---|
| Model Router (L4, 99%, Healthy) | Ollama, Gemini, Mistral, GLM/Kimi/Qwen, LiteLLM (candidate slot) | No — reference implementation | None needed |
| Observability (L2, 60%) | Arize Phoenix (live), garak (unrun), deepeval (shadow-mode) | Yes — no CI-blocking eval gate | promptfoo, deepteam |
| Data Classification & Model Routing (L2, 50%) | Presidio, NeMo Guardrails (2 of 3 clients) | Partial — coverage gap | guardrails-ai (lighter-weight extension), PyRIT |
| Search (L2, 63%, fragmented) | Meilisearch (hybrid, 1 of 6 paths), Qdrant, Supabase/pgvector | Yes — 5 of 6 implementations remain | pgvectorscale, FlashRank, bm25s/txtai |
| Unified Memory (L2, 65%, dormant) | mem0ai + Qdrant (1 of 9 paths) | Wiring gap, not tooling gap | None — finish existing integration |
| Knowledge (L3, 84%; temporal tables ghost) | Graphiti (0 callers), Docling | Wiring gap for temporal; ingestion tool already right | None new — wire Graphiti |
| Voice Synthesis (L1, 40%) | Kokoro (new default), Chatterbox (cloning), edge-tts (fallback) | Narrow — validate under load | Kokoro choice independently confirmed sound |
| *(missing entirely)* Speech-to-Text | none | **Yes — net-new capability** | whisper.cpp / faster-whisper |
| Scheduling (L2, 65%, fragmented) | APScheduler ×5 | Yes, but not as framed — see §1.4 | Procrastinate / pgqueuer |
| Research Orchestration (dormant, 0 callers) | SearXNG (recommended, unconfirmed) | Yes — pipeline never revived | GPT-Researcher |
| Engineering Runtime (`batch_coding.py` gap) | ruff/bandit/semgrep (mature, don't touch) | Yes — no autonomous fix-loop reference | mini-swe-agent, PR-Agent |
| Governance (L2, 55%, fragmented ADRs) | MADR format already adopted | Small — no browsable output | log4brains |
| Captain Experience Component Library (L2, 65%, WCAG debt) | none (hand-rolled tokens, no Radix/shadcn) | Yes — recurring defect class | axe-core/Storybook a11y, Radix, React Aria |
| CI/CD & Supply-Chain Hygiene (L3, 85%, Healthy) | ruff, bandit, semgrep, detect-secrets | Small — no dependency-CVE scan | pip-audit |
| Intelligence/OSINT ingestion | BrightData, Firecrawl (paid), changedetection.io, Uptime Kuma | Cost gap, not capability gap | crawl4ai, trafilatura, SpiderFoot |

---

## 3. Ranked Top 20 Opportunities

Scored 1–10 on Strategic value (SV) · Capability uplift (CU) · Novelty (N) · Technical fit (TF) · Maturity (M) · Integration effort (IE, 10=trivial) · **Overall priority**.

| # | Project | License | Domain | SV | CU | N | TF | M | IE | **Pri** | Action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [dequelabs/axe-core](https://github.com/dequelabs/axe-core) + Storybook a11y addon | MPL-2.0 | UI | 9 | 9 | 2 | 10 | 10 | 10 | **10** | Adopt now |
| 2 | [SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | MIT | Eng runtime | 9 | 9 | 7 | 9 | 8 | 8 | **9** | Adopt as `batch_coding.py` reference |
| 3 | [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | Apache-2.0 | Research | 9 | 9 | 6 | 8 | 8 | 6 | **9** | Adopt — revives dormant pipeline |
| 4 | [Codium-ai/pr-agent (The-PR-Agent fork)](https://github.com/The-PR-Agent/pr-agent) | Apache-2.0 | Eng runtime | 9 | 8 | 6 | 9 | 8 | 8 | **9** | Adopt — self-hosted PR review |
| 5 | [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | MIT | Observability | 9 | 8 | 6 | 8 | 9 | 7 | **9** | Adopt — CI eval/red-team gate |
| 6 | [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) | MIT | Voice | 9 | 9 | 6 | 9 | 10 | 8 | **9** | Adopt — net-new STT capability |
| 7 | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | Voice | 9 | 9 | 5 | 9 | 9 | 9 | **9** | Adopt (pip-native STT alt) |
| 8 | [radix-ui/primitives](https://github.com/radix-ui/primitives) | MIT | UI | 9 | 8 | 3 | 9 | 9 | 7 | **9** | Adopt — fixes recurring WCAG debt |
| 9 | [shadcn-ui/ui](https://github.com/shadcn-ui/ui) | MIT | UI | 9 | 8 | 4 | 9 | 9 | 8 | **9** | Adopt (copy-in, re-themed LCARS) |
| 10 | [confident-ai/deepteam](https://github.com/confident-ai/deepteam) | Apache-2.0 | Observability | 8 | 7 | 5 | 9 | 7 | 9 | **8** | Adopt — reuses existing deepeval judge |
| 11 | [thomvaill/log4brains](https://github.com/thomvaill/log4brains) | MIT | Governance | 7 | 6 | 5 | 9 | 8 | 9 | **8** | Adopt — MADR-compatible, near-zero effort |
| 12 | [janbjorge/pgqueuer](https://github.com/janbjorge/pgqueuer) | MIT | Scheduling | 7 | 7 | 6 | 9 | 5 | 8 | **7** | Adopt-for-pilot (1-2 timers) |
| 13 | [procrastinate-org/procrastinate](https://github.com/procrastinate-org/procrastinate) | MIT | Scheduling | 8 | 8 | 5 | 9 | 6 | 7 | **8** | Adopt-for-pilot, fuller feature set |
| 14 | [timescale/pgvectorscale](https://github.com/timescale/pgvectorscale) | PostgreSQL License | Search | 8 | 7 | 5 | 10 | 8 | 9 | **8** | Adopt — permissive Postgres-native pgvector boost |
| 15 | [PrithivirajDamodaran/FlashRank](https://github.com/PrithivirajDamodaran/FlashRank) | Apache-2.0 | Search | 8 | 8 | 6 | 9 | 6 | 9 | **8** | Adopt — CPU reranker for `retrieve_knowledge.py` |
| 16 | [microsoft/PyRIT](https://github.com/microsoft/PyRIT) | MIT | Security | 8 | 7 | 6 | 8 | 9 | 6 | **8** | Adopt — complements never-run garak |
| 17 | [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) | Apache-2.0 | OSINT | 8 | 7 | 5 | 9 | 8 | 7 | **8** | Adopt — cost-reducing fetch tier |
| 18 | [pypa/pip-audit](https://github.com/pypa/pip-audit) | Apache-2.0 | CI/security | 6 | 6 | 3 | 9 | 8 | 9 | **8** | Adopt — closes dependency-CVE blind spot |
| 19 | [neuml/txtai](https://github.com/neuml/txtai) | Apache-2.0 | Search | 9 | 8 | 7 | 8 | 9 | 7 | **8** | Bake-off vs. remaining 5 search implementations |
| 20 | [smicallef/spiderfoot](https://github.com/smicallef/spiderfoot) | MIT | OSINT | 8 | 7 | 5 | 8 | 8 | 5 | **7** | Adopt for entity-enrichment module coverage |

*(Full sub-lists per domain — 100+ repos evaluated total — available on request; this table is the cross-domain top-20 by overall priority.)*

---

## 4. Quick Wins (low integration effort, ship this week)

- **axe-core / `@storybook/addon-a11y`** — Storybook is already installed; this surfaces every WCAG contrast violation the design-review process keeps re-finding, continuously, for free.
- **`pip-audit`** — one more `pre-commit` hook alongside the already-blocking ruff/bandit gates; closes a real dependency-CVE blind spot the current hardening pass didn't cover.
- **`deepteam`** — same vendor/API as the already-integrated `deepeval` + `_ModelRouterJudge`; extending it is closer to a config change than a new dependency.
- **`log4brains`** — points at the existing MADR-format ADR directory and generates a browsable site; no schema changes.
- **`FlashRank`** — a single pip install, no torch dependency, drops into `retrieve_knowledge.py` as a final reranking pass.
- **`whisper.cpp` or `faster-whisper`** — a few hours to wire Telegram voice-note transcription; genuinely new capability, not just an uplift.

## 5. Big Bets (major capability expansion, real integration work)

- **Procrastinate / pgqueuer → Wave-4 scheduling consolidation.** Reframes the "not an OSS gap" conclusion: this buys the hard part (Postgres `SKIP LOCKED` dedup, a real job ledger) instead of hand-building it. Pilot on 1-2 of the worst-overlap timers (`deadmans-switch`, `mission-registry-sync`) before committing platform-wide.
- **GPT-Researcher → Research Orchestration revival.** The dormant pipeline already has a search backend candidate (SearXNG); GPT-Researcher is a working reference implementation of the exact multi-source research/synthesis loop that pipeline was built to be.
- **mini-swe-agent / PR-Agent → Engineering Runtime.** `batch_coding.py`'s zero-DB-backed-state gap and the platform's own self-improvement loop are architecturally close to what these two projects already solve; both are small enough to read end-to-end rather than adopt as black boxes.
- **Radix/shadcn + React Aria re-theme of `lcars-portal`.** The Captain Experience Component Library's WCAG failures have recurred at least 4 times across missions on a fully hand-rolled component layer — this is a structural fix, not another remediation pass.
- **Postgres-native search consolidation (pgvectorscale + FlashRank + bm25s/txtai bake-off)** for the remaining 5 of 6 fragmented search implementations, extending today's Meilisearch decision rather than replacing it.

## 6. Emerging Projects Worth Monitoring (not ready to adopt)

- **`resemble-ai/chatterbox-flash`** — Resemble AI's own CPU-speed fix for Chatterbox; too new (13★) to trust today, but the direct answer if Kokoro's narration quality ever falls short.
- **`docling-project/docling-graph`** — turns Docling output directly into a knowledge graph; could shortcut the "manual, not event-driven" KG-sync gap once it matures past 885★/Nov-2025 creation.
- **`dapr/dapr-agents`** — durable, crash-recoverable agent workflows on a self-hosted sidecar; the best available reference for the still-design-only Execution Engine Interface once Hermes evaluation concludes.
- **`a2aproject/A2A`** — Linux Foundation agent-to-agent protocol; relevant only if specialist personas ever need to be independently addressable outside the platform.
- **`codavidgarcia/nemotron-3.5-asr-streaming-onnx`** — a single-maintainer proof-of-concept claiming CPU-viable NVIDIA-lineage ASR; interesting counter-evidence to the platform's blanket GPU rejection, not production-trustworthy yet.

## 7. Investigated and Rejected

| Project | Reason |
|---|---|
| `paradedb/paradedb` (pg_search) | **AGPL-3.0** — already benchmarked and rejected internally today in favor of Meilisearch; this research independently confirms the license concern |
| `bytedance/deer-flow`, `HKUDS/nanobot`, `zhayujie/CowAgent`, `TencentDB-Agent-Memory`, `WeKnora` | Star counts (16k-82k) wildly disproportionate to repo age/issue activity — likely inflated; not evaluated for substance |
| `protectai/llm-guard`, `protectai/rebuff` | Archived, maintenance stopped |
| `rhasspy/piper` | Canonical repo now **archived** — the earlier internal audit's P2 pick is now a maintenance risk; track a fork instead |
| `plastic-labs/honcho` | AGPL-3.0 — real license risk for a modified/redistributed deployment |
| `redis/agent-memory-server` | Non-standard "Other" license + adds a second database (Redis) alongside Postgres |
| `n8n-io/n8n` | Fair-code license (not OSI-approved), wants to own the whole automation loop |
| `temporalio/temporal`, `kestra-io/kestra`, `dagster-io/dagster` | Multi-service/JVM footprint disproportionate to a single CPU-only VM |
| `windmill-labs/windmill` | Genuinely Postgres-native and closest single-tool fit, but AGPL-3.0 core needs legal review before adoption |
| `typesense/typesense` | GPL-3.0 — license regression vs. already-adopted MIT Meilisearch |
| `celery`+`redbeat` | Requires a Redis/RabbitMQ broker not currently in the stack, for no dedup improvement over the status quo |
| `sourcery-ai/sourcery`, `coderabbitai` org | Core review engine is SaaS-only behind an open client — dependency risk |
| `zedeus/nitter` | Archived; reviving a scraping front-end for a platform that actively fights it is a liability, not a shortcut |
| `megadose/holehe` | Probes third-party account-recovery flows — usable only with explicit rate-limit/authorized-target guardrails, flagged not silently recommended |
| NVIDIA PersonaPlex, NeMo-Speech.cpp, Parakeet/Canary | Confirmed GPU-first across the ecosystem — consistent with the platform's existing rejections |

---

## 8. Recommended Sequence

**Now (this week, near-zero risk):**
1. `axe-core`/Storybook a11y addon
2. `pip-audit` pre-commit hook
3. `deepteam` (extends existing deepeval integration)
4. `log4brains` (ADR site)
5. Actually run `garak_gate.py` against the live Model Router (operational, not a new tool)

**Next (this sprint, real but bounded integration work):**
6. `whisper.cpp`/`faster-whisper` Telegram voice-input pilot
7. `FlashRank` reranker into `retrieve_knowledge.py`
8. `promptfoo` as a CI eval/red-team gate
9. `pgqueuer`/`procrastinate` pilot on 1-2 highest-overlap-risk timers
10. `crawl4ai`/`trafilatura` as a cost-reducing first-tier fetcher ahead of Firecrawl/BrightData

**Later (structural, needs a dedicated mission):**
11. Radix/shadcn + React Aria re-theme of the Captain Experience Component Library
12. GPT-Researcher-based revival of the Research Orchestration pipeline
13. mini-swe-agent/PR-Agent pilot against `batch_coding.py`
14. Postgres-native search consolidation bake-off (pgvectorscale + txtai/bm25s) for the remaining 5 fragmented implementations
15. Revisit Execution Engine Interface design against Dapr Agents / A2A patterns once the Hermes evaluation concludes

---

*Generated 2026-09-12 | Sources: `knowledge/SUOC-Platform-Registry.md` v2.14 (full), `AGENTS.md`, `platform-runtime/MODULE-MAP.md`, `specialists/SPECIALIST-INVENTORY.md`, `knowledge/Lessons-Learned.md`, `lcars-portal/package.json`, plus 8 parallel GitHub OSINT sweeps (100+ repositories evaluated, license/activity verified via GitHub API where tool access allowed). No repository functionality, license, or activity claim above is fabricated; anything not directly tool-verified is marked "unverified" in the underlying research and excluded from firm recommendations.*
