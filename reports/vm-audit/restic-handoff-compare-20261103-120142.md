# Restic handoff compare (read-only) — 2026-11-03 12:01 AEDT

Question: did the 4 locally-modified `ENG-HANDOFF-*.md` files (cleared between 11:45 and 11:50, see PR #548) hold work that is now lost? Compared restic snapshot `afa14ad1` (A) with git `ec7b6eea6^` (B, before the upstream edit) and `ec7b6eea6` (C, upstream edit).

## Answer

**No meaningful local work was lost (VERIFIED for content at 02:42 on 3 Nov; UNKNOWN for anything between 02:42 and 11:50).** The only local difference is a one-line `Batch Status: MERGED` stamp written by `core/coordination/delivery_reconciler.py`. Upstream (C) now holds richer, deliberate closure notes.

**New finding: the same 4 files are dirty again.** The delivery-reconciler (timer every 15 min) fired at 12:01:28 and re-stamped all four back to `Batch Status: MERGED`, overwriting upstream's `CANCELLED` / `COMPLETED`. `git status` shows all 4 modified again. This will re-block auto-deploy the next time an incoming commit touches them, and it undoes upstream's closure statuses on disk. VERIFIED (git status + file content at 12:02). No change was made by me.

## Commands run (read-only)

- Read `/opt/starship-backup/backup.sh` (repo location and password-file mechanism only; nothing printed). Used the same two env settings it uses (repository + password file, values not shown).
- `restic --no-lock snapshots --compact`, `snapshots afa14ad1 [--json]`, `ls -l afa14ad1 | grep ENG-HANDOFF`, `dump <snapshot> <path>` (4 files; plus one of them from 3 earlier snapshots for the status line). `--no-lock` so nothing was written to the repository. No `restore` into any live path; no forget/prune/unlock/check.
- `git show ec7b6eea6^:<path>`, `git show ec7b6eea6:<path>`, `cmp`, `diff -u`, `git log -- <path>`.
- Extraction directory: `/tmp/restic-inspect-20261103-115919` (mode 700). Files treated as data, never executed. Deleted after the push (see end).

## 1. Snapshots

`afa14ad1`: 2026-11-03 02:42:34, host `[redacted]`, tag `starship-nightly`, 99 paths (includes `/opt/starship-endeavour/Missions/Engineering-Handoffs/`). Repository has 10 snapshots in total:

| snapshot | time |
|---|---|
| 622f7459 | 2026-10-10 09:53 |
| 6cb6c624 | 2026-10-18 02:40 |
| c1f657ec | 2026-10-25 02:42 |
| 973b8c44 | 2026-10-28 02:42 |
| b3aaf9d4 | 2026-10-29 02:40 |
| a9de41c8 | 2026-10-30 02:40 |
| e90137e2 | 2026-10-31 02:42 |
| 7214ce0d | 2026-11-01 02:40 |
| 577289c0 | 2026-11-02 02:40 |
| **afa14ad1** | **2026-11-03 02:42** |

No snapshot exists after `afa14ad1`. Older copies do exist: the `Batch Status` line of file `…1790384229152…` reads `DELIVERED` in `b3aaf9d4` and `e90137e2`, and `MERGED` in `577289c0` and `afa14ad1`. So the status stamp first appeared between the 31 Oct 02:42 and 2 Nov 02:40 snapshots. VERIFIED. (Retention is 7 daily / 4 weekly / 3 monthly, so older copies age out.)

## 2. Presence in afa14ad1 (`restic ls -l`)

All 4 files present, all with mtime **2026-11-02 16:12:44**, sizes 1309 / 1455 / 1473 / 1316 bytes. VERIFIED.

## 3. Three-way comparison

| file (MSN id…) | A (snapshot) == B (pre-upstream)? | A == C (upstream)? | live now == C? (at 11:59) | sizes A / B / C |
|---|---|---|---|---|
| …1790384229152-20261028102727 | no (2 lines differ) | no | yes | 1309 / 1312 / 1509 |
| …1790388703110-20261028103831 | no (2 lines differ) | no | yes | 1455 / 1458 / 1565 |
| …1790388714815-20261028104051 | no (2 lines differ) | no | yes | 1473 / 1476 / 1592 |
| …1792890097761-20261028104740 | no (2 lines differ) | no | yes | 1316 / 1319 / 1447 |

Diff B → A (identical shape for all four; 2 changed lines = 1 line replaced):

```
-- Batch Status: DELIVERED
+- Batch Status: MERGED
```

Diff A → C (trimmed; Batch Status line plus an added Closure Note line):

| file | A → C |
|---|---|
| …102727 | `MERGED` → `CANCELLED`; + Closure Note: PR 462 merged a corrupted file (removed in #475), not a bump; platform-runtime already on the right pydantic_core |
| …103831 | `MERGED` → `COMPLETED`; + Closure Note: PR 464 merged a boilerplate note (removed in #475); real bump applied in PR 536 |
| …104051 | `MERGED` → `COMPLETED`; + Closure Note: PR 465 merged a corrupted script (removed in #475); real bump applied in PR 536 |
| …104740 | `MERGED` → `CANCELLED`; + Closure Note: PR 467 merged only a placeholder .patch file; Tailwind 3→4 needs its own mission |

No secret-looking strings appear in the diffs.

## 4. Classification

| file | class | explanation |
|---|---|---|
| …1790384229152-…102727 | **DIVERGENT (trivial, automated)** | differs from B and C only by the `MERGED` status stamp from the delivery reconciler |
| …1790388703110-…103831 | **DIVERGENT (trivial, automated)** | same |
| …1790388714815-…104051 | **DIVERGENT (trivial, automated)** | same |
| …1792890097761-…104740 | **DIVERGENT (trivial, automated)** | same |

Strictly none is IDENTICAL-TO-UPSTREAM or IDENTICAL-TO-PREVIOUS. The "divergent" content is one regenerable line; there is no hand-written note.

## 5. Who writes the stamp, and timing

- `core/coordination/delivery_reconciler.py` (~lines 255–267): for an engineering handoff whose `PR Branch`/`PR URL` maps to a **merged** PR, if `Batch Status` is not `MERGED` it rewrites it to `MERGED` (`_stamp_handoff`). `deploy/delivery-reconciler.timer` runs it every 15 min (`OnUnitActiveSec=15min`) in apply mode. VERIFIED (code + timer).
- All four files carry a `PR Branch` of the form `mistral/ENG-HANDOFF-…`, so the reconciler matches them. At 12:01:28 it ran and the four files went from upstream's `CANCELLED`/`COMPLETED` back to `MERGED` and are modified again (`git status --short Missions/Engineering-Handoffs` lists all four). VERIFIED.
- Timing caveat for the 02:42 snapshot: file mtime in the snapshot is 2 Nov 16:12:44 (the reconciler rewriting it). The snapshot was taken ~10 h later. The files **could** have been edited between 02:42 on 3 Nov and the 11:50 clean-up. `git log` on the path shows only two commits: `e1199fce0` (29 Oct 12:20) and `ec7b6eea6` (2 Nov 22:48 per commit time; reached the VM at 11:50 on 3 Nov), so there are no intermediate commits. Any edits in that window are not captured anywhere I could check. UNKNOWN. Likely just the same reconciler stamp, since the reconciler ran every 15 min through the morning.
- What cleared the files at ~11:50 remains UNKNOWN. Git allows a fast-forward over a dirty file only when the working copy already equals the target, so an actor (not identified) may have set them to the upstream version; the reconciler then re-stamped them at 12:01.

## 6. So what

- **Was local work lost? No (content), unknown (02:42 → 11:50 window).** The snapshot shows the local state was just the automated `MERGED` stamp, and upstream's version is a superset in information (status plus a closure note).
- **Real issue found:** the reconciler and upstream's deliberate closure statuses conflict. Until the reconciler skips handoffs already `COMPLETED`/`CANCELLED` (or the repo records the final status in a way it respects), these four files will be re-dirtied every 15 min and any future upstream edit to them will again abort auto-deploy. Not changed by this report; for a human decision.
- Side note: `restic` access needed no credential exposure; the password file path and repository come from the backup script's own settings.
