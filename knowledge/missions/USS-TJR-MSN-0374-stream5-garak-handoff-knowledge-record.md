# USS-TJR-MSN-0374 — Stream 5: garak_gate.py VM Handoff

Date: 2026-09-13
Scope: Stream 5 ONLY of USS-TJR-MSN-0374 — this is a documentation-only
handoff, not an execution of `core/quality/garak_gate.py`. Explicitly out of
scope: running the script, modifying `garak_gate.py` itself, making it a
blocking gate, and any other stream's work.

## Status: this is a handoff, not a completed run

`core/quality/garak_gate.py` (built under USS-TJR-MSN-0365 Stream C) already
exists — 12KB, executable, with a working `--router-url` CLI defaulting to
`http://127.0.0.1:8891` — but has **never produced a report**.
`reports/garak/` did not exist before this stream; a placeholder tracking
`README.md` has now been added there (see below), but it contains no run
output.

## Why this could not be executed from here

The script targets the local Model Router at `http://127.0.0.1:8891`, which
only runs on the production VM (`deploy/model-router.service`). Confirmed
directly from this sandbox:

```
$ curl -s -m 5 http://127.0.0.1:8891/health
# times out — no router reachable here
```

This stream is therefore not executable outside VM/systemd access, by
design — no attempt was made to work around it (e.g. no fake/local stub
router stood up in its place).

## What was verified (read-only)

Read `core/quality/garak_gate.py` in full. Confirmed:

- The script requires **no code changes** to be run — its `--router-url`
  CLI, `RestGenerator` config builder (matching the router's real
  `{"prompt": str} -> {"success", "response"}` contract), and report-writing
  logic are all already correct and complete.
- `REPORT_DIR = REPO_ROOT / "reports" / "garak"` — the script creates this
  directory itself (`args.report_dir.mkdir(parents=True, exist_ok=True)`) and
  writes three files per run under a `<mode>-<UTC-timestamp>` prefix:
  `<prefix>.report.jsonl` (every probe attempt), `<prefix>.hitlog.jsonl`
  (confirmed hits only, absent if zero), and `<prefix>.run.log` (full garak
  CLI output).
- Exit codes: `0` pass (hits ≤ `--max-hits`, default `0`), `1` fail (hits over
  threshold or garak itself failed), `2` could not run (missing dedicated
  garak venv at `platform-runtime/.venv-garak`, per
  `core/quality/requirements-garak.txt` — kept separate from the main venv
  because garak hard-requires `openai<3.0`).
- `garak_gate.py` was **not** touched — no edits made to it as part of this
  stream (also explicitly out of scope per the mission brief; another
  concurrent session has it mid-edit on a different branch).

## Handoff — exact command for whoever has VM/systemd access

```
python3 core/quality/garak_gate.py --router-url http://127.0.0.1:8891
```

(Equivalent to plain `python3 core/quality/garak_gate.py`, since that's
already the script's default.) Prerequisite — the dedicated garak venv must
exist first:

```
python3 -m venv platform-runtime/.venv-garak
platform-runtime/.venv-garak/bin/pip install -r core/quality/requirements-garak.txt
```

Output lands automatically under `reports/garak/` — no manual save step
needed beyond running it in a checkout where that directory exists (it now
does, tracked via `reports/garak/README.md`). Full detail on output format
and troubleshooting is in that README.

## What this mission deliberately does NOT do

- Does not run `garak_gate.py` against a real router — impossible from this
  sandbox, not attempted.
- Does not modify `garak_gate.py` in any way.
- Does not wire this gate into CI, deploy, or any other blocking pipeline.
  Whether/how to make it a blocking pre-activation gate is a separate,
  future decision — tracked for Observability's Next Planned Evolution, not
  decided or actioned here.

## Follow-ups for future missions

1. Whoever has VM/systemd access: run the handoff command above, save the
   resulting report files under `reports/garak/`, and confirm pass/fail.
2. Once a real report exists, decide (as a separate, deliberate decision —
   not a side effect of running it once) whether `garak_gate.py` should be
   wired as a blocking gate before Model Router config activation, per its
   own stated design intent in its module docstring.
3. Re-check `platform-runtime/.venv-garak` provisioning status on the VM
   before the first real run — this stream could not verify whether it
   already exists there.
