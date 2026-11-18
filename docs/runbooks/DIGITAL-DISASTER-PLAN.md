# Digital Disaster Plan — Personal + GitHub/Hosted Sites

Owner: Tim Ross · Created: 2026-11-18 · Review: every 6 months, and after any incident

> **This file is in a PUBLIC repo.** It contains no secrets, account IDs, recovery codes or phone
> numbers, and must never get them. Anything sensitive lives in the offline "break-glass" kit
> (section 2), and this file only says *where* that kit is.

## 0. How to use this in a crisis

1. Stay calm; don't act on panic. Most digital disasters are slow to get worse, fast to make worse by rushed changes.
2. Find your scenario in section 4. Follow its steps top to bottom.
3. **Contain first, recover second, investigate third.**
4. Write down what you did and the time as you go (paper or a phone note is fine). It helps recovery and any insurer/bank/platform report.

## 1. What we're protecting, and how fast we need it back

| Asset | Where it lives | Impact if lost | Target recovery (RTO) | Max data loss (RPO) |
|---|---|---|---|---|
| Primary email (the "master key": resets everything) | Outlook/Microsoft account | **Critical**: all account resets flow through it | 4 h | n/a |
| GitHub account `timjardenross` | github.com | **Critical**: source of truth for all code and sites | 4 h | 0 (git has full copies) |
| Source code: `TJRHQ` (public) + other repo | GitHub, plus clones/backups | High | 24 h | last push |
| Hosted sites / apps (Vercel, VM + Caddy/Coolify) | Vercel, VM | Medium: public-facing | 24 h | last deploy |
| Database (Supabase) | Supabase project | **High**: not in git | 24 h | 24 h (daily backup), see §3 |
| Secrets (Infisical self-hosted, API keys) | VM, `deploy/infisical` | **Critical** | 24 h | last backup |
| Domains + DNS | registrar / Vercel DNS | High: sites unreachable and email hijack risk | 24 h | n/a |
| Personal files, photos, documents | Google Drive / devices | High (personal) | 72 h | 24 h |
| Password manager | vendor vault | **Critical** | 4 h | n/a |
| Phone / laptop | local | Medium | 48 h | 24 h |

> ⚠️ Fill in the exact accounts, second repo name, and registrar in the **private** break-glass kit, not here.

## 2. Break-glass kit (do this once, this week)

The kit is the single thing that lets you recover when everything else is locked. Keep **two copies in different places** (e.g. a fireproof home safe + a trusted person's safe or bank box). Not in email, not in the cloud account you're locked out of.

Contents (printed or on an encrypted USB):

- [ ] Password-manager master password + emergency kit / secret key
- [ ] Recovery codes for: Microsoft/Outlook, GitHub, Google, Vercel, Supabase, domain registrar, Apple/Android, bank-linked 2FA
- [ ] Authenticator-app backup / seed export (or hardware security key #2)
- [ ] **Two hardware security keys** (YubiKey or similar) registered on GitHub, email, and password manager; one carried, one in the safe
- [ ] Infisical `ENCRYPTION_KEY`, `AUTH_SECRET`, `POSTGRES_PASSWORD` (the restore needs the *originals*, see `deploy/infisical/README.md`)
- [ ] restic repository password for `starship-backups-v2` (backups are useless without it)
- [ ] List of every account + its recovery email/phone + registrar contact
- [ ] Contact list: trusted person, bank fraud line, ISP, registrar support
- [ ] A copy of this plan

**Trusted contact:** pick one person who can open the kit if you're incapacitated. Tell them where it is. Write their name in the kit.

## 3. Backup standard (3-2-1)

3 copies, 2 different media/providers, 1 offsite and offline-or-immutable.

### 3a. Code and GitHub sites
- Git already gives every clone a full copy. **Keep at least one up-to-date mirror outside GitHub:**
  ```bash
  git clone --mirror https://github.com/timjardenross/TJRHQ.git
  git -C TJRHQ.git remote update      # run weekly (cron/launchd), keep on a different disk/provider
  ```
  Repeat for every repo. Include issues, wikis and releases via a periodic export (`gh api` or GitHub's migration/export tool) if they matter.
- Add a free second remote (GitLab/Codeberg) as a push mirror for the critical repos.
- **Protect `main`** on every repo: branch protection / ruleset (require PR, block force-push and deletion). Turn on **secret scanning + push protection**, Dependabot alerts (Dependabot updates already configured), and 2FA-only access.
- Tag releases so a known-good state is always addressable.

### 3b. Databases and secrets (not in git)
- **Supabase:** confirm the plan's daily backups/PITR are on; additionally schedule a weekly `pg_dump` to encrypted storage. Test a restore into a scratch project at least **twice a year**.
- **Infisical / VM:** existing nightly encrypted restic → Google Drive job (`deploy/starship-backup.service`) with weekly integrity check (`starship-backup-integrity.service`). Verify both ran: `journalctl -u starship-backup --since "3 days ago"`. Restore drill: restic restore of one volume to a temp dir, twice a year.
- Lesson already learned here: files that existed only on a VM were lost in a cleanup (see `deploy/infisical/README.md`). **If it matters, it is committed or backed up. No exceptions.**

### 3c. Personal
- Documents/photos: cloud + one local/offline copy (external drive, rotated, stored off-site).
- Phone/laptop: encrypted, automatic backups on, "Find my device" on.
- Export password-manager vault (encrypted) quarterly into the break-glass kit.

## 4. Scenarios and playbooks

### S1. GitHub account compromised or locked out — **Severity: Critical**
1. Try recovery: github.com/login → "Forgot password"; use a recovery code from the kit or a hardware key.
2. If you can still get in: change password, **revoke all** sessions, SSH keys, PATs, OAuth apps and GitHub Apps (Settings → Applications/SSH keys/Developer settings), then re-add only the ones you recognise.
3. Review the security log (Settings → Security log) for what changed; check repos for new deploy keys, webhooks, Actions secrets, collaborators and workflow files.
4. **Rotate every secret** any repo or Actions workflow could read (assume exposed): Supabase keys, Vercel tokens, API keys (Infisical is the root; rotate there then propagate).
5. If code was altered or deleted: restore from your mirror (§3a), force-push only to a repo you've confirmed is clean; check recent commits on `main` for malicious changes.
6. Can't get in at all: GitHub Support account-recovery form, with proof of ownership. Meanwhile, deploy from the mirror to keep sites alive.

### S2. Primary email compromised — **Critical (everything resets through it)**
1. From a clean device, recover the account via Microsoft recovery flow; change password, enable hardware-key/authenticator 2FA, remove unknown forwarding rules, inbox rules, connected apps and recovery methods.
2. Then, in order: password manager → GitHub → Google → Vercel/Supabase → registrar → banks. Change passwords and check each account's recovery email.
3. Tell your trusted contact and, if financial accounts were reachable, call your bank.

### S3. Hosted site down, defaced, or deploy broken — **High**
1. Check status pages (Vercel, GitHub, Supabase, registrar) first: is it them or you?
2. Last deploy broke it → **roll back** (Vercel: promote previous deployment / `request_rollback`; VM: redeploy previous git tag).
3. Defacement or malicious code → take site offline (pause the Vercel project or return a static maintenance page), then follow S1 (assume repo or token compromise), rotate tokens, redeploy from a clean tag.
4. Traffic attack → enable Vercel Attack Challenge Mode / firewall rules.
5. Post a short status note wherever your users look.

### S4. Domain or DNS hijacked / expired — **High**
1. Log into the registrar; lock the domain; enable registrar lock + 2FA; verify nameservers and DNS records match the known-good list you keep in the kit.
2. Contact registrar support if transfer was initiated. Turn on auto-renew and registry lock where offered; renewal must go to a card that isn't about to expire.
3. Keep a **zone-file export** of DNS records in the kit (quarterly).

### S5. Secrets leaked (key committed, token exposed) — **High**
1. **Revoke/rotate first**, delete the commit second (deleting doesn't un-leak, since public repo history is scraped within minutes).
2. Rotate at the provider, update in Infisical, redeploy.
3. Check provider logs for unauthorised use. Clean history with `git filter-repo` only after rotation, and tell collaborators to re-clone.
4. Add/verify secret-scanning push protection so it can't recur.

### S6. Database lost or corrupted (Supabase) — **High**
1. Stop writers if corruption is ongoing (pause the app/cron).
2. Restore from Supabase PITR/backup into a **new** project or branch; verify row counts and spot-check data before cutover.
3. Repoint env vars (via Infisical → redeploy). Take a backup of rows before any repair, as the repo's own data-fix convention requires.

### S7. VM / self-hosted services lost — **High**
1. Provision a new VM; install Docker, Caddy, Coolify, restic and rclone.
2. Clone `TJRHQ`; restore secrets store from restic using the kit's repo password; restore Infisical volumes and `.env` (original encryption key required).
3. Bring services up via `deploy/` units in dependency order (Infisical → Supabase-dependent services → model-router → web/Telegram services). Verify each with its own health check.
4. Revalidate DNS/Caddy certs.

### S8. Lost / stolen device — **High**
1. Remote lock/wipe (Find My / Find My Device / Intune).
2. From another device: revoke that device's sessions in email, GitHub, Google; remove its SSH keys and PATs.
3. If unencrypted or unlocked at theft: treat as S2 + S1 + S5 (rotate secrets it could hold).
4. Report to police if needed, for insurance.

### S9. Ransomware / malware — **Critical**
1. Disconnect from network immediately; do not pay; don't reboot (it can destroy forensics).
2. Don't log in to anything from that machine. Use a clean device to reset email → password manager → GitHub → everything else.
3. Wipe and reinstall the OS; restore data from backups that were offline or versioned **only after** they're scanned.
4. Rotate every secret the machine ever held.

### S10. Incapacitation / "bus factor" — **Medium**
Trusted contact + kit location documented (§2). Enable Google Inactive Account Manager, Apple Legacy Contact, and a GitHub **successor** (Settings → Account → Successor). List which sites should be kept alive or shut down.

## 5. Preventive controls (the 80% that stops most disasters)

- [ ] Hardware security keys on GitHub, email, password manager, registrar (phishing-resistant; SMS 2FA removed where possible)
- [ ] Unique, manager-generated passwords everywhere; passkeys where offered
- [ ] GitHub: branch protection on `main`, secret scanning + push protection, signed commits, fine-grained PATs with expiry, review installed OAuth apps quarterly
- [ ] GitHub Actions: pin third-party actions to SHAs (Dependabot already manages updates), least-privilege `permissions:` per workflow, no long-lived cloud credentials
- [ ] Registrar lock, auto-renew, DNS export
- [ ] Automatic OS/app updates on
- [ ] Full-disk encryption on phone and laptop
- [ ] Email alerts on: new login, new device, repo permission changes, billing

## 6. Testing schedule

| Frequency | Test |
|---|---|
| Monthly | Confirm backups ran (restic logs, Supabase backup list, mirror timestamp) |
| Quarterly | Clone from the mirror and run the site build; verify recovery codes still work for 2 accounts; export password vault and DNS zone |
| Twice a year | Real restore drill: Supabase to scratch project; restic restore of the Infisical volume; tabletop S1 and S2 aloud |
| After any incident | Update this plan with what was slow, missing or wrong |

## 7. 30-day action list (highest value first)

| # | Action | Time |
|---|---|---|
| 1 | Enable hardware-key/authenticator 2FA on email, GitHub, password manager; save recovery codes into the kit | 1 h |
| 2 | Build and distribute the break-glass kit (§2); name trusted contact | 2 h |
| 3 | Branch protection + secret scanning/push protection on every repo | 30 min |
| 4 | Create a mirror clone + second remote for every repo; schedule weekly refresh | 1 h |
| 5 | Verify Supabase backups on; schedule weekly `pg_dump`; do one test restore | 2 h |
| 6 | Check `starship-backup` timers are firing; store restic password in kit | 30 min |
| 7 | Export DNS zone; enable registrar lock + auto-renew | 30 min |
| 8 | Set GitHub successor and account-inactivity settings | 15 min |
| 9 | Fill in the private asset/account list; schedule the first quarterly test | 1 h |

## 8. Known gaps in this version

- Only `TJRHQ` was inspected; the second public repo and any other sites (hosting, registrar, DNS provider) still need to go in the private asset list.
- RTO/RPO figures are proposed targets, not measured: confirm them in the first restore drill.
- No monitoring/uptime alerts are documented yet (e.g. an external uptime check per site). Worth adding.
