# Host Validation Matrix — Advisor Intelligence (MSN-0101 WP3)

Execute on the **production host** (where the live services exist). This is the
fill-in-the-blanks record for the MSN-0094 runbook validation.

**Environment note:** the engineering build container used to develop this
programme has **no live Slack/Telegram/XO/Supabase/Ollama and no production
host**, so every live-transport row below is `UNAVAILABLE (CI)` here and must be
executed by the operator on the host. Logic/build-tier checks that *were* run in
CI are marked `PASS (CI)` for reference.

Status legend: `PASS` · `FAIL` · `DEGRADED` (works with reduced capability) ·
`UNAVAILABLE` (could not be reached/executed).

## Matrix

| # | Check | How to verify | CI result | Host result |
|---|---|---|---|---|
| 1 | Advisory runtime (deterministic) | `python3 core/advisory/cli.py --action advice --question "smoke" --format markdown` | PASS (CI) | ☐ |
| 2 | Advisory runtime (Ollama live) | `COMMANDER_SYNTHESIS_PROVIDER=ollama … --action advice` → synthesis_provider=ollama | UNAVAILABLE (CI) | ☐ |
| 3 | Supabase connectivity | advice cites Supabase sources; `--action evidence` returns live items | UNAVAILABLE (CI) | ☐ |
| 4 | Ollama connectivity | live synthesis returns non-empty within timeout | UNAVAILABLE (CI) | ☐ |
| 5 | Slack transport | each of the 11 commands returns a reply (see checklist) | UNAVAILABLE (CI) | ☐ |
| 6 | Telegram transport | `/advisor`, `/awareness`, `/intel`, `/timeline`, `/advisory_outcome` reply | UNAVAILABLE (CI) | ☐ |
| 7 | XO transport | XO bot `/advisory`, `/challenge`, `/evidence` reply | UNAVAILABLE (CI) | ☐ |
| 8 | Portal `/api/advisory` (auth) | authenticated POST returns `result` JSON; anonymous → redirect to `/login` | UNAVAILABLE (CI) | ☐ |
| 9 | Intelligence Centre | `/intelligence` loads; Awareness tab default; tabs fetch without error | PASS (CI build) | ☐ |
| 10 | Product actions | `--action awareness\|products\|resilience-watch\|wellness-insights\|strategic-outlook\|opportunity-review` return valid output | PASS (CI) | ☐ |
| 11 | Operational Resilience Watch (live) | OR pipeline has collected events; watch shows current items | UNAVAILABLE (CI) | ☐ |
| 12 | Closed loop | `/advisory-outcome` → `--action metrics` counter increments | PASS (CI) | ☐ |
| 13 | Secret-free build | `npm run build` (no Supabase env) → 34/34 routes | PASS (CI) | ☐ |
| 14 | Test collection | `pytest tests/ --co` → no abort (542 collected) | PASS (CI) | ☐ |

## Sign-off

| Field | Value |
|---|---|
| Validated by | __________________ |
| Date | __________________ |
| Overall | ☐ PASS ☐ PASS-WITH-DEGRADED ☐ BLOCKED |
| Failures documented | __________________ |

**Rule (per directive):** any failure is documented here; **no unsupported
workarounds** are to be introduced. Degraded behaviour (e.g. Ollama down →
deterministic synthesis) is acceptable and should be recorded as `DEGRADED`, not
"fixed" with a hack.
