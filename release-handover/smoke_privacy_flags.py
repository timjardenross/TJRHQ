import os, sys
sys.path[:0] = [".", "platform-runtime"]
bad = [k for k in os.environ if k.startswith(("BRIEF_", "COMMS_EDITORIAL", "HEALTH_LLM_EXTERNAL"))]
print("S0 flag vars present in this shell (names only):", bad or "none")
for k in bad: os.environ.pop(k)               # evaluate the code's DEFAULTS, independent of this shell
from core.security import personal_data_policy as p
from core.health.health_llm import HealthLLMProvider, external_providers_allowed
assert p.external_ai_allowed() is False and external_providers_allowed() is False; print("S1 default-deny external AI: PASS")
try:
    p.assert_may_leave_host("Captain pain 7/10, slept 4h, CPAP used, nervous system tense", route="smoke"); print("S2 content gate: FAIL (not blocked)"); sys.exit(1)
except p.PersonalDataBlockedError: print("S2 personal text blocked from leaving host: PASS")
names = HealthLLMProvider().permitted_providers()
print("S3 permitted health model(s):", names)
assert not any(n.startswith(("gemini", "mistral")) or p.is_cloud_hosted_model(n) for n in names), names
print("S3 only local models permitted: PASS")
try:
    from intelligence import brief_evidence as be, captains_brief as cb
    from lib.comms import editorial
    have = hasattr(cb, "_capacity_quality_enabled")
except ImportError:
    have = False
if not have:
    print("S4/S5 SKIPPED: #658/#662 code not deployed yet (expected after #661 only)")
else:
    assert not any(be.enabled(b) for b in be.FLAGS) and cb._capacity_quality_enabled() is False and editorial.enabled() is False
    print("S4 all new flags default OFF: PASS")
    assert cb._evidence_lines("morning", 72) == [] and cb._evidence_lines("weekly", 168) == []; print("S5 evidence hooks inert: PASS")
