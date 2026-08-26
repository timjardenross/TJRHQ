# OSS Solutions for Platform Gaps — 2026-08-23
**Method**: Platform audit → 40 gaps found → matched to free, open-source tools only. CPU VM, solo operator constraints applied. GPU-dependent tools excluded.

---

## How to read this

Each section: gap found in audit → OSS options → pick one.

**Effort rating**: `pip install` / `self-host` / `build`
**Maturity**: stars + last update

---

## GAP 1 — Quality Scoring dead (0 rows since cleanup)

`quality_scoring_service.py` built, never fires. `outcome_capture_service.py` passes `quality_scoring_service=None` by default. No LLM output quality is measured in production.

### Option A: `garak` — LLM vulnerability scanner
- **Install**: `pip install garak` — single command, no infra
- **What it does**: Probes hallucination, prompt injection, data leakage against any REST endpoint. Run it against `:8891` local model router.
- **Maturity**: ⭐ 8.9k, Apache 2.0, updated 2026-08-22
- **Right-sized**: CLI tool, one-off or scheduled. Not a framework adoption.
- **Run**:
  ```bash
  garak --model rest --model_name http://localhost:8891 \
        --probes hallucination,promptinject \
        --report_prefix /opt/starship-endeavour/reports/garak
  ```

### Option B: `deepeval` — LLM unit testing
- **Install**: `pip install deepeval` — no infra
- **What it does**: Assert LLM output correctness in Python tests. Metrics: faithfulness, answer relevancy, hallucination, contextual recall. Works with any model via custom LLM wrapper.
- **Maturity**: ⭐ 8.2k, Apache 2.0, active
- **Right-sized**: Slot into existing test suite. Wire `quality_scoring_service.py` → `deepeval` as backend.
- **Quick wire**:
  ```python
  from deepeval.metrics import HallucinationMetric
  from deepeval.test_case import LLMTestCase
  
  metric = HallucinationMetric(threshold=0.5)
  test_case = LLMTestCase(input=prompt, actual_output=response, context=[context])
  metric.measure(test_case)
  score = metric.score  # 0.0–1.0, write to quality_scores table
  ```

**Recommendation**: `garak` for system-level baseline sweep (run once), `deepeval` to wire into `quality_scoring_service.py` for per-output scoring.

---

## GAP 2 — LLM Observability not running (Arize Phoenix instrumented, silent)

`arize-phoenix 20.3.0` installed. `configure_tracing()` in 3 modules. `start-phoenix.sh` exists. No systemd unit. Spans silently dropped.

### Option A: Arize Phoenix (already installed — just needs to run)
- **Install**: Already done. Zero new dependency.
- **What it does**: Traces every LLM call — latency, tokens, input/output, span tree. Web UI on `:6006`.
- **Maturity**: ⭐ 4.1k, Apache 2.0
- **Fix**: Add to process supervisor or run in background:
  ```bash
  # Add to start-services.sh or equivalent
  nohup python -m phoenix.server.main serve &> /var/log/phoenix.log &
  ```
  Or wire into existing scheduler startup.
- **Right-sized**: Zero install cost. Ship what's already built.

### Option B: `Langfuse` — open source LLM observability
- **Install**: `pip install langfuse` + `docker compose up` (self-hosted) or free cloud tier
- **What it does**: Traces, evals, prompt management, dataset management. Better UI than Phoenix for long-term monitoring.
- **Maturity**: ⭐ 8.7k, MIT, very active
- **Right-sized**: Docker compose is ~5 min. Use cloud free tier if no Docker preference.
- **Caveat**: More infra than Phoenix-already-installed. Use Option A first.

**Recommendation**: Start Phoenix (it's already installed). Evaluate Langfuse in 30 days if Phoenix UI is insufficient.

---

## GAP 3 — Unified Memory dormant (8 of 9 paths zero callers)

`unified_memory.py` maps 9 memory types. Only `OFFICER_CONTEXT` has a caller. Episodic memory (pgvector) is new and wired. But semantic/procedural/factual memory never activates.

### Option A: `mem0` — open source memory layer
- **Install**: `pip install mem0ai` — no infra (uses existing Supabase pgvector)
- **What it does**: Add/search/update memories tied to user/agent ID. Handles dedup, versioning, retrieval automatically. Supports pgvector as backend.
- **Maturity**: ⭐ 27k, Apache 2.0, very active
- **Right-sized**: Wraps existing pgvector. Drop into `unified_memory.py` as retrieval backend for semantic/factual paths.
- **Wire**:
  ```python
  from mem0 import Memory
  
  config = {"vector_store": {"provider": "pgvector", "config": {"url": SUPABASE_URL}}}
  m = Memory.from_config(config)
  m.add("Captain prefers concise briefs under 200 words", user_id="captain")
  results = m.search("brief length preferences", user_id="captain")
  ```

### Option B: `Graphiti` — temporal knowledge graph (already in repo)
- **Install**: Already built at `core/platform/memory_graph.py`. Zero callers.
- **What it does**: Temporal fact storage — tracks when facts were true, not just what is currently true. Right tool for the ghost temporal tables (temporal_entities/facts/episodes).
- **Maturity**: ⭐ 6.1k (Zep/Graphiti OSS), Apache 2.0
- **Right-sized**: Code exists. Gap is zero callers, not zero code. Wire `retrieve_knowledge.py` → `memory_graph.py`.

**Recommendation**: Wire `Graphiti` first (code already exists, zero install). Add `mem0` as semantic memory layer for the 8 dormant paths.

---

## GAP 4 — Search fragmented (6 incompatible implementations)

6 separate search implementations. `retrieve_knowledge.py` never called. Wave 4 consolidation mission not assigned.

### Option A: `Meilisearch` — open source full-text + vector search
- **Install**: `curl -L https://install.meilisearch.com | sh` — single binary, no Docker required
- **What it does**: Full-text search + semantic search (hybrid). REST API. Runs on CPU, low memory (~50MB idle).
- **Maturity**: ⭐ 48k, MIT, very active
- **Right-sized**: Replace all 6 implementations with one REST call. Single binary to manage.
- **Run**: `meilisearch --master-key YOUR_KEY &`

### Option B: `Qdrant` — open source vector search
- **Install**: `pip install qdrant-client` + single binary or Docker
- **What it does**: Vector similarity search. Better than pgvector for semantic search at scale. REST + Python SDK.
- **Maturity**: ⭐ 22k, Apache 2.0
- **Right-sized**: Overkill if pgvector already works. Use only if pgvector performance degrades.

**Recommendation**: Meilisearch for search consolidation — single binary, hybrid search, replaces all 6 implementations with one client. Assign Wave 4 mission to wire `retrieve_knowledge.py` → Meilisearch.

---

## GAP 5 — Knowledge pipeline manual (814 doc backlog, disk-scan only)

`knowledge_utilisation.py` scans disk files. No DB integration. 814-document review backlog. Graph sync is manual, not event-driven.

### Option A: `Docling` — IBM open source document processor
- **Install**: `pip install docling` — no infra
- **What it does**: Extracts text, tables, images from PDF/Word/HTML/Markdown. Outputs structured JSON ready for vector store ingestion.
- **Maturity**: ⭐ 20k, MIT, IBM-backed
- **Right-sized**: Plug into knowledge pipeline as pre-processor. Runs on CPU.
- **Wire**:
  ```python
  from docling.document_converter import DocumentConverter
  converter = DocumentConverter()
  result = converter.convert("/path/to/doc.pdf")
  text = result.document.export_to_markdown()
  # → write to knowledge DB / vector store
  ```

### Option B: `Apache Tika` (Python wrapper)
- **Install**: `pip install tika` — wraps Java Tika server
- **What it does**: Extracts text from 1000+ file formats
- **Maturity**: Mature, Apache 2.0
- **Caveat**: Requires JVM. Heavier than Docling.

**Recommendation**: `Docling` — no JVM dependency, better structured output, actively maintained.

---

## GAP 6 — Voice output gap (XO Debrief text-only, never committed)

XO Voice Daily Debrief built 2026-07-07, never committed. Debrief tables exist. No voice response capability anywhere.

### Option A: `edge-tts` — Microsoft Edge neural TTS (free API wrapper)
- **Install**: `pip install edge-tts` — no infra, no API key
- **What it does**: 30+ neural voices via Microsoft Edge TTS. Free, unlimited. Australian + British English voices available.
- **Maturity**: ⭐ 5.7k, GPL, active
- **Right-sized**: Zero infra cost. Call from existing XO debrief handler → send audio via Telegram.
- **Wire**:
  ```python
  # core/voice/tts_edge.py
  import asyncio, edge_tts
  
  XO_VOICE = "en-AU-WilliamNeural"
  
  async def speak(text: str, output_path: str) -> str:
      communicate = edge_tts.Communicate(text, XO_VOICE)
      await communicate.save(output_path)
      return output_path
  
  # In XO debrief handler:
  audio_path = asyncio.run(speak(brief_text, "/tmp/xo-debrief.mp3"))
  await bot.send_audio(chat_id=CAPTAIN_ID, audio=open(audio_path, "rb"))
  ```

### Option B: `Piper` — offline self-hosted TTS
- **Install**: `pip install piper-tts` + model download (~50MB)
- **What it does**: Fast CPU TTS (<50ms), fully offline, no API calls
- **Maturity**: ⭐ 5.3k, MIT
- **Right-sized**: Use when offline/privacy needed or edge-tts rate limits hit
- **Swap**: Same interface as edge-tts wrapper, drop-in replacement

**Recommendation**: `edge-tts` now. `Piper` as fallback/upgrade when offline operation needed.

---

## GAP 7 — Scheduling fragmented (5 separate APScheduler instances, double-fire risk)

5 separate `apscheduler` instances across the platform. Double-fire risk on overlapping jobs.

### Option A: Consolidate to single APScheduler (no new OSS)
- **Right-sized**: Not an OSS gap — it's an internal architecture issue. Assign a mission to consolidate `intelligence/scheduler.py` as the canonical instance and decommission the other 4.
- **Cost**: Zero.

### Option B: `Rocketry` — modern Python scheduler
- **Install**: `pip install rocketry` — no infra
- **What it does**: Declarative scheduling with conditions, retry logic, built-in task tracking
- **Maturity**: ⭐ 3.4k, MIT
- **Right-sized**: Only worth adopting if APScheduler consolidation proves hard. Don't add a 6th scheduler.

**Recommendation**: Consolidate existing APScheduler first. No new OSS needed.

---

## GAP 8 — Research Orchestration dormant (Slack bot, zero callers)

`slack-bot/lib/research/` — fully built research pipeline. Zero live callers. `ResearchTask` not migrated to Task Engine.

### Option A: `SearXNG` — open source metasearch engine
- **Install**: Docker compose (5 min) or `pip install searxng`
- **What it does**: Aggregates 70+ search sources (Google, Bing, DuckDuckGo, Reddit, etc.) into one API. No API keys needed.
- **Maturity**: ⭐ 13k, AGPL, very active
- **Right-sized**: Plug into dormant research pipeline as the search backend. Replaces whatever search source it currently calls.
- **API**: `GET http://localhost:8080/search?q=query&format=json`

### Option B: `Perplexica` — open source Perplexity alternative
- **Install**: Docker compose
- **What it does**: AI-powered web search with LLM synthesis. Supports local Ollama models.
- **Maturity**: ⭐ 18k, MIT
- **Right-sized**: More opinionated than SearXNG. Use if you want pre-synthesized search results rather than raw results.

**Recommendation**: `SearXNG` — simpler, more composable, wires directly into existing research pipeline as data source.

---

## NOT AN OSS GAP — internal wiring issues

These gaps need code changes, not new tools:

| Gap | Fix |
|---|---|
| `interrupt_now` never fires (Attention Engine) | Fix threshold logic in `intelligence_store.py:770` |
| Priority Engine hardcoded zeros | Wire Learning & Adaptation outputs to weighting |
| 46 pre-existing test failures | Run suite, fix failures |
| Knowledge PATCH auth gap | Add auth check to `/memory/[id]/route.ts` |
| Event Bus dead domains | Add `publish_event()` callers in research-learning modules |
| Pattern Library zero consumers | Wire downstream calls from Captain Intelligence |
| Mobile nav (23/25 workbenches) | CSS/responsive layout work |

---

## Summary — what to install now

| Gap | Tool | Install | Priority |
|---|---|---|---|
| Quality scoring dead | `garak` + `deepeval` | `pip install garak deepeval` | P1 |
| Observability silent | Arize Phoenix (already installed) | `start-phoenix.sh` | P1 |
| Voice output missing | `edge-tts` | `pip install edge-tts` | P1 |
| Memory dormant | `mem0` | `pip install mem0ai` | P2 |
| Knowledge pipeline manual | `Docling` | `pip install docling` | P2 |
| Search fragmented | `Meilisearch` | Single binary install | P2 |
| Research dormant | `SearXNG` | Docker compose | P3 |
| Voice offline fallback | `Piper` | `pip install piper-tts` | P3 |
| Scheduling fragmented | None — consolidate APScheduler | Internal mission | P2 |

---

*Generated: 2026-08-23 | Source: 40-gap platform audit | Constraint: CPU VM, no GPU, free + open source only*
