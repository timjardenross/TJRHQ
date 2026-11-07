# SEC-01 Gate Status Register

**Authoritative record** for the SEC-01 security gates G3, G4 and G5 (self-improvement dashboard credential protection, edge protection, and validation).

Related documents (procedure, not status): `deploy/caddy/RELEASE-RUNBOOK.md`, `deploy/caddy/README-v3.md`, `deploy/caddy/G5-CHECKLIST.md`.

Evidence labels used below:
- **[VERIFIED]** checked directly by the reviewer, read-only, in the review pass recorded here.
- **[OWNER-REPORTED]** reported by the owner or recorded in the runbook from owner observation; not independently re-checked.
- **[NOT VERIFIED]** not checked, or not checkable from the environment.

---

## Summary

| Gate | Status | Closure date (UTC) | Basis |
|---|---|---|---|
| G3 — Credential protection | **CLOSED — owner-accepted historical risk** | 2026-11-07T22:11Z | Owner administrative closure authorization; see Owner acceptance |
| G4 — Edge protection | **CLOSED — owner-accepted alias caveats** | 2026-11-07T22:11Z | Owner administrative closure authorization; see Owner acceptance |
| G5 — Validation and production functionality | **CLOSED — owner-accepted evidence limitation** | 2026-11-07T22:11Z | Owner administrative closure authorization; see Owner acceptance |

Closure in this register is **administrative**. It does not mean every SEC-01 operational follow-up is complete (see Outstanding follow-ups). It does not change the status of any other gate. It does not authorise production changes; `deploy/caddy/RELEASE-RUNBOOK.md` §0 still applies.

---

## G3 — Credential protection

**Status:** CLOSED — owner-accepted historical risk.

### Verified
- **[VERIFIED]** `scripts/self_improvement/dashboard.py` (`_require_si_secret`, registered with `@app.before_request`) enforces `X-Self-Improvement-Secret` on the application: missing value returns 401; comparison uses `hmac.compare_digest`; if `SELF_IMPROVEMENT_API_SECRET` is unset the hook returns 503 for every request (fail-closed). The file defines the only Flask application; the 12 route decorators are on that application.
- **[VERIFIED]** Unauthenticated local requests to `127.0.0.1:8892` (`/api/status`, `/`) return 401 (no credential sent).
- **[VERIFIED]** Live `/etc/caddy/Caddyfile` SHA-256 equals `deploy/caddy/Caddyfile.v3`, and the header-delete directive `request>headers>X-Self-Improvement-Secret delete` is present in the live file.
- **[VERIFIED]** Caddy journal (timestamp check only, no content read): the last line containing the header key name is at 2026-11-07T03:17Z, before the pre-redaction backup `Caddyfile.bak.pre-sec01-l1-logredact-20261107T031843Z` (03:18Z). Zero such lines were found in the dashboard or lcars-portal journals since 2026-11-07 00:00.

### Owner-reported (not independently re-verified)
- **[OWNER-REPORTED]** The previous credential was rotated and revoked.
- **[OWNER-REPORTED]** Mac-side verification of the previous credential returned HTTP 401 for one read-only GET (2026-11-07).
- **[OWNER-REPORTED]** Positive-path check: the replacement credential returns HTTP 200 on the dashboard, verified on the VM (2026-11-07, per `RELEASE-RUNBOOK.md` §10). Not re-run in the closure review, by design (no credential-bearing requests).
- **[OWNER-REPORTED]** 34 historical journal lines contain the revoked credential value. Counted by the owner on the Mac via GPG decryption and SSH journal count, 2026-11-07. Not reproducible on the VM.

### Distinct measurement — not a value count
- **[VERIFIED]** 41 Caddy journal lines (from 2026-11-07 00:00 AEDT, the query window used, through the last such line at 2026-11-07T03:17Z, before redaction) contain the header key name `X-Self-Improvement-Secret`. **This is a header-key-name count. It is not a count of credential-value exposures and must not be read as 41 exposures.** It is not reconciled with the owner's 34 value count.

### Owner acceptance (G3)
- The owner accepts retaining the **34 historical journal lines** reported to contain the revoked credential, without cleanup.
- Residual risk accepted: the revoked credential remains readable in retained historical logs.
- **Historical journals were not deleted or modified** by this closure.
- **Runbook open item 10** (old-value journal count, `RELEASE-RUNBOOK.md` §6.2 and §10) is **administratively resolved by documented exception**, not by deletion and not by proof that the entries are absent. The historical journal entries containing the revoked credential remain retained, and the owner accepted that residual risk.
- Count distinction: the **34** figure is an owner-reported credential-value line count (Mac-side). The **41** figure is a verified header-key-name line count on the VM. The two are different measurements; 41 must not be read as 41 credential-value exposures, and 34 is not reproduced on the VM.

### Outstanding (G3)
- Journal cleanup of historical secret-bearing lines is a **separate** authorisation (`RELEASE-RUNBOOK.md` §8 / §10). Not part of G3 closure.

---

## G4 — Edge protection

**Status:** CLOSED — owner-accepted alias caveats.

### Verified
- **[VERIFIED]** Live Caddy configuration SHA-256: `a90ce2d7890086a5fdb8a3a59bd9ec9e9f71baceb558d09ed9d9513fc40f267e` (matches `deploy/caddy/Caddyfile.v3`).
- **[VERIFIED]** The v3 configuration restricts the four write paths by method (OPTIONS denied; non-GET/HEAD/POST denied; POST denied for non-allowlisted paths) and by header presence (POST without `X-Self-Improvement-Secret` denied at the edge), for both public host blocks.
- **[VERIFIED]** Flask validates the credential value independently of Caddy (see G3).
- **[VERIFIED]** Production aliases resolve to the expected deployment (`vercel inspect`, read-only CLI resolution, 2026-11-07):
  - `usstjros.vercel.app`
  - `usstjros-usstjr.vercel.app`
  - `usstjros-git-main-usstjr.vercel.app`

  All three → `dpl_Cs6u7WzNG6oZwbDp2q21pG3D3y5X` (`target: production`, status Ready). Public alias `usstjros.vercel.app` serves the application (`/login` returns 200).
- **[VERIFIED]** Protected Caddy v2 rollback backup exists: `/root/.sec01-caddy-rollback/Caddyfile.v2-redacted-1a309347`, SHA-256 `1a309347d05c5d943f2d3ddf23250bb5a62d40f78b9ca679172d482e08ad2ee6`.
- **[VERIFIED]** `caddy` and `self-improvement-dashboard.service` are active.

### Accepted caveats
- **Conflicting historical alias metadata.** `vercel inspect dpl_A2s7xZipN5hbGvWKD2GUZpftr9wz` (compromised deployment) still displays the three production aliases in its Aliases section. Alias resolution does not route them there. The conflict is unexplained.
- **Compromised deployment reachable directly.** `https://usstjros-jmrf5k1xn-usstjr.vercel.app/` returns HTTP 302 to an unauthenticated HEAD request. It is **not** disabled, deleted or made unreachable by this closure, and no claim is made that it is.
- **Dashboard alias-record verification unavailable.** The Vercel dashboard alias record was not obtained: MCP `get_domain` returned 403 for the production domain. The CLI does not expose the alias owner in the dashboard view.

### Owner acceptance (G4)
- The owner explicitly accepts the three caveats above for G4 closure.

### Prohibitions (not waived by closure)
- **The compromised deployment `dpl_A2s7xZipN5hbGvWKD2GUZpftr9wz` must never be promoted, restored or aliased to production.**
- Do not restore from `/etc/caddy/Caddyfile.bak.pre-sec01*` (pre-redaction).

### Outstanding (G4)
- Clear or explain the stale alias metadata on `dpl_A2s7…` via the Vercel dashboard (owner action).
- Decide whether the compromised deployment should be disabled or deleted (separate owner decision; not performed).

---

## G5 — Validation and production functionality

**Status:** CLOSED — owner-accepted evidence limitation.

### Verified (reproduced in this pass)
- **[VERIFIED]** Fresh `deploy/caddy/g5_validate.sh --live`: **31 PASS, 0 FAIL, exit code 0.**
  - Run: 2026-11-07, approximately 22:07:46–22:07:48 UTC; git HEAD `5783172ea`.
  - Request classes (from script source): GET with no header (7 paths × 2 hosts); OPTIONS on each write path (expect 403); POST on each write path with a **synthetic wrong** header value (expect 401, or 307 → `/login` on the two portal paths, refused before any handler); one loopback GET to `127.0.0.1:8892/api/status` with no header (expect 401).
  - No valid credential was sent. No production write probe was executed. The synthetic value does not appear in the retained output.
- **[VERIFIED]** Dry-run of the same script: sends nothing, exit 0, 32 lines of plan.
- **[VERIFIED]** Tracked on `main`: `tests/test_g5_redirect_policy.py`, `tests/test_g5_validate_script.py`, `tests/test_caddy_rollback_docs.py`.

### Evidence location
- `/root/sec01-g5-final-evidence/` (mode 700, owner root)
  - `MANIFEST.md`: what was executed and what was not, and why
  - `g5_live_run.txt`: command, UTC timestamps, git HEAD, complete sanitised output, exit code
  - `g5_dryrun_plan.txt`: dry-run plan

### Not verified (accepted limitation)
- **[NOT VERIFIED]** "63 additional negative probes" (earlier reported). The exact approved request matrix and retained output were **not recoverable**. The 63 probes are **not independently reproduced or verified** and are not evidence for this closure. No matrix was reconstructed to reach 63.
- **[NOT VERIFIED]** Local pytest tests were **not rerun**: the self-improvement virtualenv lacks pytest, and dependencies were not installed. The test files are tracked, but their results were not reproduced.
- **[OWNER-REPORTED]** Both owner accounts confirmed Findings, Evolution and Handoffs load in production. No decision, approval, acknowledgement or dismissal controls were pressed (per owner report).

**No claim is made that 94/94 (31 + 63) tests, or any 63-probe matrix, were reproduced or verified.**

### Owner acceptance (G5)
- The owner accepts the reproduced **31/31** validator result as sufficient for administrative closure of G5.

### Outstanding (G5)
- Recover or reconstruct the 63-probe matrix only with explicit authorisation and a documented, approved request set. Not performed.
- Run the local pytest suite in a properly provisioned environment, when authorised.

---

## Outstanding follow-ups (separate from administrative closure)

These do **not** reopen G3, G4 or G5 and are not gate failures:

1. Next scheduled auto-deploy execution after checkout reconciliation has not yet been verified.
2. Generated-state files remain modified under their existing sync/deploy policies (`core/mission-control/registry/mission-index.txt`; `.id-counters.json` and `data/self-improvement/review/evolution_summary.json` in recent auto-sync commits).
3. Moving the mission registry mirror outside the checkout is undecided.
4. Temporary recovery files and the runbook backup remain retained.
5. Historical journal lines remain retained under the owner's documented risk acceptance (G3).
6. Compromised deployment `dpl_A2s7…`: stale alias metadata clearance and disable/delete decision (G4).
7. 63-probe matrix recovery and local pytest rerun (G5), if the owner wants them as additional evidence.

## Change control

- This register records closure. It is **not** a deployment, promotion, alias change or credential change.
- Any change to a closed gate requires a new owner authorisation and a new dated entry here.
- Recorded as an owner-authorised administrative closure decision, 2026-11-07T22:11Z. Repository publication is tracked through the associated Git commit and pull request. This entry does not assert that the pull request has merged or that this record is on `main`.
