# Repository Catalogue

_Restored 2026-09-15 to satisfy `platform-runtime/prompt_loader.py`'s expected path
(`knowledge/Repository-Catalogue.md`) — content derived directly from a top-level
`ls` of this repository as of 2026-09-15. `platform-runtime/MODULE-MAP.md` independently
names `Repository-Catalogue.md` as one of the documents `repository_awareness.py`
(BOT-008) reads, which corroborates the file's intended purpose even though that module
is itself dead code — see `specialists/RUNTIME-STATUS.md`. `prompt_loader.py` has zero
live callers repo-wide._

## Top-Level Directories

| Directory | Contents |
|---|---|
| `.claude/skills/` | Persona and process skills for Claude Code (chief-engineer, chief-of-staff, xo, bc-advisor, design-audit, plus eval-workspace and archived review folders). |
| `.cortex/` | `index-sources.json` — indexing configuration for some external tool/agent. |
| `.github/` | `dependabot.yml`, PR template, and CI workflows. |
| `config/` | JSON policy/config files: `evolution_watchlist.json`, `osint_intelligence_missions.json`, `self_improvement_policy.json`. |
| `core/` | The platform's core Python packages: advisory, capture, command-centre, content, context-assembly, coordination, crew (specialist governance folders + registry), dashboard, and more. |
| `data/` | `mem0_qdrant/`, `self-improvement/` — data stores for memory/vector and self-improvement subsystems. |
| `deploy/` | Runbooks, deployment checklists, and systemd unit/service files. |
| `docs/` | Design docs, architecture notes, and decision records (`docs/decisions/` — MADR template + worked example). |
| `governance/` | `authority/` — governance/authority-related material. |
| `intelligence/` | OSINT/intelligence pipeline code: `adhd/`, `analysis/`, `audit/`, `brief/`, `classification/`, scheduler, notifier, etc. |
| `lcars-portal/` | Next.js frontend application (the "LCARS Portal" web UI), including `advisory-workbench` and other workbenches. |
| `platform-runtime/` | Shared runtime standards and modules: `prompt_loader.py` (this file's consumer), `MODULE-MAP.md`, `DEVELOPMENT-GUIDE.md`, config/error-handling/logging/release/security standards. |
| `reports/` | Automated analysis output: `deepteam/`, `garak/`, `knip/`, `ragas/`, `semgrep/`, `vulture/` (dead-code reports — see `reports/vulture/vulture-2026-09-12-full-output.txt`, which independently flags `prompt_loader.py`'s public functions as unused). |
| `schemas/` | JSON Schema files for self-improvement decisions/findings/runs. |
| `scripts/` | Operational scripts: memory backfill, intelligence audit, dashboard startup, self-improvement tooling. |
| `services/` | `revs-content-agents/`, `transcription/` — standalone service code. |
| `specialists/` | Specialist charter files (`core-crew/`, `future-crew/`, `knowledge-packs/`), plus inventory/registry/status docs (`SPECIALIST-INVENTORY.md`, `RUNTIME-STATUS.md`, etc.). |
| `telegram-bots/` | Telegram bot implementations: `capacitybot`, `recovery_officer`, `revs`, `wellness_officer`, `xo`, plus shared `llm.py`. |
| `tests/` | Pytest suite (`test_advisory_*.py`, fixtures, `conftest.py`). |
| `tools/` | Operational/maintenance scripts: secret scanning, mission minting, config-loader checks, Supabase batch SQL, domain-registry drift checks. |
| `Missions/` | `Active/`, `Engineering-Handoffs/` — mission tracking (distinct from `knowledge/missions/`, see below). |
| `USS-TJR-Control/` | VM startup/control scripts and config for the platform's host environment. |
| `knowledge/` | Narrative knowledge base: lessons learned, mission-brief template, OSS assessments, `SUOC-Platform-Registry.md`, plus `backlog-samples/`, `memory/`, and `missions/` subfolders — see `knowledge/Commander-Knowledge-Index.md` for detail. |

## Notable Top-Level Files

- `AGENTS.md` — short pointer to `.claude/skills/` and repo-wide governance rules
  (check-first registries, concurrent-session git safety).
- `README.md` — top-level project readme.
- Several large narrative mission/workbench documents live directly at repo root
  (e.g. `HEALTH_OSINT_IMPLEMENTATION.md`, `TECHNICAL_OSINT_WORKBENCH.md`,
  `REVS_Telegram_Prompt_Library.md`) rather than under `docs/` or `knowledge/` —
  a real inconsistency in where narrative documents live, not something this
  catalogue smooths over.
- `platform_runtime` and `telegram_bots` are symlinks to `platform-runtime/` and
  `telegram-bots/` respectively (hyphen/underscore aliasing).

## Related Files

- `knowledge/Commander-Knowledge-Index.md` — detail on the `knowledge/` directory itself
- `knowledge/Source-of-Truth-Matrix.md` — which files are canonical for what
- `specialists/RUNTIME-STATUS.md` — dead-code status of the loader this file serves
