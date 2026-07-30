from datetime import datetime


def build_mission_response(
    user_request: str,
    mission_domain: str,
    assigned_specialists: list,
    priority: str,
    status: str,
):
    mission_id = f"M-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    specialists = "\n- ".join(assigned_specialists)

    return f"""
# MISSION SUMMARY

Mission ID: {mission_id}

Mission Domain: {mission_domain}

Assigned Specialists:
- {specialists}

Priority:
{priority}

Status:
{status}

---

# ASSESSMENT

Commander TJR received:

{user_request}

Mission routing has been completed.

---

# RECOMMENDATIONS

Assigned specialists should review this request.

---

# NEXT ACTIONS

1. Review routing.
2. Assess specialist requirements.
3. Generate mission response.

---

# MISSION STATUS

{status}
"""
