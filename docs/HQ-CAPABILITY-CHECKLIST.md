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
| Essential journeys from the existing workbenches reachable in HQ, specialist screens kept | Partial | Weekly Review, activity, capture inbox, research, Ask and knowledge discovery are in HQ. Specialist editing stays in its own screen by design (content drafting, advisory sessions and outcomes, alert silences, capture routing and AI enrichment, knowledge memory editing); System links to all of them. |
| **Home** | | |
| What needs attention (existing "needs you" logic, without personal health) | Partial | Verify with live data. Intelligence items from the Intelligence delivery will appear here once it is merged. |
| Decisions waiting, what I know, work on my behalf | Partial | Verify with live data. |
| This week (Weekly Review, personal sections removed on the server) | Partial | Verify with live data. Completing the review stays in the Weekly Review workbench. |
| A material system problem shown without routine telemetry | Partial | Agree what counts as material. Verify with live data. |
| **Intelligence** | | |
| One list of signals, alerts and health evidence with filters | Partial | Verify with live data. |
| Item detail, and Start mission (creates a mission candidate for your review) | Partial | Verify the mission route live. Missions have no field for a source link, so the link travels in the text. |
| Morning brief page with governed publish | Partial | Verify live. |
| From an intelligence item to a decision request (evidence, reason, options and any recommendation kept; one request per item) | Partial | Built on the existing proposal mechanism and tested. Verify live. |
| Incident clustering and delivery tiers | Partial | Connected to the Intelligence delivery's incident endpoint; incidents join the list and can become decision requests. Shows "off" until that flag is activated, which is the release lead's decision. Verify live once activated. |
| Provider disruption, systemic view, forward watch | Partial | Connected to the products endpoint; products and their exceptions appear. Shows "not available" until the products migration (a draft, not applied) is applied by the Intelligence programme. Verify live. |
| Source coverage | Partial | Connected to the source-coverage endpoint (counts, limitations, non-healthy sources). Verify with live data. |
| Investigation path from an item | Outstanding | The existing investigation engine is not linked from HQ. |
| **Decisions** | | |
| One inbox for build requests and AI proposals | Partial | Verify with live data. |
| Brief publish, knowledge review and improvements in the same inbox | Partial | Verify live. Improvements need owner access. |
| Routine package: approve several, each recorded individually | Partial | Verify with live data. |
| Each decision states what is decided, why, the options, the consequences and whether you are needed (unknowns stated as unknown) | Partial | Default wording is in place. Review it with real data. |
| No conflicting build-request decisions, enforced in the database | Partial | Migration 0261 is written and tested on a local database but NOT applied. Applying it to production needs your go. Until then the existing Decisions page can still overwrite a decision. |
| No double execution of an AI proposal | Partial | Atomic claim built and tested. Verify live. |
| No repeated or conflicting improvement decisions | Partial | Guard built and tested in the improvements service. It takes effect when that service restarts. The VM's pull-based `deploy/auto-deploy.sh` restarts services whose start time predates the newest commit, so merging to `main` restarts it. No manual step. |
| No repeat brief publication notification | Outstanding | Needs a change in the Intelligence workflow (a repeat publish must not resend the notification). To be agreed with the Intelligence agent. |
| Decisions arising from intelligence products and incidents | Partial | Product exceptions and incidents are items in Intelligence, and "Ask me to decide" turns one into a governed request. Verify live once the products and incident data exist. |
| **Work** | | |
| Missions and engineering hand-offs grouped as ready, blocked, in progress, done | Partial | Verify with live data. |
| Research as a type of work, with the mission's real status ("Requested, not running" until something executes it) | Partial | Verify live. |
| Research that actually runs, with progress, findings and deliverables | Outstanding | No research runner exists. Needs a worker that reads research missions and runs them (your decision, it is new infrastructure). |
| Capture inbox: make a mission, mark reviewed, dismiss (personal captures excluded) | Partial | Verify live. |
| Activity history (mission changes and execution events; personal sources excluded) | Partial | Verify with live data. |
| Outputs and deliverables per item | Outstanding | Missions record no outputs. Hand-offs show PR links only. |
| Summary of agent activity with routine steps hidden | Outstanding | Not built. |
| **Library** | | |
| One search across knowledge, memory, intelligence archive, briefs and content, showing where each item is stored | Partial | Verify with live data. |
| Search Notion directly | Partial | Built and tested (read-only server route, personal-data filtered, shown in Library). Goes Operational once a read-only `NOTION_TOKEN` is set in the Vercel project and verified. Until then the Library says "Notion search is not connected yet." |
| Health evidence, captures and missions in Library search | Outstanding | Not connected. |
| **Ask and contextual actions** | | |
| Ask (retrieval first, then the existing AI Console; Advice mode uses the existing Advisory service; proposed actions queue for approval) | Partial | The deployment has `OLLAMA_CLOUD_BASE_URL`/`OLLAMA_CLOUD_MODEL` but no `OLLAMA_CLOUD_ENABLED`, so `/api/ai/chat` answers "not enabled". Switching it on routes prompts to the cloud model, a privacy-boundary setting that is yours to approve. Verify live after. Without it HQ says Ask is unavailable. |
| Capture an idea from any screen, with that screen attached | Partial | Verify live. |
| New mission from any screen (a candidate for your review) | Partial | Verify the mission route live. |
| **Protection of the existing environment** | | |
| Existing workbenches, routes, APIs and landing unchanged | Partial | Unchanged in local checks (22 routes identical, flag off and on). Small additive changes to shared code are covered by tests. Confirm after deployment. |
| Personal health, Pain Recovery Studio and personal tasks kept out of HQ | Partial | Enforced in code and tests, including server-side removal from the weekly review. Confirm with live data. |
| Deployment controls respected | Partial | Observed: three pushes to this branch created no Vercel deployment. That says nothing about other branches. A live-data preview must use the deployment ticket gate when capacity allows. |
| **Commitments from the original design not yet in HQ** | | |
| Targeted improvements to the Missions, Capture, Content and Advisory screens | Outstanding | Not started. |
| One consistent vocabulary for risk, evidence, posture and capacity across HQ | Partial | HQ uses one scale. The existing workbenches keep theirs and their correctness fixes have not started. |
| Route-usage telemetry to support any later retirement decision | Outstanding | Not started. No retirement is authorised. |


## Release sequence (approved 2026-11-24)

1. Merge #718 to `main` (flag off) in the first production slot; the internal budget re-opens about 20 hours after 07:30 UTC on 2026-11-24.
2. Migrations: `0261_build_request_decision_integrity` (HQ) first, then the Intelligence products draft promoted as `0262`. Rollback for 0261 is in its header. Neither is applied until separately approved.
3. Verify existing routes unchanged and `/hq` 404 with the flag off.
4. Set `HQ_WORKBENCH_ENABLED=true` after the morning-brief assessment, if the checks pass.
