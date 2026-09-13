# reports/garak/ — status

No garak report has been generated yet. This directory previously did not
exist; it is being created now purely as a placeholder tracking entry so the
handoff has somewhere to land its output.

## Why no run has happened

`core/quality/garak_gate.py` (added under USS-TJR-MSN-0365 Stream C) targets
the local Model Router at `http://127.0.0.1:8891`. That router only runs on
the production VM (under `deploy/model-router.service`) — it is not
reachable from a sandbox/dev environment. A direct check from this
environment confirms the point:

```
$ curl -s -m 5 http://127.0.0.1:8891/health
# times out — no router listening here
```

The script itself needs **no code changes**. It already has a working
`--router-url` CLI (default `http://127.0.0.1:8891`), builds the correct
`RestGenerator` config for the router's `{"prompt": str} -> {"success",
"response"}` contract, and writes its own timestamped report files under
this directory (`REPORT_DIR = REPO_ROOT / "reports" / "garak"`, see
`core/quality/garak_gate.py`). It just needs to actually be *run* from a
host that has both VM/systemd access to the router and the dedicated garak
venv (`platform-runtime/.venv-garak`, per
`core/quality/requirements-garak.txt`).

## Handoff command

Whoever has VM/systemd access to the production host should run:

```
python3 core/quality/garak_gate.py --router-url http://127.0.0.1:8891
```

(This is also the script's default `--router-url`, so plain
`python3 core/quality/garak_gate.py` is equivalent.)

Before running, confirm the dedicated garak venv exists and is provisioned —
the script checks this itself and exits with code 2 and setup instructions
if not:

```
python3 -m venv platform-runtime/.venv-garak
platform-runtime/.venv-garak/bin/pip install -r core/quality/requirements-garak.txt
```

If the router isn't up yet, check `deploy/model-router.service` status
first — the gate only *warns* (doesn't hard-fail) on a failed `/health`
preflight and will otherwise proceed and let garak's own connection errors
surface as failures.

## Where the output goes

The script writes its own report files here automatically — no manual
save step is required beyond running it in a checkout where this directory
exists (now true). Per run it produces, under a
`gate-<UTC-timestamp>` prefix (e.g. `gate-20260913T120000Z`):

- `<prefix>.report.jsonl` — every garak probe attempt, regardless of outcome.
- `<prefix>.hitlog.jsonl` — only the confirmed hits (present only if there
  were any); absence of this file means zero hits.
- `<prefix>.run.log` — full stdout/stderr of the underlying `garak` CLI
  invocation.

Exit code: `0` = gate passed (hits at or below `--max-hits`, default `0`,
zero-tolerance); `1` = gate failed (hits over the threshold, or garak itself
exited non-zero); `2` = could not run at all (missing venv/garak install).

An `--offline-selftest` mode also exists (garak's bundled
`test.Blank` generator, no network) to sanity-check the run/parse/threshold
code path without the real router — useful for CI, but **not** a substitute
for the real run above before trusting a green result in production.

## Status

Handoff only. No run has been performed as part of USS-TJR-MSN-0374 Stream
5. This mission does not wire `garak_gate.py` into any blocking CI/deploy
gate — that remains a separate, future decision (see Observability's Next
Planned Evolution backlog).
