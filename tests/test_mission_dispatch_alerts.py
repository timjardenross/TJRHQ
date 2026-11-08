import core.engineering.mission_dispatch as dispatch



def test_failed_dispatch_emits_one_alert(tmp_path, monkeypatch):
    mission = {"mission_id": "MSN-TEST-001", "title": "Test dispatch"}
    monkeypatch.setattr(dispatch, "fetch_approved_missions", lambda limit=25: [mission])
    monkeypatch.setattr(dispatch, "dispatch_one", lambda repo_root, mission: {"success": False, "error": "fixture failure"})
    alerts = []
    def capture_alert(body, **kwargs):
        alerts.append((body, kwargs))
        return type("Result", (), {"ok": True})()
    result = dispatch.run_cycle(tmp_path, tmp_path / "data", alert_notifier=capture_alert)
    assert result["failed"] == 1
    assert result["alerts"] == 1
    assert len(alerts) == 1
    assert "MSN-TEST-001" in alerts[0][0]

def test_alert_failure_does_not_mask_job_failure(tmp_path, monkeypatch):
    mission = {"mission_id": "MSN-TEST-002", "title": "Test dispatch"}
    monkeypatch.setattr(dispatch, "fetch_approved_missions", lambda limit=25: [mission])
    monkeypatch.setattr(dispatch, "dispatch_one", lambda repo_root, mission: {"success": False, "error": "fixture failure"})
    def broken_alert(body, **kwargs):
        raise RuntimeError("telegram unavailable")
    result = dispatch.run_cycle(tmp_path, tmp_path / "data", alert_notifier=broken_alert)
    assert result["failed"] == 1
    assert result["alerts"] == 0
