# USS-TJR-MSN-0474 - Switch Emergency Alert emails to the ANZ mailboxes (VM mission)

## Mission Header

- **Mission ID:** USS-TJR-MSN-0474 (minted with `python3 tools/mint_id.py MSN`)
- **Priority:** High - live alert delivery
- **Runs on:** the ingestion VM, in the shared checkout at `/opt/starship-endeavour` (read-only for git; see guardrails)
- **Source:** Captain request 2026-11-02. Alert emails now push alerts as-is to a team mailbox that Cowork reads (PR #520 merged). Delivery to the ANZ mailbox was tested with `tools/emergency_alerts/send_test_email.py` and arrived; this mission makes it the live destination.
- **Parameters the Captain supplies when launching (not stored in the repo):**
  - `TEAM_MAILBOX` - the shared team address (primary recipient, `To`)
  - `CAPTAIN_CC` - the Captain's own work address (`Cc`)

## Pre-flight

1. [ ] **Existing-entry check.** The mission edits two existing keys in the ingestion service's environment (`EMERGENCY_ALERT_EMAIL_TO`, `EMERGENCY_ALERT_EMAIL_CC`); it adds no registry rows. Grep for where they are set and record it:
   ```
   systemctl cat <service> | grep -i -E "EnvironmentFile|Environment=|WorkingDirectory|ExecStart"
   grep -rn "EMERGENCY_ALERT_EMAIL" /opt/starship-endeavour/.env /etc/systemd/system 2>/dev/null
   ```
   Record: the service name, the file the keys live in (or "not set"), and the current values of both keys (these are addresses, not secrets, so print them).
2. [ ] **Premise verification.** Verify, do not assume:
   - the service is running the merged code: `git -C /opt/starship-endeavour log -1 --oneline` shows a commit at or after "push alerts to the mailbox as-is, without site matching" (PR #520), and `git -C /opt/starship-endeavour status -sb` is on `main` and clean;
   - `python3 -c "import intelligence.emergency_alerts as ea; print(ea._EMERGENCY_EMAIL_TO, ea._EMERGENCY_EMAIL_CC)"` (run from the checkout) prints what the code will use now - record it as the "before" value;
   - `RESEND_API_KEY` and `RESEND_FROM` are present (check with `grep -c "^RESEND_" <envfile>`; **never print their values**).
3. [ ] **Explicitly not in scope** - see below.

## Explicitly Not In Scope

- Any code change. This is a configuration and verification mission; if the checkout is behind `main`, STOP and report rather than pulling into a dirty or non-`main` checkout.
- Switching branches, `git checkout`, or editing tracked files in the shared checkout (AGENTS.md: the shared checkout is reference-only for interactive sessions).
- Changing `RESEND_API_KEY`, `RESEND_FROM`, silences, alert rules, the site register or the workbench.
- Sending anything to addresses other than `TEAM_MAILBOX` and `CAPTAIN_CC`.
- The NT feed, thunderstorm asthma outside Victoria, ACT structure fires (separate follow-ups).

## Scope / Streams

**Stream 1 - Capture the "before" state (read-only).** Run the Pre-flight commands. Write the service name, env file path, and before-values into the mission notes. Stop if the service cannot be identified.

**Stream 2 - Dry run.** `python3 tools/emergency_alerts/send_test_email.py --to "$TEAM_MAILBOX" --cc "$CAPTAIN_CC" --dry-run` must list six `[TEST]` subjects showing both recipients and **no site content**. Send nothing yet.

**Stream 3 - Change the two settings.**
1. Back up the env file next to itself: `cp -p <envfile> <envfile>.before-anz-switch` (it contains secrets; keep the same permissions; do not print or cat it).
2. Set (replace if present, append if absent): `EMERGENCY_ALERT_EMAIL_TO=$TEAM_MAILBOX` and `EMERGENCY_ALERT_EMAIL_CC=$CAPTAIN_CC`. Use `sed -i` on those two keys only, then show only `grep -n "^EMERGENCY_ALERT_EMAIL" <envfile>`.
3. Re-run the "what will the code use" one-liner; it must print the two new addresses.

**Stream 4 - Restart and confirm health.**
1. **Ask the Captain for explicit confirmation before restarting** (a restart interrupts one 15-minute ingestion cycle).
2. `sudo systemctl restart <service>`; then `systemctl status <service> --no-pager | head -12` and `journalctl -u <service> -n 60 --no-pager`. Look for a clean start and no tracebacks.
3. Within 20 minutes confirm a normal ingestion run in the logs or via the next heartbeat (no new failures).

**Stream 5 - End-to-end confirmation.** With the Captain's confirmation, run `python3 tools/emergency_alerts/send_test_email.py --to "$TEAM_MAILBOX" --cc "$CAPTAIN_CC" --only EW,BOM-HIGH`. Expect `2 sent, 0 failed`. The Captain confirms arrival in both inboxes and that Cowork reads the header block (Alert-ID, Notice, Tier, Jurisdiction, Headline, Location, Issued, Official-Link, Source, Sent-At).

**Stream 6 - Hand over.** Delete nothing automatically. Tell the Captain the backup file path and that it holds the same secrets as the env file (delete it, or keep it with the same permissions, their choice).

## Rollback

`cp -p <envfile>.before-anz-switch <envfile> && sudo systemctl restart <service>`, then re-run the one-liner to confirm the before-values are back. Roll back immediately if the service fails to start, ingestion heartbeats go red after the restart, or the Captain asks.

## Acceptance

- The "what will the code use" one-liner prints `TEAM_MAILBOX` and `CAPTAIN_CC`.
- Service is active after the restart with no tracebacks in the journal, and the next ingestion run completes normally.
- Stream 5 reported `2 sent, 0 failed`, and the Captain confirmed both inboxes received them (not junk or quarantine) and Cowork read the header.
- Before/after values, service name, env file path and the backup path are recorded in the knowledge record. No secret value appears in any output, note or commit.

## Guardrails (read before starting)

- Never print, log or commit `RESEND_API_KEY`, `.env` contents beyond the one `grep` above, or any token.
- Stop and ask the Captain if anything differs from this brief: unknown service name, keys defined in more than one place (systemd drop-in AND `.env`), checkout not on `main`, or tests/send errors.
- The two addresses come from the Captain at launch; do not guess or reuse addresses from older messages or files.

## Reporting

One knowledge record: `knowledge/missions/USS-TJR-MSN-0474-knowledge-record.md` (before/after values, commands run, test output, confirmations, rollback path). No SUOC Platform Registry update needed (configuration only).
