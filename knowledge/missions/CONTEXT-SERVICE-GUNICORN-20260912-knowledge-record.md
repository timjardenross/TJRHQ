# Knowledge Record — context-service swapped from Werkzeug dev server to gunicorn, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0365 (Stream B) |
| Title | context-service's own code acknowledged it was running the dev server in production; now runs gunicorn |
| Date | 2026-09-12 |
| Lesson | LL-150 |

## Outcome

`core/context-assembly/context_service.py`'s `serve` CLI subcommand called
`flask_app.run(host=..., port=..., debug=False, threaded=True)` directly —
the file's own comment already acknowledged this was "not a production WSGI
server" — while `deploy/context-service.service` ran it under systemd
supervision on a path reachable (via Caddy) from outside the VM.

Fixed in PR #156 (https://github.com/timjardenross/TJRHQ/pull/156, merged):

- Added a module-level `create_app()` WSGI factory (thin wrapper around the
  existing `_make_flask_app()`) and a `_run_gunicorn(host, port)` helper that
  `os.execvp`'s into `gunicorn --worker-class gthread --workers 1 --threads 4
  --timeout 300 context_service:create_app()`. The `serve` subcommand now
  calls this instead of `flask_app.run()`; the `--host`/`--port` CLI
  contract is unchanged.
- `--timeout 300` was a deliberate choice, not gunicorn's 30s default: the
  `/brief/evolved` route's real LLM calls run 50-260s (MSN-0329 Phase 3) and
  the default would kill them mid-flight. `--worker-class gthread --threads
  4` reproduces the old `threaded=True` "one slow request shouldn't stall
  `/health`" property.
- `platform-runtime/requirements.txt` gets `gunicorn>=23.0.0` appended.
- `deploy/context-service.service`'s `ExecStart` now invokes
  `platform-runtime/.venv/bin/gunicorn` directly against
  `context_service:create_app()`, preserving the existing `127.0.0.1:5001`
  bind.

**Evidence, real (not simulated) verification since this sandbox cannot run
systemd against the actual VM:**
- `gunicorn --check-config --chdir <repo>/core/context-assembly --pythonpath
  <repo>/core/context-assembly "context_service:create_app()"` → clean exit.
- A real short-lived `gunicorn --daemon` start on a scratch port, `curl
  /health` → real HTTP 200, log confirmed `Using worker: gthread`.
- The actual deploy CLI path (`python3 context_service.py serve --host
  127.0.0.1 --port <port>`) launched gunicorn and served real requests,
  shutting down cleanly on SIGTERM.
- `pytest core/context-assembly/tests/test_health_adjusted_queue.py
  test_number_one_brief.py` → 21 passed. `test_captain_brief_integration.py`
  → 20 passed, 12 skipped offline; re-run with a live gunicorn instance on
  `127.0.0.1:5001` → 9 of those 12 passed, 1 skipped (Slack-token-gated), 2
  failed on corpus-count assertions caused by this isolated build
  worktree's empty missions/ADR corpus — unrelated to the Werkzeug→gunicorn
  change (confirmed the failing assertions are about data volume, not
  server behavior).

## Lesson

A code comment admitting "this isn't a production server" is a known-debt
marker that's easy to walk past once a service is live and stable — nothing
forces revisiting it until load actually breaks it. This capability sat on
the dev server in production for long enough that a specific concurrency
concern (`/brief/evolved`'s long-running LLM calls) had already been solved
around the dev server's own limitation (`threaded=True`) rather than by
fixing the underlying gap.

## Future Guidance

**Required VM step, not automatic:** `pip install -r
platform-runtime/requirements.txt` in the service's venv (installs
gunicorn), `systemctl daemon-reload` (picks up the new `ExecStart`),
`systemctl restart context-service`, then `systemctl status
context-service` — confirm it shows a gunicorn master + `gthread` worker
process tree, not a bare `python3 ... context_service.py serve` process,
and that `/health` (direct and through Caddy) still returns 200. This
cannot be verified from a build sandbox; it is real production risk until
someone with VM access runs it.
