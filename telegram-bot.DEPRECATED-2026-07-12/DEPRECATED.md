# DEPRECATED — 2026-07-12

Retired. This is the singular **Chief Engineer** Telegram agent (read-only build-request
logging + `/eng_*` Directed Engineering Operator + advisory commands), run on the VM as
`telegram-chief-engineer.service`.

Retired per Captain's decision (2026-07-05): **XO is the only Telegram bot going forward.**
See `reports/PHASE0-STABILISATION-DOSSIER-2026-07-05.md` §16/§256. At retirement the
service was crash-looping on a missing `python-telegram-bot` dependency and, once that was
fixed, its `TELEGRAM_BOT_TOKEN` was rejected by Telegram (`InvalidToken`). It was
disabled + stopped, not restored. The live bot is `telegram-bots/xo/` (`tg-xo.service`).

At quarantine time it had no systemd service running, was not in the process list, and had
zero live importers. Its one code-reuse edge (`../xo-bot`) already pointed at a directory
that had itself been quarantined (`xo-bot.DEPRECATED-2026-07-05/`, since deleted), so the
read-command path was already broken at runtime.

**Not deleted outright** — quarantined (renamed, not removed) to preserve a recovery window,
matching the Phase-0 convention. It remains the richest reference implementation of the
engineering-operator and advisory command surfaces. Delete in a later pass once confirmed
nothing here is worth porting to `telegram-bots/xo/`.

## Not affected by this retirement (still live)
- `core/coordination/telegram_build_executor.py` + `deploy/telegram-build-executor.service`
  — still `active` on the VM; retirement is a separate, higher-risk mission
  (see `docs/EOS-CANONICAL-ARCHITECTURE-DECISIONS.md` §52).
- Supabase `build_request_inbox`, `intelligence_notes`, role `telegram_engineer_ro`
  — load-bearing for the LCARS portal's Decide/governance and Captain's Notebook flows.
