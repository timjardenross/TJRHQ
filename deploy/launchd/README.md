# Mac Automation — USS-TJR-MSN-0207A

Turns the first two stages of the document intake pipeline from a manual,
human-invoked (or Claude-invoked) CLI sequence into a scheduled, unattended
macOS LaunchAgent. Normal operation should require no Captain or Claude
involvement at all — this directory is the "wiring," not new pipeline logic.

## What this chains

Two already-built, already-tested CLI tools, run in order by
[`run_knowledge_collection.sh`](./run_knowledge_collection.sh):

1. **Mac Collector Agent** — [`core/infrastructure/mac-collector`](../../core/infrastructure/mac-collector/README.md)
   `python cli.py scan` then `python cli.py export-manifest`
2. **Secure File Transfer to VM** — [`core/infrastructure/vm-transfer`](../../core/infrastructure/vm-transfer/README.md)
   `python cli.py transfer --manifest <path from step 1>`

Nothing downstream of the transfer (extraction, OCR, classification,
eligibility filtering, memory ingestion — `vm-processing`, `lcars-portal`)
is touched by this automation; those already run as their own VM-side
process, independent of this schedule.

## Where the safeguards actually live (read this before "fixing" anything)

This script calls both tools with their **default configuration** and never
passes a flag that would relax either of these two properties:

- **Cloud-aware collection** (OneDrive/iCloud placeholder files are never
  hashed/tracked) is implemented inside `mac-collector`'s `Collector.scan()`
  / `cloud_detection.py`, and is on by default (`ignore.include_cloud_only:
  false`). This script does not detect placeholders itself and does not
  need to — it inherits this behaviour simply by not overriding it.
- **Content eligibility** (excluding ebooks, temp files, junk) is enforced
  **server-side, on the VM**, by `vm-processing`'s `eligibility.py`, after
  files have already arrived in `inbox/received/`. This script's job ends
  at a successful rsync + checksum verify — it does not and should not
  attempt to replicate eligibility logic on the Mac side.

If you're reading this because you're wondering "where should I add
duplicate-file or ebook filtering to the launchd script" — don't. It
belongs in one of the two places above, not here.

## Files in this directory

| File | Purpose |
|---|---|
| `run_knowledge_collection.sh` | Wrapper script: chains scan → export-manifest → transfer, with locking, logging, and a clean skip when there's nothing to send. |
| `com.usstjr.knowledge-collection.plist` | LaunchAgent definition — runs the wrapper on a schedule. |
| `README.md` | This file. |

## Prerequisites (must already be done — this automation does not set these up)

Both tools need their own machine-specific setup completed first, per their
individual READMEs:

- `core/infrastructure/mac-collector/`: `.venv` created, `pip install -r
  requirements.txt` run, `config.yaml` copied from `config.example.yaml`
  with real OneDrive/iCloud source paths confirmed.
- `core/infrastructure/vm-transfer/`: `.venv` created, `pip install -r
  requirements.txt` run, `config.yaml` copied from `config.example.yaml`
  with the real VM host/user/SSH key/base path, and that SSH key already
  authorized on the VM (key-based auth only, `BatchMode=yes` — no
  interactive password prompt is possible from a LaunchAgent).

If either `config.yaml` is missing, `run_knowledge_collection.sh` fails
fast with a clear error before touching anything (see "Fails fast on setup
gaps" below).

## Deployment

1. **Edit the placeholders.** Both files have machine-specific paths that
   must be filled in for the deployment machine:

   - In `com.usstjr.knowledge-collection.plist`: replace every
     `REPLACE_WITH_REPO_ROOT` with the absolute path to this repo checkout
     (e.g. `/Users/yourname/Documents/GitHub/USSTJROS`), and every
     `REPLACE_WITH_USERNAME` with the deployment account's username.
   - `run_knowledge_collection.sh` does **not** need editing for a normal
     deployment — its `REPO_ROOT` default already matches this checkout,
     and it also accepts `USSTJR_REPO_ROOT` / `USSTJR_MAC_COLLECTOR_VENV`
     / `USSTJR_VM_TRANSFER_VENV` as environment overrides, which is exactly
     what the plist's `EnvironmentVariables` block sets. If you deploy this
     repo somewhere other than this checkout's path, editing the plist's
     `EnvironmentVariables` is sufficient — you should not need to touch
     the script.

2. **Copy the plist into place:**

   ```bash
   cp deploy/launchd/com.usstjr.knowledge-collection.plist \
      ~/Library/LaunchAgents/com.usstjr.knowledge-collection.plist
   ```

   (Copy, not symlink — `launchd` is picky about symlinked agent files on
   some macOS versions.)

3. **Load it:**

   ```bash
   launchctl load -w ~/Library/LaunchAgents/com.usstjr.knowledge-collection.plist
   ```

   `-w` clears any previous "disabled" override for this label. Loading
   does **not** run the job immediately (`RunAtLoad` is `false` by design —
   see the plist's comments) — it just registers the schedule.

4. **Remove it** (uninstall):

   ```bash
   launchctl unload ~/Library/LaunchAgents/com.usstjr.knowledge-collection.plist
   rm ~/Library/LaunchAgents/com.usstjr.knowledge-collection.plist
   ```

## Schedule

`StartCalendarInterval` fires at **08:00, 14:00, 20:00, and 02:00** local
time (four times/day). `StartInterval` (a rolling "every N seconds since
load") was deliberately not used — it drifts over time and, worse, if the
Mac is asleep across a whole interval boundary, launchd can fire a backlog
of missed runs back-to-back on wake. `StartCalendarInterval` instead fires
once for each specific wall-clock trigger, and if the Mac was asleep at
that exact time, launchd runs it once shortly after wake — no pile-up.

Reasoning for the specific cadence: this is a personal, single-user intake
pipeline, not a latency-sensitive service. A same-day (not same-minute)
turnaround from "file lands in OneDrive/iCloud" to "arrived on the VM" is
sufficient. Three runs across the working day plus one overnight run
(02:00, to catch anything that synced late, e.g. an overnight phone
backup) was judged to comfortably balance freshness against not polling a
human-speed data source unnecessarily. See the cadence comment block in
the plist itself for the full reasoning if you want to change it.

## Verifying it's running

```bash
# Confirm launchd knows about the job (shows PID if currently running,
# last exit code if not, empty output if not loaded at all)
launchctl list | grep usstjr

# Tail the wrapper script's own narrative log (stage-by-stage progress,
# skip/failure reasons, timestamps)
tail -f ~/Library/Logs/starship-knowledge-collection.log

# Tail launchd's raw stdout/stderr capture (catches problems that happen
# before the wrapper's own logging starts, e.g. "no such file")
tail -f ~/Library/Logs/starship-knowledge-collection.launchd.log
```

### Trigger a manual one-off run (for testing)

```bash
launchctl start com.usstjr.knowledge-collection
```

This runs the job immediately, exactly as if a scheduled trigger had fired,
without waiting for the next `StartCalendarInterval` slot. On macOS
versions with the newer `launchctl kickstart` subcommand (per-user domain
form), the equivalent is:

```bash
launchctl kickstart gui/$(id -u)/com.usstjr.knowledge-collection
```

Either way, check the two log files above afterward to see what happened.

You can also just run the wrapper script directly, bypassing launchd
entirely, which is often the fastest way to test changes:

```bash
deploy/launchd/run_knowledge_collection.sh
```

## Operational behaviour

- **Fails fast on setup gaps.** If either tool's `.venv` or `config.yaml`
  is missing, the script exits `1` immediately with a clear message,
  before running anything.
- **Stops on first failure.** `set -euo pipefail` plus explicit exit-code
  checks after each stage mean a failed `scan` never proceeds to
  `export-manifest`, and a failed `export-manifest` never proceeds to
  `transfer` — no stage runs against stale or missing output from a failed
  prior stage.
- **Skips the transfer cleanly when there's nothing to send.**
  `export-manifest` always exits `0` and reports `file_count` in its JSON
  output even when it's `0` (nothing new since the last scan). The wrapper
  parses that count and, if it's zero, logs "nothing to transfer" and exits
  `0` without invoking `vm-transfer` at all — it never calls `transfer`
  against an empty or non-existent manifest.
- **Won't overlap with itself.** See "Locking" below.
- **Logs everything.** All stdout/stderr from both tools, plus the
  wrapper's own stage narrative, is timestamped and appended to
  `~/Library/Logs/starship-knowledge-collection.log` (configurable via
  `USSTJR_KNOWLEDGE_COLLECTION_LOG`).

## Locking

macOS does not ship a GNU-compatible `flock(1)` binary as part of the base
OS (verified on this deployment machine — `which flock` finds nothing;
Homebrew's `util-linux` doesn't add one to `PATH` by default either), so
this script does not depend on it. Instead it uses the classic `mkdir`
lock pattern: `mkdir` is atomic on every filesystem bash runs on, so
exactly one concurrent invocation can succeed in creating the lock
directory (default `~/Library/Application Support/starship-knowledge-
collection/run.lock`, configurable via `USSTJR_KNOWLEDGE_COLLECTION_LOCK`).
A losing invocation logs that another run holds the lock and exits `0`
(not an error — "someone else is already doing this" is an expected,
harmless outcome, not a failure). If the lock directory exists but the PID
recorded inside it is no longer running (e.g. the machine lost power
mid-run), the next invocation detects the stale lock, reclaims it, and
proceeds normally.

## Testing performed

No `launchctl load` was run against a real `~/Library/LaunchAgents/`
during development of this automation (out of scope per this work's
instructions). Instead, the wrapper script's control flow was validated
directly against stub replacements of both tools' `cli.py` (fake venvs,
fake `config.yaml`, fake `cli.py` scripts returning canned JSON/exit
codes for `scan` / `export-manifest` / `transfer`), covering:

- Empty manifest (`file_count: 0`) → transfer stage skipped, exit 0.
- Non-empty manifest → transfer stage invoked with the correct
  `--manifest` path, exit 0.
- `scan` returning a non-zero exit (errors present) → chain stops before
  `export-manifest`/`transfer` run at all, exit 1.
- A live, currently-held lock → contending invocation logs and exits 0
  without touching the lock or running any stage.
- A stale lock (recorded PID no longer running) → reclaimed automatically,
  run proceeds normally.

This was judged sufficient given the small, mostly-linear control flow;
writing a full automated test harness (pytest + subprocess stubs, or a
bats suite) for a ~200-line orchestration shell script was judged
disproportionate scaffolding for what it would additionally catch beyond
the manual scenarios above. If this script grows materially more complex,
revisit that call.
