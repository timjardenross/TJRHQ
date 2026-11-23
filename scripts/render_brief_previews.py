"""Offline internal preview of the three briefs, before (legacy code paths) and after (V1 shared evidence), from exported read-only data.
Nothing is sent, scheduled or stored. Usage: render_brief_previews.py EVENTS_JSON LEGACY_INPUTS_JSON OUT_DIR [LEGACY_WEEKLY_TXT]"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO), str(_REPO / "platform-runtime")]

NOW = datetime(2026, 11, 23, 0, 30, tzinfo=timezone.utc)


def main(events_path, legacy_path, out_dir, legacy_weekly=None):
    for k in ("BRIEF_EVIDENCE_V1", "BRIEF_EVIDENCE_V1_MORNING", "BRIEF_EVIDENCE_V1_WEEKLY", "BRIEF_EVIDENCE_V1_COMMS"):
        os.environ.pop(k, None)
    from lib.comms import editorial, pillars, weekly
    from lib.comms import opportunities as opp

    from intelligence import brief_evidence as be
    from intelligence import captains_brief as cb
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw = json.loads(Path(events_path).read_text())
    events = [{"id": r["id"], "title": r["title"], "summary": r.get("summary") or "", "source": r["source"], "geography": r["geography"],
               "collected_at": r["collected_at"], "url": r.get("url")} for r in raw]
    leg = json.loads(Path(legacy_path).read_text())

    def since(h):
        cut = NOW - timedelta(hours=h)
        return [e for e in events if datetime.fromisoformat(e["collected_at"].replace("+00", "+00:00")) >= cut]

    # MORNING
    before = ["<legacy code path: _format_intelligence_posture_block + _format_signals_block>"]
    before += [x for x in cb._format_intelligence_posture_block(leg["brief"])]
    before += cb._format_signals_block(cb._with_risk_label(leg["signals"]), "📡 OTHER SIGNALS (24h)")
    ev72 = be.build_evidence(since(72), now=NOW, window_hours=72)
    after = be.morning_view(ev72)
    (out / "morning_before.txt").write_text("\n".join(before))
    (out / "morning_after.txt").write_text("\n".join(after))
    # WEEKLY
    ev7 = be.build_evidence(since(168), now=NOW, window_hours=168)
    (out / "weekly_after.txt").write_text("\n".join(be.weekly_view(ev7)))
    if legacy_weekly and Path(legacy_weekly).exists():
        (out / "weekly_before.txt").write_text(Path(legacy_weekly).read_text())
    # COMMS
    opps = [opp.build_opportunity("lesson", ref=r, title=t, body="") for r, t in leg["lessons"]]
    (out / "comms_before.txt").write_text(weekly._compose_weekly_brief_core(opps))

    def pillar_fn(text):
        _s, pkey, hits = editorial.classify_stream(text)
        return pillars.PILLARS_BY_KEY[pkey].name if pkey and hits else None
    view = be.comms_view(ev7, existing_titles=[o.title for o in opps], pillar_fn=pillar_fn, similarity_fn=editorial.max_similarity)
    (out / "comms_after.txt").write_text(weekly._compose_weekly_brief_core(opps) + "\n\n" + "\n".join(view))
    cnt = {p: sum(1 for i in ev7.incidents if i.priority == p) for p in ("ESCALATE", "VERIFY", "WATCH", "REFERENCE")}
    (out / "summary.json").write_text(json.dumps({"events_7d": len(since(168)), "events_72h": len(since(72)), "incidents_7d": len(ev7.incidents),
                                                   "priorities_7d": cnt, "method": ev7.method_version}, indent=1))
    print(json.dumps({"events_7d": len(since(168)), "events_72h": len(since(72)), "incidents_7d": len(ev7.incidents), "priorities_7d": cnt}))


if __name__ == "__main__":
    main(*sys.argv[1:5])
