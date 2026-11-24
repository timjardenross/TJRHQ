# HQ Workbench capability checklist

The single delivery record for HQ. Statuses use the Intelligence programme's definitions:

- **Operational**: running in production and observed working.
- **Partial**: some functionality exists, but completion, integration, activation or operational verification remains outstanding.
- **Outstanding**: not delivered.

HQ is built and tested locally but is not deployed or switched on, so nothing below is Operational yet.
Last updated: 2026-11-24.

| Capability | Status | What's left to complete |
|---|---|---|
| **Shell and access** | | |
| Separate HQ workbench at its own address with its own navigation (Home, Intelligence, Decisions, Work, Library) | Partial | Deploy it, then verify with live sign-in and live data. |
| Independent on/off switch (off by default; off means HQ does not exist) | Partial | Observe it in a deployment, off and on. |
| Sign-in and access (uses the existing sign-in) | Partial | Verified only against a stand-in. Verify live. |
| Entry in the existing workbench switcher, shown only when HQ is on | Partial | See it in a deployment with HQ on. |
| Phone and tablet use | Partial | Layout, keyboard and contrast checks pass locally. Check on a real phone and with a screen reader. |
| Reach everything HQ does not rebuild | Partial | System lists every existing workbench. Weekly Review, Timeline, Content, Advisory, Capture inbox and alert silences have no HQ equivalent: decide which should come into HQ. |
| **Home** | | |
| What needs attention (existing "needs you" logic, without personal health) | Partial | Verify with live data. Intelligence items from the Intelligence delivery will appear here once it is merged. |
| Decisions waiting, what I know, work on my behalf | Partial | Verify with live data. |
| A material system problem shown without routine telemetry | Partial | Agree what counts as material. Verify with live data. |
| **Intelligence** | | |
| One list of signals, alerts and health evidence with filters | Partial | Verify with live data. |
| Item detail, and Start mission (creates a mission candidate for your review) | Partial | Verify the mission route live. Missions have no field for a source link, so the link travels in the text. |
| Morning brief page with governed publish | Partial | Verify live. A repeat publish upstream re-sends the notification (existing gap, owned by Intelligence). |
| Incident clustering and delivery tiers | Outstanding | Waiting for the Intelligence delivery to merge, then connect. |
| Provider disruption, systemic view, forward watch | Outstanding | Waiting for the Intelligence delivery to merge, then connect. |
| Source coverage | Outstanding | Waiting for the Intelligence delivery to merge, then connect. |
| From an intelligence item to a decision | Outstanding | No governed way to add an item to the Decisions inbox exists. Needs your decision on how. |
| Investigation path from an item | Outstanding | The existing investigation engine is not linked from HQ. |
| **Decisions** | | |
| One inbox for build requests and AI proposals | Partial | Verify with live data. |
| Brief publish, knowledge review and improvements in the same inbox | Partial | Verify live. Improvements need owner access. |
| Routine package: approve several, each recorded individually | Partial | Verify with live data. |
| Each decision explains the request, why, the recommendation, the consequences and whether you are needed | Partial | Wording is per source type because the data holds no per-item consequences. Needs your review of the wording. |
| No duplicate or conflicting decisions: build requests | Partial | Server-side atomic check is built and tested. The existing Decisions page still writes without a check; closing that needs a database rule (your approval). |
| No duplicate or conflicting decisions: AI proposals, brief, improvements | Partial | AI proposals and knowledge review are checked server-side but not atomically. Brief re-publish and improvements have no server check. Fixes belong with their owners. |
| Decisions arising from intelligence products | Outstanding | Waiting for the Intelligence delivery to merge, then connect. |
| **Work** | | |
| Missions and engineering hand-offs grouped as ready, blocked, in progress, done | Partial | Verify with live data. |
| Outputs and deliverables per item | Outstanding | Missions record no outputs. Hand-offs show PR links only. |
| Summary of agent activity with routine steps hidden | Outstanding | Not built. |
| Captured research requests shown, clearly marked not running | Partial | Verify live. |
| **Library** | | |
| One search across knowledge, memory, intelligence archive, briefs and content, showing where each item is stored | Partial | Verify with live data. |
| Find items stored in Notion | Partial | Only items already in the knowledge library appear. No direct Notion search is connected. |
| Health evidence, captures and missions in Library search | Outstanding | Not connected. |
| **Contextual actions** | | |
| Capture an idea from any screen, with that screen attached | Partial | Verify live. |
| New mission from any screen (a candidate for your review) | Partial | Verify the mission route live. |
| Request research (captured in Capture, nothing runs) | Partial | Verify live. |
| Research that actually runs | Outstanding | No research runner exists. Needs your decision on which service runs it. |
| Ask a question | Outstanding | No safe existing service. Needs your decision. |
| **Protection of the existing environment** | | |
| Existing workbenches, routes, APIs and landing unchanged | Partial | Unchanged in local checks (22 routes identical, flag off and on). One small additive entry in the shared workbench header. Confirm after deployment. |
| Personal health, Pain Recovery Studio and personal tasks kept out of HQ | Partial | Enforced in code and tests. Confirm with live data. |
| Deployment controls respected | Partial | Observed: the push and draft PR created no Vercel deployment. A live-data preview must use the deployment ticket gate when capacity allows. |
| **Commitments from the original design not yet in HQ** | | |
| Targeted improvements to the Missions, Capture, Content and Advisory screens | Outstanding | Not started. |
| One consistent vocabulary for risk, evidence, posture and capacity across HQ | Partial | HQ uses one scale. The existing workbenches keep theirs and their correctness fixes have not started. |
| Route-usage telemetry to support any later retirement decision | Outstanding | Not started. No retirement is authorised. |
