# Knowledge Record — Arize Phoenix LLM observability, live 2026-09-12

| Field | Value |
|---|---|
| Mission ID | none (ad-hoc "finish what's built" task, OSS-Gap-Solutions GAP 2) |
| Title | The stated gap ("no systemd unit") was real but not the whole story |
| Date | 2026-09-12 |
| Lesson | LL-145 |

## Outcome

Requested: turn on Arize Phoenix per `knowledge/OSS-Gap-Solutions-2026-08-23.md`
GAP 2 — described as purely "collector installed and instrumented, nothing
listening." `arize-phoenix 20.3.0` was confirmed already installed in
`platform-runtime/.venv`. `tools/start-phoenix.sh` worked as written.

Adding only a systemd unit would not have closed the gap. On investigation,
a second, independent problem existed: all 7 `configure_tracing()` call
sites import `platform_runtime.lib.telemetry` (underscore) but the
directory on disk is `platform-runtime` (hyphen) — that import has
apparently never resolved for any of them, each silently swallowed by its
own `try/except Exception`. Historical spans in `~/.phoenix/phoenix.db`
stop dead at 2026-08-29, consistent with whatever earlier state made the
import work (a since-removed symlink, an old directory name, or an editable
install that didn't survive a venv rebuild) breaking silently on both
counts at once, with nothing anywhere logging the failure.

Fixed both:
1. `deploy/phoenix.service` (systemd unit, tracked, named to match this
   repo's no-prefix convention — `model-router.service`, `xo-bot.service` —
   not the ad-hoc `starship-phoenix.service` that was already running
   untracked when this task started; swapped it out for the tracked unit
   without losing the existing `~/.phoenix` trace store).
2. Two symlinks — `platform_runtime -> platform-runtime` at repo root
   (tracked in git) and the same target inside
   `platform-runtime/.venv/lib/python3.12/site-packages` (untracked,
   `.venv/` is gitignored — self-healed instead by `tools/start-phoenix.sh`
   checking and recreating it on every start). Zero changes to any of the
   7 call sites — this is a packaging/environment gap, not an
   instrumentation gap.

Verified end-to-end: restarted `model-router.service`, `tg-xo.service`, and
`intelligence-scheduler.service`; a real call to
`POST /api/model/classify-capture` produced a `router.classify-capture`
span with real attributes (`task_type`, `model=gemma3:4b`, `duration_ms`,
`success=true`) visible in the Phoenix UI's `starship-endeavour` project —
the first new span since 2026-08-29.

## Lesson

A gap-solutions audit that names one visible symptom ("nothing is
listening on the collector's port") can be correct about that symptom
while still describing an incomplete fix — a second, silent failure one
layer upstream (every producer's own import of the tracing helper) meant
the collector could have been running for weeks with zero data ever
reaching it. Both failures shared the same shape: a `try/except Exception:
pass`/`return` guard with no log line on the failure path, which is
exactly the design that makes "confirm the write-up's own root cause
before implementing its fix" worth doing even when the write-up looks
complete and the constraints explicitly say not to touch the producers.

## Future Guidance

Any cross-cutting `try/except Exception` around an optional feature (here:
`configure_tracing()`'s import guard, repeated identically at all 7 call
sites) should log the swallowed exception at least once, even as a
one-line WARNING — "tracing unavailable: <reason>" would have surfaced
this exact `ModuleNotFoundError` for months instead of it being
indistinguishable from "packages intentionally absent." Silence on a
guarded failure path is cheap to add and is the only way to tell
"working as designed" apart from "broken since the last unrelated
directory rename."
