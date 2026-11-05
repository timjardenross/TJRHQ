# Unit reconcile and venv freeze — 2026-11-05

Companion PRs: #575 (unit reconcile), #576 (backup freeze). Both draft, not merged. Nothing installed on the VM, nothing restarted.

## 1. Install self-improving-system by replacing it — NOT DONE (gated)

Gate: "only after the Captain says #572 is merged". #572 is still **OPEN** (VERIFIED via `gh pr view 572`) and no merge confirmation was given, so I did not pull, back up, install or `daemon-reload`. Steps are ready when told:

1. `git pull`; `diff deploy/self-improving-system.service /etc/systemd/system/self-improving-system.service` must show only the `ExecStartPre` block and the `After=` line (STOP otherwise).
2. `cp -a /etc/systemd/system/self-improving-system.service /root/unit-rollback-2026-11-05/`
3. Install with the same mode/owner as the old file (installed: 644 root:root; the repo file is 755 in git, so set 644 explicitly), `systemctl daemon-reload`, no restart.
4. Confirm with `systemctl cat ... | grep -E 'ExecStartPre|ExecStart='` and `systemctl list-timers | grep self-improving`. Rollback: copy the saved file back, `daemon-reload`.

## 2. Three units (PR #575, repo only)

| Unit | Outcome | Evidence | Status |
|---|---|---|---|
| auto-deploy | Repo file made byte-identical to installed (re-enables `OnFailure=alert-on-failure@%n.service`; removes the repo-only `ExecStartPre=-+/opt/deploy-guard/repair-git-perms.sh`, which on the VM is supplied by the untracked drop-in `auto-deploy.service.d/repair-git-perms.conf`, along with `repair-tree-perms.sh`) | `diff` clean | VERIFIED |
| governance-cache-sweep | Wrapper + comment match installed. One line differs: `After=... docker.service` added | `diff` shows only that `After=` line. `tests/test_infisical_unit_ordering.py` requires it for any wrapper unit (failed 1/2 without it) | VERIFIED |
| command-bus | **Not changed.** Installed has 3 active raw `EnvironmentFile=-` lines; matching them fails the `no-raw-env-secrets` hook (`tools/check_no_raw_env_secrets.py`, MSN-0371) | I did not bypass or allowlist a deliberate policy hook | VERIFIED (blocked) |

`pytest tests/test_infisical_unit_ordering.py -q`: 2 passed. `systemd-analyze verify`: exit 0 for both changed units. No secret values committed.

Deviation from "match exactly": governance-cache-sweep's `docker.service`. The same trade-off as #572: revert the line and the guard test fails.

### Does the Infisical wrapper cover command-bus's EnvironmentFile= variables?

Method (names and hash-style equality only; no values printed): ran `run-with-infisical-bot.sh xo -- env -0` in an empty environment (what the wrapper alone provides), compared with the variables in `.env` and `platform-runtime/.env`, and compared the live `command-bus` process (`/proc/<pid>/environ`) against both.

- `telegram-bot/.env` does **not exist**, so that line is already a no-op (VERIFIED).
- **Names: yes, fully covered.** `.env` 43 vars and `platform-runtime/.env` 51 vars; 0 names are missing from the wrapper's 112 (VERIFIED).
- **Values: not identical.**
  - `.env`: 37 identical, 6 differ (BRIGHTDATA_API_KEY, BRIGHTDATA_ZONE, GEMINI_API_KEY, GEMINI_BILLING_API_KEY, MISTRAL_API_KEY, MISTRAL_BATCH_API_KEY).
  - `platform-runtime/.env`: 43 identical, 8 differ (BRIEF_CHANNEL, BRIGHTDATA_API_KEY, EMBEDDING_PROVIDER, GEMINI_API_KEY, GEMINI_BILLING_API_KEY, MISTRAL_API_KEY, SUPABASE_ANON_KEY, TELEGRAM_BOT_TOKEN).
- **Correction (2026-11-05, see installs report):** the first version of this section said BRIGHTDATA_ZONE, BRIEF_CHANNEL and EMBEDDING_PROVIDER carried the `.env` value in the live process and that removing the lines would change them. That was wrong: I compared the live process against each `.env` separately, but the two `.env` files **disagree with each other** on those three, and systemd layers them in order. Comparing all three sources, the **live process value equals the Infisical value for all three** (VERIFIED), so removing the `EnvironmentFile=` lines changes none of them today.
- The 7 other differing variables (API keys/tokens) also carry the Infisical value in the live process.

Conclusion: the wrapper covers every variable name and, for every differing one, the live process already uses the wrapper's (Infisical) value. Removing the lines looks safe for these variables; the `.env` files hold conflicting stale values (e.g. EMBEDDING_PROVIDER `ollama` vs `mistral`) and are a hazard if someone relies on them. `command-bus` was started 2026-11-01; a restart would re-read Infisical at that time (UNKNOWN whether Infisical changed since).

## 3. Venv freeze (PR #576)

Change in `deploy/starship-backup.sh`: per venv, `venv-freeze/<slug>.freeze.txt`, `.python.txt`, `.pyvenv.cfg`, plus `.pip-stderr.txt` only if pip wrote anything. pip stderr is separate; failures log `venv freeze failed for <path>: <reason>` via `log` (not `fail`) so the backup still succeeds; the torch/CUDA extra-index note is a comment only.

| Check | Result | Status |
|---|---|---|
| `bash -n` | ok | VERIFIED |
| Failure paths (fake root: pip exit 3, missing venv, empty freeze, missing chatterbox) | 4 `venv freeze failed for ...` lines; block exit 0; error text only in `.pip-stderr.txt`, none in any freeze | VERIFIED |
| Live venvs | 5 ok | VERIFIED |
| Added time | block alone 4.6s; in the full dry run 08:31:49 -> 08:31:53 (~4s). Old chatterbox line ~1s, so net **about +3s** | VERIFIED |
| File sizes | freeze files 13,710 B (platform-runtime 7,625; vm-processing 2,409; chatterbox 2,550; supabase 985; self_improvement 141), plus 5 x 14 B python files and 5 x ~190 B pyvenv.cfg = **14,732 B** total | VERIFIED |
| `DRY_RUN=1` full script from the branch | exit 0, "finished OK", 39.8s total; restic dry-run would add 24.5 MiB (mostly git bundle + dumps); nothing written to the repo | VERIFIED |
| Real nightly run with the new script | not run (not installed; the timer uses `/opt/starship-backup/backup.sh`, currently equal to main's script) | UNKNOWN |

Notes:
- The dry run was launched through `run-with-infisical.sh` for convenience; the real unit runs `/opt/starship-backup/backup.sh` directly (script uses its own wrapper only for the Supabase step). Supabase dump was skipped as cached (53h < 72h), so no egress.
- Earlier UNKNOWN resolved: `reports/vm-audit/backup-verification-20261105.md` row 4 shows the old `chatterbox-venv-freeze.txt` is in the restic snapshot (2,550 bytes, 129 lines, no error lines). I did not re-open restic myself.
- Rename: `chatterbox-venv-freeze.txt` -> `venv-freeze/core_voice_chatterbox-venv.freeze.txt`.
- Python version: all five on system 3.12.3 (`home = /usr/bin`); the version file makes the rebuild interpreter explicit.
- **Caveat on the dry-run listing:** restic's `5/5 retention` dry-run output prints `.env`/`.env.bak` paths (names only). Nothing secret was printed.

## Open decisions for the Captain

1. Tell me when #572 is merged to run section 1.
2. command-bus: allowlist the three `EnvironmentFile=` lines in the hook with justification, or remove them from the live unit (the live values already come from Infisical; see correction above).
3. Installing the backup change means copying `deploy/starship-backup.sh` to `/opt/starship-backup/backup.sh` (not done).
4. Still-open from the drift report: 17 units lacking `After=docker.service`, human-systems-scheduler, starship-meilisearch inline master key.
