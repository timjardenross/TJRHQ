# TJRHQ

TJR HQ — the operational platform repository for USS TJR.

Everything required to run the internal operational platform lives here: workbenches, bots,
Telegram/Slack integrations, cron jobs, systemd services, background workers, AI processing
pipelines, operational databases and migrations, and deployment scripts.

This repo was extracted from `USSTJROS` on 2026-07-19 as part of a three-repo split (see
[Repository relationships](#repository-relationships) below). Extraction used `git filter-repo`,
so file history predating the split is preserved.

---

## Repository relationships

- **TJRHQ** (this repo) — operational platform. Runtime code, bots, workbenches, infrastructure.
- **tjrmindbody_public** — the public-facing website and digital experience.
- **USSTJROS** — mission, governance, architecture, and institutional-knowledge repository.
  Governs and documents capabilities implemented here, but is not itself a home for
  operational code. Design/implementation-notes docs for several TJRHQ components (context
  assembly, coordination, health, command-centre, infrastructure integrations) live there
  under `architecture/component-design-notes/` — this repo has the code, USSTJROS has the
  design record.

---

## Interfaces & runtime components

- **`lcars-portal/`** — An LCARS-style web command dashboard (Next.js + React + TypeScript +
  Tailwind), branded "Starship Endeavour" (NCC-170230). Additive to (not a replacement for)
  the Commander runtime, Command Centre backend, Context Assembly, and Supabase. Pages
  include Captain's Chair, Missions, Engineering, Number One, XO Brief, Medical/Wellness,
  Operations, and Knowledge Base.
- **`platform-runtime/`** — The primary Commander runtime ("Number One"): mission registry,
  proactive scheduling, specialist registry, captain notifications, runtime event logging,
  the collaboration engine. (Historically this lived at `slack-bot/`; it was renamed to
  `platform-runtime/` in mission MSN-0337 — don't recreate a `slack-bot/` directory.)
- **`telegram-bots/`** — Telegram-facing bots. `xo/` is the only live Telegram bot (Captain
  decision 2026-07-05) — the Captain's action interface, running as `tg-xo.service`.
  `recovery_officer/` and `wellness_officer/` are its helpers. The standalone Chief Engineer
  bot was retired 2026-07-12 and removed from the tree; see git history
  (`telegram-bot.DEPRECATED-2026-07-12/` prior to removal).
- **`core/command-centre/`** — Express.js backend + frontend for the command centre surface.

---

## Repository structure

```
TJRHQ/
├── platform-runtime/     # Commander runtime ("Number One") — mission registry, scheduler,
│                         #   specialist registry, notifications, event logging
├── lcars-portal/         # LCARS web command dashboard (Next.js)
├── telegram-bots/        # xo/ (live), recovery_officer/, wellness_officer/
├── core/                 # advisory, capture, content, coordination, dashboard, engineering,
│                         #   governance (authority enforcement), health, inbox, infrastructure
│                         #   (mac-collector, vm-processing, vm-transfer, Supabase migrations),
│                         #   integrations, intelligence, knowledge (operational scripts),
│                         #   knowledge_navigation, llm, model-router, platform, tests,
│                         #   command-centre, context-assembly
├── intelligence/         # AI content pipeline: ingestion, classification, enrichment,
│                         #   ranking, brief generation, governance gate
├── specialists/          # runtime-loadable specialist charters/knowledge packs
├── tools/                # runtime utilities, incl. tools/supabase/ (Commander/Dual-Commander
│                         #   evaluation scripts, embeddings, decision support)
├── services/             # standalone microservices (e.g. transcription)
├── data/                 # operational data (data/self-improvement/ is a historical
│                         #   archive from the deprecated self-improvement loop; live
│                         #   runs now write to /tmp/usstjros-findings/, not here)
├── schemas/              # JSON schemas (self-improvement decision/finding/run records)
├── config/               # runtime policy config
├── scripts/              # self-improvement automation (collector, orchestrator, dashboard)
├── deploy/               # systemd services/timers, launchd, deployment runbooks/checklists
├── USS-TJR-Control/      # VM control layer: launchers, start/stop/status scripts
├── docs/                 # runbooks (graphify maintenance, security remediation),
│                         #   self-improvement operations/deployment docs
└── tests/                # test suites
```

---

## Supabase backend

Operational database migrations live at `core/infrastructure/supabase/migrations/`.
Implementation-notes design records for the Supabase integration (IMPLEMENTATION-NOTES-MSN-*,
SUPABASE-DESIGN, etc.) live in `USSTJROS` under
`architecture/component-design-notes/infrastructure/supabase/`, not here.

## Dual Commander evaluation

`tools/supabase/collaborative_specialist_runtime.py` supports side-by-side Commander model
evaluation — two models receive the same specialist context independently and produce
separate recommendations, with a template-based comparison appended.

```bash
python3 tools/supabase/collaborative_specialist_runtime.py "question"
python3 tools/supabase/collaborative_specialist_runtime.py "question" --challenge
python3 tools/supabase/collaborative_specialist_runtime.py "question" --challenge --dual-commander
```

The candidate slot can be routed through [LiteLLM](https://docs.litellm.ai/) instead of a
second local Ollama tag, so any provider LiteLLM supports (OpenAI, Anthropic, Gemini, Mistral,
or Ollama-through-LiteLLM) can stand in as the candidate — or the primary, since each slot's
provider is independent. This is an optional dependency: run
`tools/supabase/.venv/bin/pip install -r tools/supabase/requirements.txt` once (creating
`tools/supabase/.venv` first with `python3 -m venv tools/supabase/.venv` if it doesn't exist
yet), then invoke the script with `tools/supabase/.venv/bin/python3` instead of the system
`python3` whenever `COMMANDER_PRIMARY_PROVIDER` or `COMMANDER_CANDIDATE_PROVIDER` is set to
`litellm`. Without it, the `ollama`-only path above needs no extra install.

Environment variables (add to `.env`, never commit it):

```
COMMANDER_PRIMARY_MODEL=qwen3:8b
COMMANDER_CANDIDATE_MODEL=deepseek-r1:14b

# Shared default provider for both slots (unchanged behaviour if this is all you set).
COMMANDER_SYNTHESIS_PROVIDER=ollama

# Optional per-slot overrides — primary and candidate can use DIFFERENT providers.
# Each falls back to COMMANDER_SYNTHESIS_PROVIDER, then to "ollama", if unset.
# COMMANDER_PRIMARY_PROVIDER=ollama
# COMMANDER_CANDIDATE_PROVIDER=litellm

OLLAMA_BASE_URL=http://localhost:11434
```

Example: local Ollama primary vs. a cloud candidate via LiteLLM —

```
COMMANDER_PRIMARY_MODEL=qwen3:8b
COMMANDER_PRIMARY_PROVIDER=ollama
COMMANDER_CANDIDATE_MODEL=gemini/gemini-2.5-flash
COMMANDER_CANDIDATE_PROVIDER=litellm
GEMINI_API_KEY=...            # or whatever LiteLLM requires for the chosen provider
```

`COMMANDER_CANDIDATE_MODEL` must be a LiteLLM-formatted model string when
`COMMANDER_CANDIDATE_PROVIDER=litellm` (e.g. `gemini/gemini-2.5-flash`,
`anthropic/claude-sonnet-5`, `ollama/qwen3:8b`) — LiteLLM reads the provider out of the
string itself. A LiteLLM call failure (bad API key, provider down, model not found) falls
back to the same deterministic synthesis the Ollama path uses; it never crashes the run.

---

## Testing

```bash
python -m pytest platform-runtime/ telegram-bots/ -v
```

---

## Governance

This repo implements capabilities; it does not define how they're governed. See
`USSTJROS/governance/` for standards, ADRs, and decision rights, and
`USSTJROS/CLAUDE.md` for standing operational rules (commit conventions, branch policy,
autonomy logging).
