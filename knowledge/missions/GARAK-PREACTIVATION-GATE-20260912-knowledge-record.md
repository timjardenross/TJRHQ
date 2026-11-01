# Knowledge Record — garak pre-activation gate added against the local Model Router, 2026-09-12

| Field | Value |
|---|---|
| Mission ID | USS-TJR-MSN-0365 (Stream C) |
| Title | garak wired as a pre-activation vulnerability gate; GAP 1's other half (deepeval) already merged via PR #114 |
| Date | 2026-09-12 |
| Lesson | LL-151 |

## Outcome

`garak` and `deepeval` had both been recommended in the 2026-08-23 audit
(`knowledge/OSS-Gap-Solutions-2026-08-23.md`, GAP 1) and confirmed still
absent from every `requirements.txt` in the repo as of 2026-09-12. PR #114
(merged earlier in this same mission) closed the deepeval half — a real
judge model (`_ModelRouterJudge`) for `score_output()` and its first caller.
This record covers the remaining garak half, PR #170
(https://github.com/timjardenross/TJRHQ/pull/170, merged):

- `platform-runtime/requirements.txt`: appended `garak==0.17.0`.
- New `core/quality/garak_gate.py`: a pre-activation gate that runs garak
  against the local Model Router (`http://127.0.0.1:8891`, confirmed against
  `core/model-router/app.py` and `deploy/model-router.service`) and exits
  non-zero on any confirmed hit.
- **Real-contract discovery, not assumed:** the Model Router has no
  OpenAI-style `/v1/chat/completions` endpoint — `do_POST` in
  `core/model-router/app.py` only exposes task routes speaking `{"prompt":
  str} -> {"success", "response"}`. `garak_gate.py` builds a garak
  `RestGenerator` config against that real contract (default task:
  `xo-response`) instead of assuming an endpoint that doesn't exist.
- **Threshold choice, documented in the script:** zero-tolerance — any
  confirmed hit in garak's own deduplicated `hitlog.jsonl` fails the gate.
  Rationale: `tools/garak_sweep.sh` (the pre-existing periodic sweep) can
  tolerate noise for a human to triage later; a pre-activation gate stands
  between a config and production traffic and shouldn't. Overridable via
  `--max-hits` / `GARAK_GATE_MAX_HITS` for a documented exception.

**Real merge conflict, resolved:** this stream's branch was cut before
Stream B's gunicorn PR merged; both append to
`platform-runtime/requirements.txt`. Per this mission's own directive,
resolved by merging `origin/main` into the branch and keeping both appended
lines (gunicorn, then garak) — no reordering of the rest of the file.

**Evidence:** the Model Router is not reachable from a build sandbox
(`curl http://127.0.0.1:8891/health` → connection refused). Verified in two
real, non-mocked ways instead: (1) running `garak_gate.py --probes
promptinject` against the real router URL — garak's `RestGenerator`
genuinely attempted `POST http://127.0.0.1:8891/api/model/xo-response` and
got a real `ConnectionError`, proving the wiring targets the right
host/path and fails closed rather than passing silently; (2)
`--offline-selftest` (garak's own bundled `test.Blank` generator, no
network) produced a genuine passing garak report under `reports/garak/`
(real probes, real detectors, real run metadata), proving the
run/parse/threshold/report-save code path works end to end.

## Lesson

A gate that has only ever been exercised against a target it can't reach
proves its own wiring is correct but says nothing about what it will
actually find on the real system. That gap is real here and is called out
explicitly rather than implied by "tests pass."

## Future Guidance

**Required VM step, not automatic:** run `python3 core/quality/garak_gate.py`
(no flags) against the actually-running Model Router at `127.0.0.1:8891` to
get a first true pass/fail verdict. Nothing currently wires this gate into
any activation/deploy flow — it is a standalone script today, not an
enforced check (see the new Observability capability record in the SUOC
Platform Registry, added this pass, for the broader tracking of this gap).
Also gitignore `reports/garak/` (added this pass, PR #172) — both this gate
and the pre-existing `tools/garak_sweep.sh` write timestamped reports there,
and neither path had ever been excluded from git.
