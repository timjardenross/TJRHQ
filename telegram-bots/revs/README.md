# REVS Bot

Standalone Telegram bot delivering the REVS coaching framework to
end users (`@tjrmindbody_bot`). Built from `REVS_Telegram_Prompt_Library.md`
v1.1 and `REVS_Telegram_Worksheet_Mapping.md` (TJRHQ repo root, added
2026-08-14). Pilot scope only — see §8.1 in the source doc and "Scope"
below.

## Why a standalone bot, not part of XO

XO (`telegram-bots/xo/`) is hard-allowlisted to a single Telegram
`chat_id` — the Captain — and runs with full host/shell control
(`_global_auth_gate` in `xo/app.py` silently drops every other chat).
This bot talks to the public and stores health-adjacent data (PEM status,
crisis flags, free text). Routing that traffic through XO's process would
put stranger input inside the same trust boundary as mission-governance
and host commands. So: separate token, separate systemd unit
(`deploy/revs-bot.service`, **not installed by this build**), separate
scoped Postgres role (`revs_bot`, migration
`0147_revs_bot_scoped_role.sql`, **not yet applied**), no service_role
fallback (see `scoped_supabase.py`'s docstring — a misconfigured scoped
credential here must fail closed, not silently grant a public bot access
to all ~112+ platform tables).

Naming note: `/revs_generate` already exists on XO (`xo/app.py`) and means
something unrelated — it triggers `services/revs-content-agents`, a
Captain-only marketing-asset pipeline. No code or table overlap with this
bot; flagged only because of the shared "REVS" name.

## Scope (pilot — §8.1 of the source doc)

**Built:** full onboarding (§1), daily AM/PM check-ins + What Held add-on
(§2), weekly review (§3.1), `/tools` `/pace` `/setback` `/pem` `/stage`
`/mydata` `/deleteme` `/quiet` `/pause` `/resume` `/whatheld`, safety
triggers §5.1 (downward trend), §5.4a/b/c (crisis language/non-text/
re-contact), §5.5 (silence), §5.6 (PEM re-screen), §5.7 (storage-time
screening).

**Deferred to v2, per the source doc:** RECOGNISE loop generation
(Part 6), `/expand` (§4.4) and everything gated behind it, monthly review
(§3.2), early-warning matching (§5.2) and repeating-cause (§5.3) — these
need weeks of real check-in data to mean anything. There is no `/expand`
handler at all, not even a stub.

## Known gaps / rough edges (read before going live)

- **Crisis classifier (`safety.py`) is keyword/regex, not ML.** Biased
  toward over-triggering on purpose (false positive = one extra gentle
  message; false negative = the thing the whole safety layer exists to
  catch). Still needs the adversarial review the source doc's §8.3
  checklist calls for.
- **Q4 system rotation (`weekly.py`) only has names for 6 of the 12 REVS
  capacity systems** — the source docs name systems 3, 6, 8, 9, 11, 12 by
  number; the full 1–12 registry lives in a framework doc (REG-001 or
  similar) not provided alongside these two files. Others render as
  "System N" until that's wired in.
- **§7.4 default regulation instructions are explicitly placeholders**
  per the source doc, pending Tim's review against REG-002.
- **§4.6 stage-advance gate is not implemented** — `/stage` lets a user
  change stage freely with no minimum-duration warning. Low-risk while
  `/expand` (the thing that gate mostly protects) is deferred, but should
  land before REBUILD-track users show up for real.
- **Weekly trend lines (rows 5/6 of the §3.1 pattern-line table)** always
  fall through to "Mixed week" — the previous week's matched/logged
  snapshot isn't persisted yet, so "steadier/less steady than last week"
  can't be computed. Needs a small migration addition, not a safety gap.

## Running locally

```bash
cd telegram-bots/revs
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN
bash start.sh
```

`SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_JWT_SECRET` are read from
`platform-runtime/.env` (same two-file precedence as `tg-xo.service` —
see `config.py`), not duplicated into this bot's own `.env`.

**Will refuse to start** until migration `0147_revs_bot_scoped_role.sql`
has been applied to the live Supabase project — `scoped_supabase.py`
verifies the `revs_bot` role with a live query before handing back a
client, and `app.py` exits rather than run unscoped.

## Launch blockers (ported from the source doc's §8.3, not yet cleared)

- [ ] Migration `0147_revs_bot_scoped_role.sql` applied to the live
      Supabase project (**not done — written, not run**)
- [ ] Escalation decision made and documented — automated-only vs a human
      (Tim) getting paged on §5.4a. The source doc calls this the largest
      unmitigated risk in the product; still open.
- [ ] Crisis classifier reviewed/hardened past the keyword-list MVP
- [ ] Emergency numbers (§1.2b/§5.4a) verified current per locale
- [ ] PEM copy (§1.3, §4.2, §7.2) reviewed against TRAIN-05 by Tim
- [ ] §7.4 default regulation instructions reviewed against REG-002
- [ ] Privacy Policy on tjrmindbody.com updated to cover Telegram
      check-in data (page already exists:
      `public-site/content/pages/privacy-policy.md` in `tjrmindbody_public`)
- [ ] `/mydata` and `/deleteme` tested end to end against the live schema
- [ ] `deploy/revs-bot.service` installed and `tg-revs.service` started
      (**not done by this build, intentionally**)

Do not point this bot at real users until the escalation decision and the
crisis-classifier review are both closed.
