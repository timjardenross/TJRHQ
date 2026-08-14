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
  catch) — and that bias is itself recognised field practice (Crisis Text
  Line, Trevor Project, and the AI-crisis-detection literature all treat
  recall over precision as correct at this tier), not a shortcut. Pattern
  list expanded 2026-08-14 from a best-practices research pass — added
  indirect/euphemistic ideation, chronic-illness/disability-specific
  despair and burden-perception phrasing (the population this bot
  actually serves — the single biggest gap a generic list would have
  had), coded/euphemistic language ("unalive" etc.), and caregiver-strain
  phrasing. Deliberately did NOT add bare method/acquisition nouns
  ("pills", "rope") — too generic to regex without context; the research
  recommends a Layer 2 LLM-based confirmation pass for that
  disambiguation specifically, which is **not built** — logged here as a
  real next step, not silently dropped. Still needs the adversarial
  review the source doc's §8.3 checklist calls for — a wider list isn't
  the same thing as a reviewed one.
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

- [x] Migration `0147_revs_bot_scoped_role.sql` applied to the live
      Supabase project — applied 2026-08-14, verified live (role +
      full CRUD round-trip tested through `revs_bot`).
- [x] Escalation decision made — 2026-08-14: crisis triggers (§5.4a
      language, §5.4b non-text) now alert the Captain via XO's own bot
      identity/chat (`escalate.py`, `notify_captain()`), fire-and-forget
      after the user's own resources message is sent. Reads XO's
      credentials directly from `telegram-bots/xo/.env` — no new secret
      duplicated into this bot's own `.env`. Untested against a live
      Telegram send (credentials verified present, HTTP call not yet
      fired for real) — worth one manual trigger before relying on it.
- [x] Crisis classifier pattern list expanded from a best-practices
      research pass (see "Known gaps" above) — still needs the
      adversarial review itself, and a Layer 2 LLM confirmation pass is
      a recommended-but-unbuilt next step for the method/acquisition
      phrasing a keyword list can't safely cover without false-positive
      blowup.
- [ ] Emergency numbers (§1.2b/§5.4a) verified current per locale — AU
      now includes Lifeline/13YARN/Beyond Blue with websites, not just
      phone numbers (2026-08-14). UK/US still phone-only, unchanged.
- [ ] PEM copy (§1.3, §4.2, §7.2) reviewed against TRAIN-05 by Tim —
      **on hold**, TRAIN-05 isn't in any repo I have access to
      (TJRHQ / USSTJROS / tjrmindbody_public — checked 2026-08-14).
- [x] §7.4 default regulation instructions — REG-002 also isn't
      accessible (same check, 2026-08-14), so the instructions
      themselves are unchanged from v1 (each already maps to a
      widely-recognised regulation technique — see the comment above
      `DEFAULT_REGULATION` in `copy_bank.py` for which). Didn't invent
      new clinical content without a source to check it against — Tim's
      review against REG-002 is still the real close-out here, just a
      faster one now that the technique mapping is documented inline.
- [x] Privacy Policy updated —
      `tjrmindbody_public:public-site/content/pages/privacy-policy.md`,
      commit `14b0b74`, 2026-08-14. Covers what's collected, retention
      rationale, `/mydata`/`/deleteme`, and the crisis-escalation note.
- [x] `/mydata` and `/deleteme` tested end to end — 2026-08-14, through
      the actual command handlers (not just `db.py`) against the live
      scoped client: export contains all 5 child tables with correct
      counts, deletion verified empty across all 6 tables afterward.
- [ ] `deploy/revs-bot.service` installed and `tg-revs.service` started
      (**not done by this build, intentionally**)

Still open before this talks to a real user: emergency-number freshness
check, PEM/REG-002 copy review (blocked on getting those source docs),
adversarial review of the crisis classifier, and a live-fire test of the
XO escalation path.
