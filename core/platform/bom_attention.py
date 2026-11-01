"""Which Bureau of Meteorology warnings need a human's attention now?

BOM's warning feeds carry no Advice / Watch and Act / Emergency Warning tier
(see intelligence/ingestion/emergency_alert_adapters/bom_warnings.py), so
those alerts are stored with severity 'unknown' — and that stays true: this
module does NOT invent an AWS tier or write one into the database.

What it does instead is a separate, clearly platform-assigned "attention
level" derived from BOM's own product names, used to (a) sort the workbench's
weather-warnings section and (b) decide which BOM warnings trigger an email.
It is a policy choice of this platform, not BOM's judgement, and the UI and
email say so.

  high      the product names an immediate threat to life or property:
            tropical cyclone warnings/watches, severe thunderstorm, severe
            weather, tsunami (unless BOM says "no threat"), and Moderate or
            Major flood warnings.
  standard  everything else BOM publishes here: Minor or unqualified flood
            warnings/watches, fire weather warnings, gale and similar.

Pure string rules over the headline, mirrored client-side by
lcars-portal/src/lib/bomAttention.ts — keep the two in step.
"""

from __future__ import annotations

HIGH = "high"
STANDARD = "standard"


def attention_level(headline: str | None, alert_type: str | None = None) -> str:
    text = (headline or "").upper()
    atype = (alert_type or "").lower()

    if "TROPICAL CYCLONE" in text or atype == "cyclone":
        return HIGH
    if "SEVERE THUNDERSTORM" in text or "SEVERE WEATHER" in text:
        return HIGH
    if "TSUNAMI" in text or atype == "tsunami":
        return STANDARD if "NO THREAT" in text else HIGH
    if "FLOOD" in text or atype == "flood":
        return HIGH if ("MODERATE FLOOD" in text or "MAJOR FLOOD" in text) else STANDARD
    return STANDARD


def attention_label(level: str) -> str:
    return "High attention" if level == HIGH else "Standard"
