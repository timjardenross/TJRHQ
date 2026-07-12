#!/usr/bin/env python3
"""
Self-Improvement System Dashboard

Simple web UI for reviewing findings and providing feedback.
Runs on http://localhost:8892
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify, request

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dashboard")

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Paths - prefer /tmp on VM (where /root is read-only), fall back to REPO_ROOT
REPO_ROOT = Path(__file__).parent.parent.parent
_tmp_data_root = Path("/tmp/usstjros-findings")
DATA_ROOT = _tmp_data_root if _tmp_data_root.exists() else REPO_ROOT / "data" / "self-improvement"
RUNS_DIR = DATA_ROOT / "runs"
DECISIONS_FILE = DATA_ROOT / "review" / "decisions.jsonl"

log.info(f"DATA_ROOT: {DATA_ROOT}")
log.info(f"RUNS_DIR exists: {RUNS_DIR.exists()}")
if RUNS_DIR.exists():
    log.info(f"Run directories: {list(RUNS_DIR.iterdir())}")


def get_latest_run():
    """Get the most recent run directory."""
    if not RUNS_DIR.exists():
        return None
    runs = sorted([d for d in RUNS_DIR.iterdir() if d.is_dir()], reverse=True)
    return runs[0] if runs else None


def load_findings():
    """Load findings from latest run."""
    run_dir = get_latest_run()
    if not run_dir:
        return [], None

    findings_file = run_dir / "findings_classified.json"
    if not findings_file.exists():
        return [], None

    try:
        with open(findings_file) as f:
            data = json.load(f)
        findings = data.get("findings", [])
        return findings, run_dir.name
    except Exception as exc:
        log.error(f"Failed to load findings: {exc}")
        return [], None


def load_decisions():
    """Load existing decisions."""
    if not DECISIONS_FILE.exists():
        return {}

    decisions = {}
    try:
        with open(DECISIONS_FILE) as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    finding_id = d.get("finding_id")
                    if finding_id:
                        decisions[finding_id] = d
    except Exception as exc:
        log.error(f"Failed to load decisions: {exc}")

    return decisions


def save_decision(finding_id, decision, reasoning=""):
    """Save a decision to the decisions file."""
    DECISIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

    decision_record = {
        "finding_id": finding_id,
        "decision": decision,
        "reasoning": reasoning,
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        with open(DECISIONS_FILE, "a") as f:
            f.write(json.dumps(decision_record) + "\n")
        log.info(f"Saved decision for {finding_id}: {decision}")
        return True
    except Exception as exc:
        log.error(f"Failed to save decision: {exc}")
        return False


@app.route("/")
def index():
    """Serve the dashboard."""
    return render_template("dashboard.html")


@app.route("/api/findings")
def api_findings():
    """Get all findings from latest run."""
    findings, run_id = load_findings()
    decisions = load_decisions()

    # Enrich findings with decision status
    for f in findings:
        fid = f.get("finding_id")
        if fid in decisions:
            f["decision"] = decisions[fid]["decision"]
            f["decision_reasoning"] = decisions[fid].get("reasoning", "")
        else:
            f["decision"] = None

    return jsonify({
        "run_id": run_id,
        "findings": findings,
        "total": len(findings),
    })


@app.route("/api/finding/<finding_id>")
def api_finding(finding_id):
    """Get a specific finding."""
    findings, _ = load_findings()
    decisions = load_decisions()

    finding = next((f for f in findings if f.get("finding_id") == finding_id), None)
    if not finding:
        return jsonify({"error": "Finding not found"}), 404

    if finding_id in decisions:
        finding["decision"] = decisions[finding_id]["decision"]
        finding["decision_reasoning"] = decisions[finding_id].get("reasoning", "")

    return jsonify(finding)


@app.route("/api/decide", methods=["POST"])
def api_decide():
    """Record a decision on a finding."""
    data = request.json
    finding_id = data.get("finding_id")
    decision = data.get("decision")  # approved, rejected, more_evidence
    reasoning = data.get("reasoning", "")

    if not finding_id or not decision:
        return jsonify({"error": "Missing finding_id or decision"}), 400

    if decision not in ["approved", "rejected", "more_evidence"]:
        return jsonify({"error": "Invalid decision"}), 400

    success = save_decision(finding_id, decision, reasoning)
    if success:
        return jsonify({"success": True, "finding_id": finding_id, "decision": decision})
    else:
        return jsonify({"error": "Failed to save decision"}), 500


@app.route("/api/status")
def api_status():
    """Get system status."""
    findings, run_id = load_findings()
    decisions = load_decisions()

    return jsonify({
        "system": "operational",
        "latest_run": run_id,
        "findings_count": len(findings),
        "decisions_count": len(decisions),
        "pending_count": len([f for f in findings if f.get("finding_id") not in decisions]),
    })


if __name__ == "__main__":
    log.info("Starting Self-Improvement Dashboard on http://localhost:8892")
    app.run(host="0.0.0.0", port=8892, debug=False)
