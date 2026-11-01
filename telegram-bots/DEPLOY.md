# Telegram Bot Deployment — superseded

This was a one-time bootstrap task-log (branch `claude/sweet-shannon-npafr5`,
manual venv/BotFather setup for 3 bots) from an early stage of the project.
Every fact in the original version is now stale:

- Chief Engineer (`@Starship_ChiefEngineer_bot`) and Engineering Dept
  (`@starship_endeavour_bot`) were both retired 2026-09-15 — **XO is the
  only bot with host/shell action capability** (REVS and CapacityBot are
  separate, non-action, still-live bots — see `USS-TJR-Control/README.md`).
- The manual `python3 -m venv` / `bash start.sh` bootstrap steps are
  superseded by systemd (`tg-xo.service`, `tg-revs.service`,
  `tg-capacitybot.service`).
- `/recovery_status`, `/recovery_pulse` are not registered commands in the
  live XO bot — `recovery_pulses` was retired in favor of
  `capacity_checkins` (MY CAPACITY TODAY migration, 2026-08-22).

For current bot deployment/config, see:
- `deploy/README-xo-bot.md` — XO's real command set, security model, install.
- `USS-TJR-Control/README.md` — whole-platform service/bot topology.

Original content preserved in git history if the bootstrap-task format is
ever useful as a template again.
