# PR #661 — Privacy containment: go/no-go assessment, deployment impact, rollback

Status: **GO (recommended), pending Captain approval and the VM diagnostic.** Nothing merged or deployed.
Policy: personal health data is processed locally; external AI is default-deny. The only opt-in is
`HEALTH_LLM_EXTERNAL_ALLOWED=1`, and an unrecognised value stays closed.

## 1. Pathways (7 found; the original audit listed 5)
| # | Pathway | Before | After | Test |
|---|---|---|---|---|
| 1 | XO chat (`telegram-bots/xo/app.py`) | cloud-first to Ollama Cloud with full wellness context | `personal=True`: local router only; no reply (not a cloud call) if local fails | containment + failure-path |
| 2 | Correlation synthesis | cloud providers | `local_only` unless opt-in | containment |
| 3 | Nightly memory consolidation | cloud-first | `personal=True` | containment |
| 4 | XO debrief engine | Gemini → Mistral → Ollama | Ollama only unless opt-in | containment |
| 5 | Direct Gemini (`platform-runtime/llm.py`) | unguarded | raises `LLMUnavailableError` on personal content | containment |
| 6 | **New:** weekly health summary (`commands/health_synthesis._llm_synthesis`) | Captain's nervous-system/energy/sleep data and a prompt naming the spinal condition sent to Gemini; the detector did not recognise this format | gated on the flag; detector extended | failure-path (mutation-checked) |
| 7 | **New:** health narrative providers (`core/health/health_llm.py`) | journal free text and weekly prompts to Gemini/Mistral; the detector cannot see free text | local-only provider by default; cloud-tagged "Ollama" models refused | failure-path (standalone) |
| — | Morning-brief email | personal blocks in the email body | blocks stripped; email withheld if personal content remains | containment |

Pathways 6 and 7 were found during this assessment, not in the original audit. Pathway 7 depended on #660; it is now included in #661
with identical file content so the two PRs merge cleanly in either order.

## 2. Failure behaviour (real call functions, `urlopen` patched, every request host recorded)
- Local router timeout, connection refused, non-JSON, empty reply, with a fully configured cloud key: no off-box request, result `None` → deterministic fallback. (4 failure modes × 3 call shapes)
- `MODEL_ROUTER_URL` pointing to a public host: **new fail-closed check** — personal routes refuse it (5 bad URLs, 4 accepted loopback/private forms).
- Bad `LLM_PERSONAL_ROUTER_TIMEOUT` values: default 60 s, still local-only. Unrecognised flag values (`0`, `maybe`, `2`, blank): closed.
- Cloud unreachable on opt-in: returns `None`, no exception escapes. Public (non-personal) routes keep the router→cloud fallback unchanged.
- Logs and exception text never contain the personal content (asserted for each failure mode).
- Mutation checks: removing the router-locality guard → 5 failures; letting a personal route fall through to cloud → 25 failures; removing the weekly-summary gate → 1 failure.
- Counts: 50 failure-path + 47 containment + 25 health-provider tests (122 in total).

## 3. Compatibility
Based on current `main` (`9be606d0`). Merged cleanly in both orders (661→658→659→660 and 660→661→659→658). Root, intelligence, platform-runtime comms and
telegram-bots/xo suites: **0 new failures versus main** in #661 alone and in both integrations (48 pre-existing environment failures, identical on main:
missing pytest-asyncio/flask). CI on the earlier head was green; the latest head must be green before merge.

## 4. Deployment impact (merge to main auto-deploys within about 5 minutes and restarts ten services)
- **XO chat will be slower or sometimes silent.** The local router averaged ~80 s per `xo-response` on this CPU-only host; the personal timeout is 60 s. Expect some XO chat turns to time out and show the deterministic fallback. Tunable with `LLM_PERSONAL_ROUTER_TIMEOUT`. This is the main cost of the policy.
- Weekly health narratives and the nightly consolidation fall back to deterministic text when the local model is unavailable. They never reach a cloud provider.
- Morning-brief email loses its personal blocks; the Captain-only Telegram brief is unchanged.
- No schema change, no new dependency, no scheduler change. Services affected: tg-xo, intelligence-scheduler, tg-capacitybot, model-router and others via restart only.
- **Not verified:** the VM local model. Run `python3 scripts/check_health_llm_local.py` on the VM (exit 0 ok, 2 not configured, 3 unreachable, 4 cloud-tagged). A deterministic fallback is privacy-safe without it.

## 5. Rollback
- Revert the PR; auto-deploy restores the prior behaviour within about 5 minutes. Do not edit the VM checkout.
- Emergency alternative without a revert: setting `HEALTH_LLM_EXTERNAL_ALLOWED=1` restores the old external behaviour. It re-enables transmission of personal health data, so it is a Captain decision, not an operational toggle.

## 6. Residual risks
1. The content detector is pattern-based. Pathways that mark personal routes explicitly (1, 3, 4, 7) do not depend on it; free text elsewhere would. Two gaps were found by audit, so more may exist.
2. `intelligence/adhd/task_decomposition.py` sends task text to Mistral/Gemini. It is not health metrics, but the tasks are the Captain's own; classify it before release.
3. Routes using the unguarded local Ollama function accept a locally tagged model only; a mis-tagged cloud model is caught by the `:cloud`/`-cloud` suffix rule only.
4. Production behaviour on the VM (router latency, local-model availability) is unmeasured from this environment.

## 7. Recommendation
Approve #661 for merge after (a) CI is green on the latest head, (b) the Captain accepts the XO chat latency trade-off, (c) the VM diagnostic is run
or the deterministic-fallback posture is explicitly accepted. Add a follow-up task for residual risks 1–2.

---
## 8. Final release checklist (Captain's direction of 2026-11-23: conditional approval; do not merge without explicit final authorisation)
| # | Item | Status (evidence) |
|---|---|---|
| 1 | CI and merge-gate on the latest commit | Re-check on the final head before merge; the last confirmed fully green head was `63eb87e5`. |
| 2 | Diff limited to privacy changes | Confirmed: 18 files (policy, call guards, health provider, diagnostic, XO fallback, tests, this doc). |
| 3 | `HEALTH_LLM_EXTERNAL_ALLOWED` not enabled in the VM environment | **Operator action.** On the VM run, without printing values: `systemctl show -p Environment tg-xo intelligence-scheduler model-router \| grep -c HEALTH_LLM_EXTERNAL_ALLOWED` (expect 0) and `grep -rls HEALTH_LLM_EXTERNAL_ALLOWED /etc/systemd /opt/starship-endeavour/.env* 2>/dev/null` (expect no output). A test asserts no repository file enables it. |
| 4 | `python3 scripts/check_health_llm_local.py` on the VM | **Operator action; exit code to be recorded:** 0 ok · 2 not configured · 3 unreachable · 4 cloud-tagged model. Exit 3 or 2 is acceptable for privacy (the deterministic fallback applies) but means narratives and XO chat will be unavailable. |
| 5 | Deterministic fallback is privacy-safe when the local model is unavailable | Confirmed by tests: timeout, refusal, bad JSON, empty reply, bad config → no off-box request, deterministic text. |
| 6 | XO fallback wording | Done: "The local AI assistant is unavailable right now. You can still use /brief or /priorities." |
| 7 | End-to-end test of the XO handler | Done: `telegram-bots/xo/test_xo_local_fallback.py` runs the real `cmd_message` with a timing-out and a refusing router, asserts that exact reply and that only loopback hosts were requested. Skips where python-telegram-bot is absent. |
| 8 | Logs, exceptions, telemetry | Confirmed: no personal text in logs or exception text; LLM spans carry provider/model only and export to localhost. |
| 9 | Seven pathways | Confirmed by 126 privacy tests plus the XO end-to-end test. External fallback stays disabled. |

### Expected service impact
Merge to `main` auto-deploys within about 5 minutes and restarts ten services plus the portal build. Behaviour changes: XO chat answers only from the local model (it averaged about 80 s per reply on this host against a 60 s limit, so some turns will show the fallback); weekly health narratives, nightly consolidation, correlation synthesis and the debrief use local models only and fall back to deterministic text; the morning-brief email omits personal blocks; the weekly health summary no longer calls Gemini. No schema, dependency or scheduler change.

### Rollback
Revert the PR on `main`; auto-deploy restores prior behaviour in about 5 minutes. Do not edit the VM checkout. `HEALTH_LLM_EXTERNAL_ALLOWED=1` is an emergency alternative that re-enables external transmission; it is a Captain decision, not an operational toggle.

### Post-merge health checks (operator, within 15 minutes of deploy)
1. `git -C /opt/starship-endeavour rev-parse --short HEAD` equals the merged commit; `systemctl is-active` for tg-xo, intelligence-scheduler, tg-capacitybot, tg-resiliencebot, human-systems-scheduler, model-router, context-service, command-centre, mint-server, self-improvement-dashboard all `active`.
2. `journalctl -u tg-xo --since "15 min ago" | grep -ci "personal health content"` (blocks logged by name only; any count is expected, not a failure) and no tracebacks.
3. Send XO one chat message and one `/brief`: confirm either a local reply or the fallback text, never silence.
4. `python3 scripts/check_health_llm_local.py` again; record the exit code.
5. Confirm no outbound request to a cloud LLM host carried a health prompt: model-router and provider logs show no new `gemini`/`mistral`/`ollama.com` entries for the health jobs.
