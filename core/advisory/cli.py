#!/usr/bin/env python3
"""Advisory Runtime CLI — USS-TJR-MSN-0092 / 0093 / 0095 / 0096.

Thin invocation API for non-Python interfaces (the LCARS Portal Node route
shells out to this). Prints JSON (default) or markdown.

Advice / evidence:
    --action advice|challenge|lessons|evidence --question "..."
Loop / measurement:
    --action metrics|calibration|advisory-health
    --action outcome --advisory-id ADV-... --outcome success [--note "..."]
Temporal & pattern intelligence (MSN-0095):
    --action temporal --question "what changed last month?"
    --action episodic --question "..."
    --action patterns|signals|timeline
Proactive intelligence (MSN-0096):
    --action proactive
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _local_import_advisory import import_sibling as _import_sibling  # noqa: E402
invoke = _import_sibling("service").invoke
_lessons = _import_sibling("lessons")  # noqa: E402
import metrics as _metrics  # noqa: E402
import calibration as _calibration  # noqa: E402
_outcomes = _import_sibling("outcomes")  # noqa: E402
import temporal as _temporal  # noqa: E402
import episodic as _episodic  # noqa: E402
_patterns = _import_sibling("patterns")  # noqa: E402
import signals as _signals  # noqa: E402
import timeline as _timeline  # noqa: E402
import proactive as _proactive  # noqa: E402
import advisory_health as _advisory_health  # noqa: E402
_operating_picture = _import_sibling("operating_picture")  # noqa: E402
import wellness as _wellness  # noqa: E402
import strategic as _strategic  # noqa: E402
_forecast = _import_sibling("forecast")  # noqa: E402
_daily_brief = _import_sibling("daily_brief")  # noqa: E402
import data_quality as _data_quality  # noqa: E402
import products as _products  # noqa: E402
import presentation as _presentation  # noqa: E402


def _temporal_route(question: str) -> dict:
    q = question.lower()
    if "preced" in q or "before" in q or "led to" in q:
        return _temporal.what_preceded(question)
    if "begin" in q or "start" in q or "when did" in q or "since when" in q:
        return _temporal.when_did_begin(question)
    if "next" in q or "happens" in q or "usually" in q or "normally" in q:
        return _temporal.what_happens_next(question)
    if "as of" in q or "state at" in q or "was true" in q:
        return _temporal.what_changed(question)  # falls back to change view
    return _temporal.what_changed()


def main() -> int:
    parser = argparse.ArgumentParser(description="USS TJR Advisory Runtime")
    parser.add_argument("--action", default="advice", choices=[
        "advice", "challenge", "lessons", "evidence",
        "metrics", "calibration", "advisory-health", "outcome", "loops",
        "temporal", "episodic", "patterns", "signals", "timeline", "proactive",
        "operating-picture", "wellness", "strategic", "forecast", "daily-brief",
        "data-quality",
        # MSN-0099 intelligence products
        "awareness", "resilience-watch", "wellness-insights", "strategic-outlook",
        "opportunity-review", "captains-picture", "products",
    ])
    parser.add_argument("--question", default="")
    parser.add_argument("--mission-id", default=None)
    parser.add_argument("--format", default="json", choices=["json", "markdown"])
    parser.add_argument("--no-challenge", action="store_true")
    parser.add_argument("--advisory-id", default="")
    parser.add_argument("--outcome", default="", choices=["", "success", "failure", "partial", "unknown"])
    parser.add_argument("--decision", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    md = args.format == "markdown"

    def emit(obj, markdown_fn=None):
        if md and markdown_fn:
            print(markdown_fn(obj))
        else:
            print(json.dumps(obj, indent=2, ensure_ascii=False, default=lambda o: getattr(o, "to_dict", lambda: str(o))()))

    # -- nullary measurement / intelligence actions ---------------------------
    if args.action == "metrics":
        return emit(_metrics.advisory_metrics(), _metrics.to_markdown) or 0
    if args.action == "calibration":
        return emit(_calibration.calibration_report(), _calibration.to_markdown) or 0
    if args.action == "advisory-health":
        return emit(_advisory_health.advisory_health(), _advisory_health.to_markdown) or 0
    if args.action == "patterns":
        ps = _patterns.detect_patterns()
        return emit([p.to_dict() for p in ps], lambda _x: _patterns.to_markdown(ps)) or 0
    if args.action == "signals":
        ss = _signals.emerging_signals()
        return emit([s.to_dict() for s in ss], lambda _x: _signals.to_markdown(ss)) or 0
    if args.action == "timeline":
        ev = _timeline.load_events()[:50]
        return emit({"span": _timeline.span(), "events": [e.to_dict() for e in ev]}) or 0
    if args.action == "proactive":
        return emit(_proactive.proactive_scan(), _proactive.to_markdown) or 0
    if args.action == "operating-picture":
        return emit(_operating_picture.captain_operating_picture(), lambda _x: _operating_picture.to_markdown()) or 0
    if args.action == "wellness":
        return emit(_wellness.wellness_intelligence(), lambda _x: _wellness.to_markdown()) or 0
    if args.action == "strategic":
        return emit(_strategic.strategic_intelligence(), lambda _x: _strategic.to_markdown()) or 0
    if args.action == "forecast":
        return emit(_forecast.all_forecasts(), lambda _x: _forecast.to_markdown()) or 0
    if args.action == "daily-brief":
        return emit(_daily_brief.daily_intelligence_brief(), lambda _x: _daily_brief.to_markdown()) or 0
    if args.action == "data-quality":
        return emit({"capture_gaps": _data_quality.capture_gaps(), "trust": _data_quality.trust_metrics()},
                    lambda _x: _data_quality.to_markdown()) or 0
    # MSN-0099 intelligence products (Captain-facing; machinery hidden)
    _PRODUCT_ACTIONS = {
        "awareness": _products.daily_awareness_brief,
        "resilience-watch": _products.operational_resilience_watch,
        "wellness-insights": _products.wellness_insights,
        "strategic-outlook": _products.strategic_outlook,
        "opportunity-review": _products.opportunity_review,
        "captains-picture": _products.captains_operating_picture,
    }
    if args.action in _PRODUCT_ACTIONS:
        return emit(_PRODUCT_ACTIONS[args.action](), _presentation.to_markdown) or 0
    if args.action == "products":
        return emit(_products.catalogue(), lambda _x: _products.catalogue_markdown()) or 0
    if args.action == "outcome":
        result = _outcomes.record_outcome(args.advisory_id, outcome=args.outcome or "unknown",
                                          decision_taken=args.decision, feedback=args.note)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    if args.action == "loops":
        open_loops = [r for r in _outcomes.load_records() if not r.get("outcome")]
        return emit({"loops": open_loops}) or 0

    # -- question-bearing actions --------------------------------------------
    if not args.question:
        print(json.dumps({"error": "--question is required for this action"}))
        return 1

    if args.action == "temporal":
        return emit(_temporal_route(args.question), _temporal.to_markdown) or 0
    if args.action == "episodic":
        r = _episodic.find_similar_episodes(args.question)
        return emit(r, _episodic.to_markdown) or 0

    opts = {}
    if args.mission_id:
        opts["mission_id"] = args.mission_id
    if args.action == "advice" and args.no_challenge:
        opts["challenge"] = False

    result = invoke(args.action, args.question, **opts)
    if md:
        if args.action == "lessons":
            print(_lessons.to_markdown(result))
        elif args.action == "evidence":
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result.to_markdown())
        return 0
    if args.action in ("lessons", "evidence"):
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
