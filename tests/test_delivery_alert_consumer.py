"""Consumer of the degraded-delivery alerts (dead-man's switch) and detection of a missing consumer (verification engine)."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core" / "platform"))

import deadmans_switch as dm
import verification_engine as ve

from intelligence import delivery_degraded as dg

NOW = 2_000_000_000


def _sender(sent, ok=True):
    def send(text):
        sent.append(text)
        return ok, None if ok else "down"
    return send


def test_prefix_matches_the_emitter():
    assert dm._DELIVERY_ALERT_PREFIX == dg.ALERT_PREFIX


def test_alerts_send_one_notice_without_content_and_advance(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "_DELIVERY_STATE_FILE", tmp_path / "s.json")
    sent, seen = [], []
    line = f'{dg.ALERT_PREFIX} {{"brief_id": "secret-id"}}'
    res = dm.check_delivery_alerts(read=lambda since: seen.append(since) or [line, line], send=_sender(sent), now_epoch=NOW)
    assert res["ok"] and res["alerts"] == 2 and len(sent) == 1 and "secret-id" not in sent[0]
    assert seen == [NOW - 3600]
    res = dm.check_delivery_alerts(read=lambda since: seen.append(since) or [], send=_sender(sent), now_epoch=NOW + 600)
    assert res["ok"] and len(sent) == 1 and seen[-1] == NOW


def test_unsent_notice_or_unreadable_journal_leaves_the_heartbeat_unwritten(tmp_path, monkeypatch):
    state = tmp_path / "s.json"
    monkeypatch.setattr(dm, "_DELIVERY_STATE_FILE", state)
    assert not dm.check_delivery_alerts(read=lambda since: ["x"], send=_sender([], ok=False), now_epoch=NOW)["ok"]

    def boom(since):
        raise OSError("journal")

    assert not dm.check_delivery_alerts(read=boom, send=_sender([]), now_epoch=NOW)["ok"]
    assert not state.exists()


def test_missing_or_stale_consumer_is_detected(tmp_path, monkeypatch):
    state = tmp_path / "s.json"
    monkeypatch.setattr(ve, "_DELIVERY_CONSUMER_STATE", state)
    assert not ve._delivery_alert_consumer_ok()
    state.write_text(json.dumps({"checked_at": time.time() - 3600}))
    assert not ve._delivery_alert_consumer_ok()
    state.write_text(json.dumps({"checked_at": time.time()}))
    assert ve._delivery_alert_consumer_ok()
