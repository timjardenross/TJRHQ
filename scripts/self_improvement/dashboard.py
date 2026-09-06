#!/usr/bin/env python3
"""
Self-Improvement System Dashboard

Simple web UI for reviewing findings and providing feedback.
Runs on http://localhost:8892
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify, request

from opportunity_store import OpportunityStore
import outcome_contract as outcome_contract_module

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dashboard")

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# 2026-08-29: was "prefer /tmp on VM (where /root is read-only), fall back
# to REPO_ROOT" - that read-only constraint no longer holds on this host
# (confirmed: /opt/starship-endeavour/data/self-improvement is writable,
# root fs mounted rw). Preferring /tmp whenever it happens to exist was
# also its own bug independent of that: it meant this dashboard silently
# kept reading /tmp's history forever, even after a fix to make
# orchestrator.py write to the persistent path - the two would permanently
# disagree unless someone remembered to manually delete /tmp. Unconditional
# persistent path now, matching orchestrator.py's new --data-root default
# in the same commit. The pre-existing /tmp history was migrated over
# rather than orphaned.
REPO_ROOT = Path(__file__).parent.parent.parent
DATA_ROOT = REPO_ROOT / "data" / "self-improvement"
RUNS_DIR = DATA_ROOT / "runs"
DECISIONS_FILE = DATA_ROOT / "review" / "decisions.jsonl"

log.info(f"DATA_ROOT: {DATA_ROOT}")
log.info(f"RUNS_DIR exists: {RUNS_DIR.exists()}")
if RUNS_DIR.exists():
    log.info(f"Run directories: {list(RUNS_DIR.iterdir())}")


def get_latest_run():
    """Get the most recent run directory.

    2026-08-29: was a lexicographic sort on directory name (reverse=True),
    which silently broke the moment the persistent data root's older
    'r_20260712_NNN'-style run directories got mixed in with the newer
    date-prefixed ones ('r' > '2' in ASCII, so a July run always sorted as
    "latest" over an August one) - found live while migrating orchestrator.py
    off its old /tmp data root onto this persistent path in the same
    commit. Sorting by actual mtime instead is correct regardless of
    whatever naming convention a run directory happens to use.
    """
    if not RUNS_DIR.exists():
        return None
    runs = sorted(
        (d for d in RUNS_DIR.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
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


# ── HQ Evolution routes (additive — the routes above are the preserved,
# unmodified legacy self-improvement findings/decide pipeline) ────────────

opportunity_store = OpportunityStore(DATA_ROOT)

# Section 26/30/32/33: what each Discover/Investigate/Improve button is
# allowed to do to an opportunity's lifecycle_state. The LLM never chooses
# this mapping — it's fixed here, decided by which button the human clicked.
DECISION_TRANSITIONS = {
    "turn_into_improvement": {"lifecycle_state": "proposed"},
    "keep_watching": {"lifecycle_state": "watching"},
    "not_useful": {"lifecycle_state": "rejected"},
    "approve_improvement": {"lifecycle_state": "approved"},
    "create_mission": {"lifecycle_state": "implementing"},
    "more_evidence": {"lifecycle_state": "investigating"},
    "reject": {"lifecycle_state": "rejected"},
    # V2: a human asserting that an approved change has actually been
    # applied outside the two automated signals (legacy bounded remediation,
    # Mission status) — e.g. a manually-applied config/maintenance change.
    # This is the load-bearing bridge that starts the observation window
    # for opportunities with no automated implementation signal; it is
    # still a human decision, not something HQ infers on its own.
    "mark_implemented": {"lifecycle_state": "verifying"},
}


@app.route("/api/opportunities")
def api_opportunities():
    """List current opportunities, optionally filtered by lifecycle_state
    (?state=discovered,investigating,proposed,...) — comma-separated."""
    state_filter = request.args.get("state")
    states = set(s.strip() for s in state_filter.split(",")) if state_filter else None

    opportunities = opportunity_store.all_current()
    if states:
        opportunities = [o for o in opportunities if o.get("lifecycle_state") in states]
    opportunities.sort(key=lambda o: o.get("updated_at") or "", reverse=True)

    return jsonify({"opportunities": opportunities, "total": len(opportunities)})


@app.route("/api/opportunity/<opportunity_id>")
def api_opportunity(opportunity_id):
    """Get a specific opportunity's current state (folded from its full
    append-only history)."""
    opp = opportunity_store.get(opportunity_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    return jsonify(opp)


@app.route("/api/opportunity/decide", methods=["POST"])
def api_opportunity_decide():
    """Record a human decision against an opportunity (section 30: the
    human gate). decision_type picks the lifecycle transition; reasoning is
    optional free text captured against whichever field that transition
    uses (rejection_reason / watch_reason / missing_evidence)."""
    data = request.json or {}
    opportunity_id = data.get("opportunity_id")
    decision_type = data.get("decision_type")
    reasoning = data.get("reasoning", "")
    mission_id = data.get("mission_id")

    if not opportunity_id or not decision_type:
        return jsonify({"error": "Missing opportunity_id or decision_type"}), 400
    if decision_type not in DECISION_TRANSITIONS:
        return jsonify({"error": f"Invalid decision_type. Must be one of: {sorted(DECISION_TRANSITIONS)}"}), 400

    existing = opportunity_store.get(opportunity_id)
    if not existing:
        return jsonify({"error": "Opportunity not found"}), 404

    # Section 25: capability/product_improvement/architecture opportunities
    # are Mission-only — the API itself refuses a direct "approve_improvement"
    # (bounded-remediation) approval for them, matching PolicyEngine's own
    # manual_only classification for these change classes.
    mission_only = {"capability", "product_improvement", "architecture"}
    if decision_type == "approve_improvement" and existing.get("change_class") in mission_only:
        return jsonify({
            "error": f"'{existing.get('change_class')}' opportunities are Mission-only — use create_mission instead",
        }), 400
    if decision_type == "create_mission" and not mission_id:
        return jsonify({"error": "create_mission requires mission_id (create the Mission via the canonical /api/missions endpoint first)"}), 400
    if decision_type == "mark_implemented" and existing.get("lifecycle_state") not in ("approved", "implementing"):
        return jsonify({"error": f"mark_implemented requires the opportunity to be 'approved' or 'implementing' (currently '{existing.get('lifecycle_state')}')"}), 400
    if decision_type == "mark_implemented" and not existing.get("outcome_contract"):
        return jsonify({"error": "No outcome contract on this opportunity — approve_improvement or create_mission must run first"}), 400

    changes = dict(DECISION_TRANSITIONS[decision_type])
    if decision_type in ("reject", "not_useful"):
        changes["rejection_reason"] = reasoning or "Rejected — no reason given"
    elif decision_type == "keep_watching":
        changes["watch_reason"] = reasoning or "Promising but premature"
    elif decision_type == "more_evidence":
        missing = list(existing.get("missing_evidence") or [])
        if reasoning:
            missing.append(reasoning)
        changes["missing_evidence"] = missing
    elif decision_type == "create_mission":
        changes["mission_id"] = mission_id

    # V2 section 5-6: build the Outcome Contract once, at approval time,
    # before implementation — never rebuilt afterward. Both approval paths
    # (bounded remediation and Mission handoff) get a contract; only the
    # evidence-collection specifics differ per implementation_source at
    # evaluation time (outcome_evaluation.py). Guarded on "no contract yet"
    # rather than just decision_type so a duplicate/replayed approve call
    # can never retrospectively rewrite the original baseline to fit
    # whatever has happened since — the whole point of a contract.
    if decision_type in ("approve_improvement", "create_mission") and not existing.get("outcome_contract"):
        try:
            changes["outcome_contract"] = outcome_contract_module.build_outcome_contract(existing, REPO_ROOT)
        except Exception as exc:
            log.warning(f"Failed to build outcome contract for {opportunity_id}: {exc}")

    # V2: a human directly asserting implementation happened — start the
    # observation window immediately rather than waiting for the next
    # overnight cycle to detect it (there is nothing to detect; only the
    # human knows this happened outside the automated pathways).
    if decision_type == "mark_implemented":
        # Timezone-aware (+00:00), matching outcome_contract.py/
        # outcome_evaluation.py's convention — is_observation_window_
        # satisfied() computes a timedelta against datetime.now(timezone.utc),
        # which requires an offset-aware string here or the comparison raises.
        now_iso = datetime.now(timezone.utc).isoformat()
        changes["outcome"] = {
            **(existing.get("outcome") or {}),
            "implementation_success": True,
            "implementation_source": "manual",
            "implementation_verified_at": now_iso,
        }
        changes["outcome_contract"] = {
            **(existing.get("outcome_contract") or {}),
            "observation_started_at": now_iso,
            "evaluation_status": "observing",
        }

    updated = opportunity_store.update(opportunity_id, **changes)
    if not updated:
        return jsonify({"error": "Failed to update opportunity"}), 500

    log.info(f"Opportunity decision: {opportunity_id} -> {decision_type} ({changes.get('lifecycle_state')})")
    return jsonify({"success": True, "opportunity": updated.to_dict()})


@app.route("/api/evolution-summary")
def api_evolution_summary():
    """Section 15/20/37: the morning-compression + Captain's Chair summary.
    Combines the last overnight cycle's numbers (evolution_summary.json,
    written by evolution_orchestrator.py) with a live pending-decision
    count, since decisions can happen between cycles."""
    summary_file = DATA_ROOT / "review" / "evolution_summary.json"
    cycle_summary = {}
    if summary_file.exists():
        try:
            with open(summary_file) as f:
                cycle_summary = json.load(f)
        except Exception as exc:
            log.warning(f"Failed to read evolution_summary.json: {exc}")

    current = opportunity_store.all_current()
    pending_decisions_count = sum(1 for o in current if o.get("lifecycle_state") == "proposed")
    any_verification_failure = any(
        o.get("lifecycle_state") == "verifying" and o.get("outcome", {}).get("implementation_success") is False
        for o in current
    )

    # V2 section 25: worth_considering_count (this cycle's surfaced
    # shortlist) stays distinct from pending_decisions_count (the whole
    # undecided backlog) — and both stay distinct from the outcome-learning
    # fields below, which describe what was LEARNED, not what needs a
    # decision. Regressions surfaced here are evidence, not a second queue.
    regressions_count = sum(
        1 for o in current
        if o.get("lifecycle_state") == "learned" and o.get("outcome", {}).get("outcome_result") == "regressed"
    )

    return jsonify({
        "run_id": cycle_summary.get("run_id"),
        "timestamp": cycle_summary.get("timestamp"),
        "investigated_count": cycle_summary.get("investigated_count", 0),
        "worth_considering_count": cycle_summary.get("worth_considering_count", 0),
        "nothing_worth_changing": cycle_summary.get("nothing_worth_changing", pending_decisions_count == 0),
        "highest_value_opportunity": cycle_summary.get("highest_value_opportunity"),
        "pending_decisions_count": pending_decisions_count,
        "any_verification_failure": any_verification_failure,
        "has_run_yet": bool(cycle_summary),
        "outcomes_completed_count": cycle_summary.get("outcomes_completed_count", 0),
        "regressions_count": cycle_summary.get("regressions_count", regressions_count),
        "latest_material_learning": cycle_summary.get("latest_material_learning"),
        "cycle_status": cycle_summary.get("cycle_status", "unknown" if not cycle_summary else "ok"),
        "freshness": cycle_summary.get("freshness", cycle_summary.get("timestamp")),
    })


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
