# Builds the three briefs in memory ONLY. No Telegram/email/scheduler/heartbeat call is made; prints sizes and booleans, never content.
import os, sys
sys.path[:0] = [".", "platform-runtime"]
for k in [k for k in os.environ if k.startswith(("BRIEF_", "COMMS_EDITORIAL"))]: os.environ.pop(k)
import intelligence.captains_brief as cb
m = cb.generate_morning_brief(); w = cb.generate_weekly_report()
for name, t in (("morning", m), ("weekly", w)):
    assert t and "EVIDENCE-BASED" not in t, name
    print(f"S6 {name}: built, {len(t.splitlines())} lines, new evidence section absent: PASS")
assert "Not enough observations" not in w and "future-dated" not in w, "weekly capacity correction is active but its flag is off"
print("S6b weekly capacity block is the legacy form: PASS")
import human_systems_scheduler as hs
msg = hs._build_message("comms_weekly")
if msg is not None: assert "EVIDENCE-BASED" not in msg.body and "Editorial Intelligence" not in msg.body
print("S7 comms_weekly:", "quiet (nothing publishable)" if msg is None else f"built, {len(msg.body.splitlines())} lines, legacy shape: PASS")
