# USS-TJR-MSN-0369 Stream 1: Bandit Triage — Knowledge Record

**Date:** 2026-09-12
**Branch:** `msn-0369-stream1-bandit-triage`
**Status:** Complete — not merged to main (per instructions), branch pushed to origin.

## Context

This session **continued an interrupted prior pass**. On pickup, the working tree
already had 92 files with uncommitted changes — real B310 (urllib scheme) fixes
and suppressions done by a previous agent that got interrupted before committing.
This session reviewed that diff for quality (spot-checked ~10 files across
core/, intelligence/, tools/), found it sound, then re-ran `bandit -ll` against
the whole repo (with the pending fixes already on disk, since bandit scans the
working tree) to find what remained, and closed out the rest.

## Method

- Installed bandit 1.9.4 into an isolated venv (`/tmp/bandit-venv`) since no
  system bandit was available and PEP 668 blocked a global pip install.
- Ran `bandit -r . -ll -x './node_modules,./.git'` (medium+ severity/confidence,
  no real `.venv` dirs existed in this checkout so no extra excludes were
  needed).
- Before this session's edits: 92 files already modified, 151 `nosec` comments
  added by the prior agent (mostly B310, plus 4 B104 already resolved — see
  below).
- After this session's edits: **10 → 2 medium findings**, both in the
  deliberately deferred file.

## Final bandit -ll count

**0 unaddressed medium findings**, except the deliberately deferred pair in
`intelligence/adhd/task_nudge_scheduler.py` (1× B108, 1× B310) — confirmed via
`git diff --stat` showing **zero changes** to that file (Stream 2's ruff
autofix must land there first, per the brief).

Final scan output:
```
B108 ./intelligence/adhd/task_nudge_scheduler.py:28   (DEFERRED — untouched)
B310 ./intelligence/adhd/task_nudge_scheduler.py:148  (DEFERRED — untouched)
```

## By check type

### B310 (urllib scheme audit)
Handled almost entirely by the prior agent's uncommitted work (the bulk of the
92-file diff). All resolved via `# nosec B310 - <reason> - reviewed 2026-09-12`
suppression comments rather than urlparse/scheme-allowlist rewrites, because
every case inspected was a URL built from a fixed constant, an internal env
var (SUPABASE_URL, OLLAMA_BASE, ROUTER_URL, BACKEND_HEALTH_URL), or a hardcoded
literal API host (api.resend.com, api.mistral.ai,
generativelanguage.googleapis.com) — never attacker-controlled input, so a
runtime scheme check would be dead code. Spot-checked ~10 files
(core/capture/enrichment_worker.py, core/coordination/command_bus.py,
core/notifications/resend_email.py, core/llm/provider_chain.py,
core/quality/garak_gate.py, etc.) — all suppressions cite the specific source
of the URL, not a generic "trusted" wave-off. No remaining open B310 findings
outside the deferred file.

### B108 (hardcoded /tmp)
Original brief said ~12 findings, 1 deferred. Actual fresh scan (after the
prior agent's B310 work already reduced drift) showed only 9 total, 1 of which
is the deferred file. This session fixed the remaining 8, all in test files
where the `/tmp/...` path is a synthetic fixture for a "missing/mocked file"
test case, never a real write target:
- `core/coordination/test_number_one.py:580` — asserts graceful degradation
  on a missing handoffs directory.
- `services/transcription/test_transcribe.py:34` — asserts missing-file error
  handling in `transcribe_file`.
- `telegram-bots/xo/test_voice_capture.py:150,162,242,261,370,387` — one real
  missing-file assertion; the other five pass a fake path into
  `transcribe_audio`/`handle_capture_from_voice` while `subprocess.run` or
  `transcribe_audio` itself is mocked, so no real file I/O ever touches the
  path.

All 8 suppressed with dated, specific `# nosec B108 - ...` reasons rather than
rewritten to use `tempfile`, since rewriting would add real filesystem I/O to
tests whose whole point is to *not* touch the filesystem.

### B314 (XXE via xml.etree.ElementTree)
Verified already fully resolved before this session — 0 open findings in the
fresh full-repo scan, and no B314-tagged `nosec` needed to be added. Confirmed
`xml.etree.ElementTree` is not the parser in use where XML is handled;
`defusedxml` is the pattern.

### B608 (SQL string building)
Verified already fully resolved — 0 open findings; `nosec B608` suppressions
present in the tree with dated reasons already predate this session (found via
`grep -rn "nosec B608"` — 12 total nosec references across B314/B608/B318,
already applied). No rework needed.

### B318 (minidom)
Verified already fully resolved — 0 open findings for minidom-based XML
parsing (`tools/graphify_to_gexf.py`, `tools/graphify_gephi_export.py` use
`xml.etree.ElementTree`/other paths already suppressed or non-issue). No
rework needed.

**No discrepancies found** between the "should already be fixed" claims in the
brief (B314/B608/B318) and the actual state of the repo — all three were
genuinely already handled prior to this session.

### B104 (bind 0.0.0.0) — REAL DECISION, not previously done

Brief said 2 findings; actual scan (post-prior-agent-diff) found **4** call
sites, all already resolved in the uncommitted diff this session inherited.
Reviewed each against deployment configs to confirm the reasoning holds:

1. **`core/voice/tts_chatterbox.py:182`** — `uvicorn.run(app, host="0.0.0.0", ...)`.
   **Decision: keep 0.0.0.0, suppress.** This TTS service is deliberately
   exposed via Caddy so Vercel-hosted lcars-portal can reach it (see module
   docstring). `TTS_SERVICE_SECRET` header auth is the compensating control.
2. **`core/voice/tts_kokoro.py:192`** — same pattern as tts_chatterbox.py.
   **Decision: keep 0.0.0.0, suppress**, same reasoning (same Caddy-fronted
   voice-service architecture, same secret-header compensating control).
3. **`intelligence/watchlist/changedetection_webhook.py:194`** —
   `ThreadingHTTPServer(("0.0.0.0", port), ...)`. **Decision: keep 0.0.0.0,
   suppress.** Verified against `deploy/docker-compose.watchlist.yml` and
   `deploy/watchlist-changedetection-webhook.service`: the changedetection.io
   container reaches this webhook via `host.docker.internal`, which requires
   the host listener to be on all interfaces, not just loopback.
4. **`intelligence/watchlist/uptime_kuma_webhook.py:161`** — same pattern,
   verified against the same compose file and
   `deploy/watchlist-uptime-kuma-webhook.service` for the Uptime Kuma
   container's `host.docker.internal` requirement. **Decision: keep 0.0.0.0,
   suppress.**

All four are genuine "yes, needs broader reachability" cases with a named
compensating control (secret header or Docker network necessity) documented
in the suppression comment for human review/override.

## Deferred file — confirmed untouched

`intelligence/adhd/task_nudge_scheduler.py` — `git diff --stat` shows **no
changes** to this file across the entire session (prior agent's pass + this
session's). It retains its 1× B108 and 1× B310 open findings, to be handled
after Stream 2's ruff autofix lands, per the brief.

## Outcome

- Fresh `bandit -ll` on HEAD-of-branch working tree: **2 findings, both in the
  deferred file** — 0 unaddressed findings elsewhere.
- 95 files changed total (92 inherited + 3 touched this session:
  `core/coordination/test_number_one.py`,
  `services/transcription/test_transcribe.py`,
  `telegram-bots/xo/test_voice_capture.py`).
- All changes committed to `msn-0369-stream1-bandit-triage` and pushed to
  origin. Not merged to main.
