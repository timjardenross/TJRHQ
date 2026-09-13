# USS-TJR-MSN-0374 Stream 2: pip-audit pre-commit + CI gate — Knowledge Record

**Date:** 2026-09-13
**Branch:** `msn-0374-stream2-pip-audit`
**Status:** Complete — gate wired, advisory/report-only on this first landing (per mission scope). Not merged to main; branch pushed to origin, PR opened.

## Context

Confirmed real gap before starting: `grep -n "pip-audit\|pip_audit" .pre-commit-config.yaml` on `main` found nothing. This repo had zero dependency-CVE scanning of any kind — bandit covers static security lint, gitleaks/detect-secrets cover leaked secrets, but nothing scanned `requirements*.txt` pins against known-vulnerable-version databases.

Scope for this stream: wire the gate (pre-commit hook + CI job), scoped to `platform-runtime/requirements.txt` and every other tracked `requirements*.txt`, non-blocking on first landing. Explicitly out of scope: fixing any CVEs found, gitleaks (already present and working), any other MSN-0374 stream's work.

## What was found (found via `find . -name "requirements*.txt" -not -path "*/node_modules/*"`)

15 tracked `requirements*.txt` files repo-wide:

```
scripts/self_improvement/requirements.txt
platform-runtime/requirements.txt
telegram-bots/revs/requirements.txt
telegram-bots/capacitybot/requirements.txt
telegram-bots/xo/requirements.txt
services/revs-content-agents/requirements.txt
core/quality/requirements-garak.txt
core/quality/requirements-ragas.txt
core/knowledge/requirements-docling.txt
core/security/requirements-llmsec.txt
tools/supabase/requirements.txt
core/infrastructure/mac-collector/requirements.txt
core/infrastructure/vm-processing/requirements.txt
core/infrastructure/vm-transfer/requirements.txt
intelligence/ingestion/browser_worker/requirements.txt
```

## Real pip-audit run — actual captured finding count

Installed `pip-audit==2.10.1` into an isolated venv (`/tmp/pip-audit-venv`, PEP 668 blocks a global install) and ran `pip-audit -r <file> --skip-editable -f json` against each of the 15 files above for real. Not a "the gate exists" claim without numbers — full output captured to `/tmp/pip-audit-out/*.json` and deduplicated by `(package, version, vuln id)` (pip-audit's own JSON output listed each finding twice per affected package in this run — same `id`, same `aliases`, no distinct advisory — a pip-audit output quirk, not a real doubling of vulnerabilities; deduped before counting).

**Total: 17 distinct (package, version, advisory-id) findings, across 12 unique package@version pins, in 5 of the 15 scoped files.** 9 files scan clean (0 findings). 1 file (`telegram-bots/revs/requirements.txt`) could not be resolved at all — see below.

| requirements file | findings | packages affected |
|---|---|---|
| `services/revs-content-agents/requirements.txt` | 8 | `python-dotenv` 1.0.0 (PYSEC-2026-2270), `requests` 2.31.0 (PYSEC-2026-1872, -1873, -2275), `weasyprint` 69.0 (PYSEC-2026-3940), `pypdf2` 3.0.1 (PYSEC-2026-1835), `black` 24.4.2 (PYSEC-2026-2120, -2121) |
| `core/security/requirements-llmsec.txt` | 3 | `cryptography` 48.0.1 (PYSEC-2026-3552, -3553, -3554) |
| `core/quality/requirements-ragas.txt` | 3 | `ragas` 0.4.3 (PYSEC-2026-3046), `diskcache` 5.6.3 (PYSEC-2026-2447), `langchain-openai` 1.1.9 (PYSEC-2026-76) |
| `core/quality/requirements-garak.txt` | 2 | `datasets` 3.6.0 (PYSEC-2026-3716), `nltk` 3.10.3 (PYSEC-2026-3740) |
| `platform-runtime/requirements.txt` | 1 | `python-dotenv` 1.2.1 (PYSEC-2026-2270) |
| `scripts/self_improvement/requirements.txt` | 0 | — |
| `telegram-bots/capacitybot/requirements.txt` | 0 | — |
| `telegram-bots/xo/requirements.txt` | 0 | — |
| `core/knowledge/requirements-docling.txt` | 0 | — |
| `tools/supabase/requirements.txt` | 0 | — |
| `core/infrastructure/mac-collector/requirements.txt` | 0 | — |
| `core/infrastructure/vm-processing/requirements.txt` | 0 | — |
| `core/infrastructure/vm-transfer/requirements.txt` | 0 | — |
| `intelligence/ingestion/browser_worker/requirements.txt` | 0 | — |
| `telegram-bots/revs/requirements.txt` | **could not resolve** | pip-audit's dependency resolver hit `ResolutionImpossible`: the pinned requirements plus an implicit `httpx<0.29` constraint have conflicting dependencies. This is a pre-existing dependency-graph issue in that file, not a CVE finding — pip-audit never got to the vulnerability-matching step for it. Flagged, not fixed (out of scope for this stream). |

Remediating any of the 17 findings above, or the `telegram-bots/revs` resolution failure, is explicitly out of scope for this stream — this mission's job was standing up the gate and reporting the real number, per the brief.

## What was wired

- **`.pre-commit-config.yaml`**: added a `pip-audit` hook under the existing `repo: local` block (alongside `no-raw-env-secrets`), not a hosted `repo:` entry like bandit/ruff-check — pip-audit has no "report but don't fail" flag, so a real finding always exits non-zero, and gating commits on the unmeasured/nonzero backlog above (now measured, but not this mission's job to fix) would block every contributor's commits for reasons unrelated to their own change. `tools/run_pip_audit_advisory.py` is the wrapper: it runs `python -m pip_audit -r <file>` for real against every changed `requirements*.txt` (matched via `files: 'requirements.*\.txt$'`), prints full findings to stderr, and always exits 0. `language: python` + `additional_dependencies: ["pip-audit==2.10.1"]` gives pre-commit its own isolated managed env for pip-audit (matching how bandit/ruff-check/gitleaks/detect-secrets each get isolated envs above), rather than requiring a system-wide install.
- **`.github/workflows/python-ci.yml`**: added a standalone `pip-audit` job (mirrors the existing `vulture`/`semgrep` advisory-job pattern in the same file), running `pip-audit -r` directly (not through `pre-commit run`, for the same non-blocking reason above) against every file `find . -name "requirements*.txt"` turns up, with `continue-on-error: true` on the step itself (not just the job) — confirmed by the vulture job's own comment in this file that job-level `continue-on-error` alone still reports the job's check-run as failed; step-level is what actually shows green-with-a-log.

## Follow-ups for a future mission

1. Triage the 17 real findings above (12 unique package@version pins across 5 files) to zero or documented-accepted, the same way MSN-0369/0370 triaged bandit/ruff, then flip `tools/run_pip_audit_advisory.py` to propagate pip-audit's real exit code (or drop the wrapper and call `pip-audit` directly in both the pre-commit hook and the CI job) to make the gate blocking.
2. Fix `telegram-bots/revs/requirements.txt`'s dependency conflict (pinned deps vs. an implicit `httpx<0.29` constraint) so pip-audit — and any other tool that needs to actually resolve this file's dependency graph — can scan it at all.
