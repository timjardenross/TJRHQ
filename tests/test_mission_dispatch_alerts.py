import core.engineering.mission_dispatch as dispatch


def test_failure_alert_is_suppressed_after_successful_alert(tmp_path, monkeypatch):
    mission = {"mission_id": "MSN-COOLDOWN-001", "title": "Cooldown test"}
    monkeypatch.setattr(dispatch, "fetch_approved_missions", lambda limit=25: [mission])
    monkeypatch.setattr(dispatch, "dispatch_one", lambda repo_root, mission: {"success": False, "error": "fixture failure"})
    alerts = []
    def capture_alert(body, **kwargs):
        alerts.append(body)
        return type("Result", (), {"ok": True})()
    first = dispatch.run_cycle(tmp_path, tmp_path / "data", alert_notifier=capture_alert)
    second = dispatch.run_cycle(tmp_path, tmp_path / "data", alert_notifier=capture_alert)
    assert first["alerts"] == 1
    assert second["alerts"] == 0
    assert len(alerts) == 1


def test_rejected_alert_is_logged_and_retried(tmp_path, monkeypatch, caplog):
    mission = {"mission_id": "MSN-COOLDOWN-002", "title": "Rejected alert"}
    monkeypatch.setattr(dispatch, "fetch_approved_missions", lambda limit=25: [mission])
    monkeypatch.setattr(dispatch, "dispatch_one", lambda repo_root, mission: {"success": False, "error": "fixture failure"})
    def reject_alert(body, **kwargs):
        return type("Result", (), {"ok": False})()
    result = dispatch.run_cycle(tmp_path, tmp_path / "data", alert_notifier=reject_alert)
    assert result["alerts"] == 0
    assert "Telegram alert was rejected" in caplog.text
