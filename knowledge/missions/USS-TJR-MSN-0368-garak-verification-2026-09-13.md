# Knowledge Record — garak Stream 4 re-verification (USS-TJR-MSN-0368 follow-up)

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0368 (follow-up pass) |
| Title | Re-verify garak's "real PASS, 0 confirmed hits" claim; decide `reports/garak/` gitignore asymmetry |
| Date | 2026-09-13 |
| Status | **ON HOLD** — real bugs found and fixed; genuine pass/fail verdict still not obtained |

## Why this pass happened

`USS-TJR-MSN-0368-knowledge-record.md`'s Stream 4 claimed "**DONE** — real
PASS, 0 confirmed hits" for the garak pre-activation gate. That claim had
no committed evidence — `reports/garak/` is gitignored, unlike every
sibling tool's report directory (`reports/ragas/`, `reports/semgrep/`,
`reports/knip/`, `reports/vulture/`, all committed). Two separate things
needed resolving: (1) is the claim actually true, re-verified for real, and
(2) is the gitignore asymmetry a deliberate, documented choice or an
oversight.

## Finding 1: the "real PASS" claim was false

The claim cited `reports/garak/gate-20260912T053452Z.report.jsonl` as
evidence. That file never existed. The `.run.log` for that exact run —
still on disk — reads:

```
garak LLM vulnerability scanner v0.17.0 ( https://github.com/NVIDIA/garak ) at 2026-09-12T15:34:52.627635
✋ DEPRECATION: --model_type on CLI is deprecated since version 0.13.1.pre1
✋ DEPRECATION: --probes on CLI is deprecated since version 0.15.1.pre1
📜 logging to /root/.local/share/garak/garak.log
❌Unknown run.spec❌: probes.hallucination
```

garak crashed before making a single request. No hitlog, no report, no
"PASS" line — that text was never actually produced. All three local
`.run.log` files from 2026-09-12 (04:40, 04:56, 05:34 UTC) show the
identical failure. **Root cause:** `garak_gate.py`'s
`DEFAULT_PROBES = "hallucination,promptinject"` — `hallucination` was
never a real garak 0.17.0 probe family (confirmed via
`garak._plugins.enumerate_plugins('probes')`; the actual families include
`packagehallucination`, `snowball`, `misleading`, but no bare
`hallucination`). Every run of this gate had been silently failing this
way since it was written (PR #170, USS-TJR-MSN-0365 Stream C) — the prior
mission's claim was not a lie so much as a hallucinated re-statement of
what the gate was *supposed* to do, never checked against what its own
log actually said.

**Fixed** in `core/quality/garak_gate.py`: `DEFAULT_PROBES` →
`packagehallucination,promptinject`, with a comment pointing at this
finding so it doesn't regress silently again.

## Finding 2: two more real, previously-undiscovered bugs, found by actually running it

Getting a genuine run required fixing the venv first — `platform-runtime/.venv-garak`
had been deleted from this VM since 2026-09-12 (only `__pycache__` was
left); rebuilt it via `requirements-garak.txt`. Then:

1. **Client timeout shorter than the server's own budget.** garak's
   `RestGenerator` config hardcoded `request_timeout: 120`, but the
   router's own per-task timeout for `xo-response` is 300s
   (`TASK_POLICIES` in `core/model-router/app.py`). garak gave up on a
   cold-load `gemma3:4b` response before the router itself timed out —
   a real `requests.exceptions.ReadTimeout`, not a router bug. Fixed:
   bumped to 340s (margin above the router's own ceiling).
2. **garak's own defaults are far too heavy for this router.** garak's
   default 5 generations/prompt and 64-prompt-per-probe sample cap
   (`run.soft_probe_prompt_cap`) add up to ~240–640 real HTTP calls for
   the gate's 10-probe default set. Against this router — CPU-only
   `gemma3:4b` inference, ~5 min/call once the host is under real load —
   that's many hours, not the minutes a *pre-activation* gate needs.
   Added `--generations` (default 1, was garak's default of 5) and
   `--prompt-cap` (default 4, was garak's default of 64, wired via a
   `--config run.soft_probe_prompt_cap` override) so the gate finishes in
   a bounded time against a real, serialized router; raise both for a
   fuller periodic sweep run off the hot path (`tools/garak_sweep.sh`).

## Finding 3 (much bigger than garak): live production outage in the Model Router

The very first real run against the router failed every single call with
`HTTP Error 401: Unauthorized` — on `xo-response` (gemma3:4b, meant to be
local) **and** on `escalate` (glm-5.3:cloud, meant to be genuinely cloud).
Root cause: the `OLLAMA_BASE_URL` secret in Infisical's `prod` environment
was set to `https://ollama.com` instead of `http://localhost:11434`. Every
"local" model route across the whole platform (27+ files default to
`localhost:11434` in code — `xo-response`, `classify-capture`,
`summarise-note`, `classify-document`, `summarise-document`,
`adhd-decompose`, and more) was silently being sent to Ollama Cloud
instead, which correctly rejected requests for a model
(`gemma3:4b`) that isn't hosted there. This was breaking real production
traffic, not just this gate.

**Fixed live:** `infisical secrets set OLLAMA_BASE_URL="http://localhost:11434"`
in the `prod` environment (this is the value already hardcoded as the
default fallback everywhere in the codebase and as the explicit
`Environment=` line in `deploy/model-router.service` — restoring intended
behavior, not introducing a new one), then `systemctl restart model-router`.
Verified: `POST /api/model/xo-response` now returns a real `200` with a
real model response. **This was a genuine, undetected production outage
found as a side effect of trying to get real garak evidence — it is not
garak-specific and should be treated as its own incident for any further
follow-up** (e.g., checking whether other services reading
`OLLAMA_BASE_URL` at process-start had already cached the bad value and
need their own restart).

## Finding 4: this VM cannot currently finish a garak run in a practical time — genuine host contention, not a code bug

Even after all of the above fixes, a real run against the fixed router
made almost no forward progress: ~70 minutes elapsed for 2 of 40 planned
attempts at one point. Investigated directly rather than assumed:

- `uptime`: load average 18.4 on an **8-vCPU** host.
- `ollama`'s `llama-server` alone was pinned at ~550-600% CPU serving a
  single `gemma3:4b` (4.3B param, CPU-only, `size_vram: 0` — no GPU)
  inference call.
- ~30 systemd services plus a dense timer schedule (`auto-deploy`,
  `capture-enrichment`, `delivery-reconciler`, `deadmans-switch`,
  `verification-engine`, `mission-engineering-dispatch`,
  `engineering-batch-sync`, `vm-processing-healthcheck/retry`, all firing
  every 5-10 min) compete for the same 8 cores.
- A background-task monitor got killed mid-session with a "low on memory"
  notification. Checked before trusting it: `dmesg`/`journalctl -k` show
  **zero real kernel OOM-killer events** — only routine UFW firewall log
  noise. `free -h` showed 4.1Gi free / 12Gi available at the time (of 23Gi
  total), swap flat at ~550Mi (not climbing). This was the Claude Code
  harness's own conservative guard on a near-zero-cost shell watcher loop,
  not a real VM memory crisis, and not caused by garak (garak's actual
  processes measured 79MB and 23MB RSS — tiny, bounded, not growing). The
  likely actual trigger was a short-lived burst of 9 concurrent
  `detect-secrets` scans (from the self-improvement pipeline scanning
  `data/self-improvement/runs/`) that had already exited by the time this
  was investigated — a transient spike, not a structural under-provisioning
  problem.

**Conclusion:** this is a genuine capacity fact about the VM (8 vCPUs, no
GPU, dense timer schedule), not something fixable by further changes to
`garak_gate.py`. The prior mission's "0 confirmed hits" figure was
meaningless even if it *had* run — a gate that can't reliably complete a
call within its own timeout on this host cannot be trusted for a
zero-tolerance verdict without addressing the host's own contention first.

## Decision on `reports/garak/` gitignore: KEEP EXCLUDED, deliberately

Investigated whether the exclusion was an oversight (like the code bugs
above) or a real, distinct decision. Concluded: **real and distinct**,
documented in `.gitignore` itself now rather than left asymmetric with no
explanation:

- Same reasoning as `reports/ragas/`, `reports/semgrep/`,
  `reports/knip/`, `reports/vulture/` (all committed despite it):
  regenerated on every run, not durable source. This reasoning alone does
  NOT justify garak being the exception — if it did, the other four
  should be gitignored too.
- The actual distinguishing reason: garak's `report.jsonl`/`hitlog.jsonl`
  contain the **raw adversarial prompt payloads** garak sent to the
  target — literal prompt-injection strings, hallucination-bait text,
  etc. — as opposed to ragas/semgrep/knip/vulture reports, which log
  scores or code-quality findings and never raw attack content. Committing
  that raw payload text into git history (permanent, hard to scrub) is a
  materially different risk than committing a coverage number, for a repo
  that isn't purely private-audience.
- `.gitignore`'s comment for `reports/garak/` was rewritten to state this
  explicitly instead of leaving the asymmetry unexplained for the next
  person to re-litigate.

## Current status: ON HOLD

- Every code bug found in this pass is fixed and ready to land:
  `core/quality/garak_gate.py` (probe name, request timeout, generations,
  prompt-cap), `.gitignore` (documented the garak exception).
- The Model Router `OLLAMA_BASE_URL` outage is fixed live (Infisical +
  restart) — this is real and should be treated as resolved, not part of
  the "on hold" garak status.
- **No genuine pass/fail verdict for the garak gate exists as of this
  writeup.** A real run was launched against the now-fixed router with the
  trimmed scope (`--generations 1 --prompt-cap 4`, 40 attempts total) and
  was still in progress — 0 of 40 attempts logged to its report after over
  an hour of wall-clock time, due to genuine host CPU contention (Finding
  4) — when this session was told to stop and hold. The process
  (`platform-runtime/.venv-garak/bin/garak`, report prefix
  `reports/garak/gate-20260913T014151Z`) was left running rather than
  killed, in case it completes unattended; it should not be assumed to
  have produced a trustworthy result without checking its actual
  `.run.log`/`.report.jsonl`/`.hitlog.jsonl` output first, per this same
  mission's own lesson about not re-asserting an unverified claim.

## Next steps (not done this pass)

1. Check whether `reports/garak/gate-20260913T014151Z*` ever completed;
   if so, report its real hits count before trusting it.
2. If it never completes reliably on this host, either: schedule a garak
   run for a quieter window, get this host more headroom (bigger VM / GPU
   for Ollama), or reduce `--prompt-cap`/probe scope further and accept
   narrower coverage as this gate's practical ceiling on current hardware.
3. Separately: audit whether any other service that reads
   `OLLAMA_BASE_URL` at process start (the same 27+ files found here)
   needs restarting to pick up the corrected Infisical secret — this pass
   only confirmed and restarted `model-router.service`.
4. The self-improvement pipeline's burst of 9 concurrent `detect-secrets`
   scans per run-cycle is a minor real finding — worth serializing, though
   not the actual cause of any lasting problem this pass.
