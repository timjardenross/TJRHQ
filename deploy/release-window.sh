#!/bin/bash
# Release-window helpers shared by deploy/auto-deploy.sh and deploy/sync-self-improvement-state.sh (sourced, not executed).
# Both jobs fast-forward the live working tree from origin, so both must obey the same windows; otherwise one of them
# moves the tree under running services and the restarts deferred by the other leave mixed code versions.
#
# 2026-11-25 (ops): routine release windows (the pull itself is deferred too, see below). 24 Nov saw 26 intelligence-scheduler restarts in one day because every
# merge or same-VM commit that landed in its own 5-minute cycle restarted the stale services separately; batching
# only helped when merges happened to land inside a single cycle. Restarts and the portal rebuild are therefore
# deferred (staleness persists, so nothing is lost) until a routine release window, which caps routine restarts at
# two a day regardless of merge timing:
#   09:30-09:39 and 14:30-14:39 Australia/Melbourne (the 5-minute timer runs at least once inside each).
# Urgent remediation or recovery: touch the flag file below; it counts for 60 minutes, then expires on its own so a
# forgotten flag cannot disable the deferral. The brief-window HOLD further down still applies on top of the flag.
# The `git merge --ff-only` is deferred with the restarts. Pulling now and restarting hours later would leave running
# services on a working tree that has moved under them (lazy in-function imports and every oneshot re-read files from
# disk), i.e. mixed code versions. Between windows the tree stays on one commit; fetch still runs so ahead/behind is
# visible. Commits made directly on this VM already sit at HEAD and cannot be deferred; their services restart in the
# next window (or sooner with the urgent flag).
# Set AUTO_DEPLOY_RELEASE_WINDOWS=0 to switch the deferral off entirely (tests do not need it; operators should not).
RELEASE_WINDOWS="${AUTO_DEPLOY_RELEASE_WINDOWS:-1}"

melbourne_mins() {
  local hm
  hm="${AUTO_DEPLOY_NOW_HHMM:-$(TZ=Australia/Melbourne date +%H:%M)}"   # AUTO_DEPLOY_NOW_HHMM: test override only
  echo $((10#${hm%%:*} * 60 + 10#${hm##*:}))
}

in_release_window() {
  local mins; mins="$(melbourne_mins)"
  # 09:30-09:39 = 570-579, 14:30-14:39 = 870-879
  { [ "$mins" -ge 570 ] && [ "$mins" -le 579 ]; } ||
  { [ "$mins" -ge 870 ] && [ "$mins" -le 879 ]; }
}

urgent_flag_active() {
  local f="${AUTO_DEPLOY_URGENT_FLAG:-${AUTO_DEPLOY_STATE_DIR:-$(git rev-parse --absolute-git-dir)/auto-deploy-state}/urgent-restart}"
  [ -n "$(find "$f" -maxdepth 0 -mmin -60 2>/dev/null)" ]
}

# True when a routine (non-urgent) restart/rebuild must wait for the next release window.
restart_deferred() {
  [ "$RELEASE_WINDOWS" = "1" ] || return 1
  urgent_flag_active && return 1
  in_release_window && return 1
  return 0
}

