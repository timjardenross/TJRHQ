# Live Workbenches — Master List

**Do not hand-edit this file.** It mirrors `lcars-portal/src/lib/workbenches.ts`'s
`LIVE_WORKBENCHES` array, which is the actual source of truth (rendered
directly by the hub tile grid and `WorkbenchShell`'s persistent switcher).
This doc exists for humans who won't open that file — update the array,
then update this list to match in the same commit.

`tools/check_workbench_registry.py` (CI-gated as `workbench-registry-gate`)
fails the build if a new top-level route appears under `lcars-portal/src/app/`
that isn't in the array below AND isn't in that script's `_EXCLUDED_ROUTES`
allowlist — so a route can't silently go unreachable the way
`comms-workbench` and `self-improvement-findings` did (see
`docs/UI-Layer-Debt-Handoff-2026-08-29.md`, Finding 4).

## The 14 live workbenches

Order is deliberate, not alphabetical: command/triage first, then domain
intelligence, then work pipelines, then the archive, then platform-ops last.

| Route | Title | Description |
|---|---|---|
| `/hub` | LifeOS Hub | Always-on glance view — situation strip, live alerts, calendar, reminders, and today's briefing. The front door. |
| `/captains-chair-workbench` | Captain's Chair | Operational dashboard — recovery posture, mission overview, alerts, and intelligence at a glance. |
| `/weekly-review` | Weekly Review | One calm weekly pass across every workbench — what happened, what slipped, what needs attention, what is safe to ignore. |
| `/ready-room` | Ready Room | Life admin and task decomposition in one place — what needs attention now, what is waiting on someone else, and a tiny first step for anything overwhelming. |
| `/intelligence-workbench` | Technical OSINT Workbench | Cyber, infrastructure, and regulatory signal intelligence — source reliability, confidence scoring, and threat escalation. |
| `/health-osint` | Health OSINT Workbench | Clinical trial and performance-research intelligence — source reliability, study confidence, and safety escalation. |
| `/emergency-alert-hub-workbench` | Emergency Alerts | Official Australian emergency information, prioritised by what may require attention now. |
| `/human-systems-workbench` | Human Systems | Personal capacity intelligence — understand your current state, what's consuming capacity, what appears to help, and what may need to change. |
| `/physical-readiness` | Physical Readiness | Adaptive gym decision-support - builds a safe session from the equipment on hand, plus exercise library and workout history. |
| `/content-workbench` | Content Workbench | Capture, research, draft, proof, and publish comms content end-to-end, plus a Portfolio of everything published — one QA-gated pipeline. |
| `/advisory-workbench` | Advisory | Decision support — think through a question, challenge assumptions, explore perspectives, and learn from what happened. |
| `/briefs` | Briefs | The intelligence brief archive — every synthesized brief across every domain, filterable by review/publish status. |
| `/agent-status-workbench` | HQ Status | Is HQ working properly? Interpreted platform health across capabilities, automations, sources, and machinery — not just a wall of job rows. |
| `/self-improvement-findings` | HQ Evolution | Continuous improvement for TJR HQ — overnight discovery, research and investigation of new capabilities, open-source opportunities, cost reductions, reliability improvements and better ways for HQ to work. |

## Real routes deliberately NOT in the master list

Kept in sync with `tools/check_workbench_registry.py`'s `_EXCLUDED_ROUTES`.
Each has its own reason recorded on the page itself — read that comment
before assuming an absence here is a bug.

| Route | Why excluded |
|---|---|
| `/home` | Retired redirect stub, not a destination. |
| `/workbenches` | The hub page that renders this list — not itself a workbench. |
| `/investigate` | Deliberately zero-nav, contextual-entry only (MSN-0353). |
| `/captains-brief-workbench` | Legacy nav-era page, predates the workbench hub model. |
| `/capture-workbench` | Legacy nav-era page, predates the workbench hub model. |
| `/health-osint-curation` | Reachable via a secondary in-app link, not orphaned but not hub-listed. |
| `/knowledge-workbench` | Reachable via a secondary in-app link, not orphaned but not hub-listed. |
| `/mission-workbench` | Reachable via a secondary in-app link, not orphaned but not hub-listed. |

**Last synced:** HQ V1 Integration QA (this mission) — added the 2 missing rows (`/hub`, `/physical-readiness`) and corrected 2 stale titles (`Human Systems` and `Advisory`, previously listed here as `Human Systems Workbench`/`Advisory Workbench`) to match `workbenches.ts`'s current `LIVE_WORKBENCHES` array exactly.
