# MSN-0035 Phase 2 Kickoff
## STARFLEET COMMAND CENTRE Backend Integration

**Date**: 2026-06-08  
**Phase**: 2 — Integration with Backend APIs  
**Target Duration**: 3-5 days  
**Status**: READY TO BEGIN

---

## What Phase 2 Accomplishes

Phase 1 delivered a beautiful, fully-functional Dashy dashboard with:
- 7 operational sections
- 42 static items
- Custom Starfleet theme
- Professional UI/UX

**Phase 2 connects this dashboard to LIVE OPERATIONAL DATA**, transforming it from a beautiful reference to a real-time intelligence platform.

---

## Phase 2 Integration Points

### 1. Mission Registry (MSN-0031)
**From**: Mission Registry database  
**To**: Dashboard "COMMAND" section  
**Shows**: Live mission counts, status, priorities, blockers

Example:
```
MISSION REGISTRY
Status: 12 active missions
P0: 1 | P1: 3 | P2: 5 | P3: 3
Blocked: 1
Health: OPERATIONAL
[VIEW QUEUE] [VIEW DETAILS]
```

### 2. Number One Coordination Engine
**From**: Coordination rules engine  
**To**: Dashboard "COMMAND" section  
**Shows**: Daily brief, escalations, work queue, recommendations

Example:
```
DAILY COMMAND BRIEF
Generated: Today 08:00 UTC
System Health: GREEN
Top Priorities: 3
Escalations: 1 HIGH
[FULL BRIEF] [ESCALATIONS] [QUEUE]
```

### 3. System Health Monitoring
**From**: Service health checks  
**To**: Dashboard "SHIP SYSTEMS" section  
**Shows**: Operational status for all services (Docker, Supabase, Slack, GitHub, etc.)

Example:
```
OPERATIONAL STATUS
✓ Mission Registry — OPERATIONAL
✓ Number One — OPERATIONAL
✓ Slack Commander — OPERATIONAL
✓ Supabase — OPERATIONAL
✓ GitHub — OPERATIONAL
```

### 4. Agent Status Dashboard
**From**: Specialist availability tracking  
**To**: Dashboard (new card)  
**Shows**: Specialist workload, availability, last activity

Example:
```
SPECIALIST STATUS
▼ Chief Engineer ........... ACTIVE (3 missions)
▼ Coder Agent .............. IDLE (1 mission)
▼ Risk Officer ............. ACTIVE (2 missions)
▼ Knowledge Officer ........ IDLE (1 mission)
▼ Mission Scribe ........... ACTIVE (4 missions)
```

### 5. Real-Time Updates
**From**: WebSocket connections  
**To**: All widgets  
**Shows**: Live data updates without page refresh

Example:
- Mission status changes → Dashboard updates in real-time
- Escalations triggered → Alert appears immediately
- System goes down → Status changes to CRITICAL
- Agent becomes available → Workload rebalances

---

## Architecture Overview

```
STARFLEET COMMAND CENTRE (Dashy Frontend)
    ↓
API Gateway / Node.js Backend
    ↓
    ├─ Mission Registry API (MSN-0031)
    ├─ Number One API (Coordination Engine)
    ├─ System Health API (Service Monitoring)
    ├─ Agent Status API (Specialist Tracking)
    └─ WebSocket Server (Real-Time Updates)
    ↓
Existing Systems
    ├─ MSN-0031 (Mission Registry - SQLite)
    ├─ Number One (Coordination Rules Engine)
    ├─ Workflow Engine
    ├─ Supabase (Database)
    ├─ Slack (Commander)
    └─ GitHub (Repository)
```

---

## Implementation Roadmap (3-5 Days)

### Day 1: API Layer Setup
- [ ] Create Node.js/Express backend
- [ ] Implement Mission Registry API endpoints (summary, active, blocked)
- [ ] Implement System Health API endpoints
- [ ] Set up error handling and fallback logic
- [ ] Testing: Verify all endpoints return correct data

### Day 2: Coordination Engine Integration
- [ ] Implement Number One API endpoints (brief, escalations, queue)
- [ ] Implement Agent Status API endpoints
- [ ] Set up caching strategy (30-120s TTLs)
- [ ] Testing: Verify real data flows correctly

### Day 3: Real-Time Updates
- [ ] Implement WebSocket server
- [ ] Create real-time update subscriptions
- [ ] Build JavaScript client for WebSocket connections
- [ ] Add automatic fallback to polling
- [ ] Testing: Verify updates appear in < 1 second

### Day 4: Dashboard Integration
- [ ] Create dynamic Dashy widget components
- [ ] Connect Mission Registry widget to API
- [ ] Connect Number One widget to API
- [ ] Connect System Health widget to API
- [ ] Connect Agent Status widget to API
- [ ] Testing: Verify all widgets display live data

### Day 5: Testing & Deployment
- [ ] End-to-end testing (user flows)
- [ ] Performance testing (< 2s load time)
- [ ] Error scenario testing (API down, timeouts)
- [ ] Fallback testing (stale data display)
- [ ] Deployment to production
- [ ] Monitoring setup

---

## API Endpoints (Detailed Specs in Phase 2 Plan)

### Mission Registry APIs
```
GET /api/v1/missions/summary          → Mission counts & health
GET /api/v1/missions/active           → List of active missions
GET /api/v1/missions/blocked          → Blocked missions detail
GET /api/v1/missions/:id/detail       → Single mission full details
```

### Number One APIs
```
GET /api/v1/coordination/brief        → Daily coordination brief
GET /api/v1/coordination/queue        → Prioritized work queue
GET /api/v1/coordination/escalations  → XO escalations
```

### System Health APIs
```
GET /api/v1/health/summary            → Overall system health
GET /api/v1/health/services           → Individual service status
GET /api/v1/health/alerts             → Active alerts
```

### Agent Status APIs
```
GET /api/v1/agents/status             → All specialists status
GET /api/v1/agents/:agent/workload    → Specialist workload
GET /api/v1/agents/:agent/activity    → Recent activity
```

### Real-Time Updates
```
WebSocket /ws/updates                 → Real-time event stream
Events: mission_updated, escalation_created, health_changed, agent_status_changed
```

---

## Key Design Decisions

### 1. Caching Strategy
- **Mission Summary**: 30 second cache (changes frequently, need freshness)
- **Health Status**: 60 second cache (slower to change)
- **Agent Status**: 120 second cache (least dynamic)
- **All endpoints**: Return cached data immediately, update in background

### 2. Error Handling
- **Tier 1**: Return cached/stale data if available
- **Tier 2**: Show "Last updated X seconds ago" badge
- **Tier 3**: If no cache, show placeholder with "Data unavailable" message
- **Never**: Show broken widgets or errors to user

### 3. Real-Time Updates
- **Primary**: WebSocket (real-time, efficient)
- **Fallback**: Polling (15 second intervals if WebSocket unavailable)
- **Automatic**: Switch to polling silently if WebSocket disconnects
- **Recovery**: Attempt to reconnect WebSocket every 5 seconds

### 4. Performance Targets
- Dashboard load: < 2 seconds
- API response: < 500ms (with cache)
- Widget update: < 1 second (with real-time)
- WebSocket event delivery: < 100ms

---

## What Stays The Same (Phase 1 Assets)

✅ Dashy configuration (dashy-config.yml)  
✅ Custom Starfleet theme (theme-starfleet.css)  
✅ Dashboard structure and sections  
✅ Color palette and aesthetic  
✅ Keyboard shortcuts and navigation  

**No changes to Phase 1** — Phase 2 is purely additive (backend integration only).

---

## What Changes

- ❌ Static items → ✅ Dynamic widgets showing live data
- ❌ Placeholder cards → ✅ Real-time mission counts and status
- ❌ No alerts → ✅ Real-time escalations and health warnings
- ❌ No specialist data → ✅ Live agent status and workload
- ❌ Manual refresh → ✅ Automatic updates every 30-120 seconds

---

## Before & After

### Before (Phase 1)
```
MISSION REGISTRY
Status: 12 active missions (placeholder)
[STATIC - REFRESH PAGE TO SEE CHANGES]
```

### After (Phase 2)
```
MISSION REGISTRY
Status: 12 active missions (LIVE)
P0: 1 | P1: 3 | P2: 5 | P3: 3
Blocked: 1 | Overdue: 0
Health: OPERATIONAL
Last updated: 2 seconds ago
[VIEW QUEUE] [VIEW DETAILS]
```

---

## Implementation Checklist

### Planning
- [x] Design API endpoints
- [x] Design integration architecture
- [x] Design error handling and fallback
- [x] Design real-time update mechanism
- [x] Create implementation roadmap
- [x] Identify open questions and risks

### Backend Development (Day 1-3)
- [ ] Set up Node.js/Express backend
- [ ] Implement Mission Registry APIs
- [ ] Implement Number One APIs
- [ ] Implement System Health APIs
- [ ] Implement Agent Status APIs
- [ ] Implement WebSocket server
- [ ] Set up caching (Redis or in-memory)
- [ ] Implement error handling and fallbacks

### Frontend Integration (Day 4)
- [ ] Create Mission Registry widget
- [ ] Create Daily Brief widget
- [ ] Create System Health widget
- [ ] Create Agent Status widget
- [ ] Connect widgets to APIs
- [ ] Implement real-time update handlers

### Testing (Day 5)
- [ ] Unit tests for API endpoints
- [ ] Integration tests for widgets
- [ ] Performance tests (load time, API response)
- [ ] Error scenario tests (API down, timeouts)
- [ ] Fallback behavior tests
- [ ] End-to-end user flow tests

### Deployment
- [ ] Deploy backend to production
- [ ] Deploy dashboard updates
- [ ] Enable monitoring and alerts
- [ ] Document new features
- [ ] Create user runbook

---

## Open Questions (Documented in Phase 2 Plan)

1. **WebSocket vs Polling**: Which real-time mechanism to use? (WebSocket primary with polling fallback recommended)
2. **Caching Layer**: Use Redis, in-memory, or localStorage? (In-memory recommended for phase 2, Redis for phase 3+)
3. **Error Budgets**: How often can APIs fail before showing stale data? (30s tolerance recommended)
4. **Data Freshness**: How stale is "acceptable stale"? (60s recommended for mission data)
5. **Specialist Availability**: How is specialist status tracked? (Need to define source system)
6. **Authentication**: Do APIs need auth tokens? (Recommend yes for production)
7. **Rate Limiting**: Do we need rate limits to protect backends? (Yes, recommend 100 req/min per client)

**See MSN-0035-PHASE2-INTEGRATION-PLAN.md for detailed discussion of each question.**

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| API unavailability | Dashboard shows stale data | Cache strategy with fallbacks |
| Slow API response | Dashboard slow to load | Caching, aggressive TTLs, background updates |
| WebSocket connection loss | Realtime stops working | Automatic fallback to polling |
| Data inconsistency | Dashboard shows wrong data | Use shared cache, version API responses |
| Too many API calls | Backend overwhelmed | Rate limiting, caching, subscription-based updates |
| Specialist data missing | Agent status incomplete | Define data collection at phase 2 kickoff |

**See Phase 2 Plan for detailed risk analysis and mitigation strategies.**

---

## Success Criteria

### Functional
- [ ] All 4 API domains implemented and tested
- [ ] All 6 widget types connected to live data
- [ ] Real-time updates working (WebSocket + polling fallback)
- [ ] Error handling and fallbacks verified

### Performance
- [ ] Dashboard loads in < 2 seconds
- [ ] API responses in < 500ms
- [ ] Widget updates in < 1 second
- [ ] WebSocket events delivered in < 100ms

### Quality
- [ ] All error scenarios tested and handled gracefully
- [ ] Fallback behavior verified (stale data, placeholders)
- [ ] 24+ hour continuous operation test passed
- [ ] User satisfaction (Captain TJR says "this is real operational data")

---

## Files & Documentation

### Documents
- **MSN-0035-ASSESSMENT.md** — Phase 1 design (completed)
- **MSN-0035-PHASE2-INTEGRATION-PLAN.md** — Phase 2 architecture (NEW)
- **MSN-0035-COMPLETION-REPORT.md** — Phase 1 completion (reference)
- **PHASE2-KICKOFF.md** — This file

### Code Locations (Phase 2)
```
core/command-centre/
├── backend/
│   ├── api/
│   │   ├── missions.js       (Mission Registry APIs)
│   │   ├── coordination.js   (Number One APIs)
│   │   ├── health.js         (System Health APIs)
│   │   ├── agents.js         (Agent Status APIs)
│   │   └── websocket.js      (Real-time updates)
│   ├── cache/
│   │   └── cache-manager.js  (Caching layer)
│   ├── middleware/
│   │   ├── error-handling.js (Error handling)
│   │   └── fallback.js       (Fallback logic)
│   └── app.js                (Express server)
├── frontend/
│   ├── widgets/
│   │   ├── mission-registry.js
│   │   ├── daily-brief.js
│   │   ├── system-health.js
│   │   └── agent-status.js
│   └── utils/
│       ├── api-client.js     (API calls)
│       └── websocket-client.js (Real-time)
└── tests/
    ├── api.test.js
    ├── integration.test.js
    └── performance.test.js
```

---

## Next Steps

1. **Review Integration Plan**
   - Read MSN-0035-PHASE2-INTEGRATION-PLAN.md
   - Review API endpoint specifications
   - Discuss open questions and decisions

2. **Finalize Decisions**
   - Choose caching strategy (Redis vs in-memory)
   - Confirm real-time mechanism (WebSocket primary)
   - Define specialist data source
   - Plan authentication approach

3. **Set Up Development Environment**
   - Scaffold Node.js/Express backend
   - Set up test infrastructure
   - Configure CI/CD for phase 2

4. **Begin Implementation**
   - Day 1: API layer
   - Day 2: Coordination integration
   - Day 3: Real-time updates
   - Day 4: Dashboard integration
   - Day 5: Testing & deployment

---

## Success = Mission Control

When Phase 2 is complete, Captain TJR opens the command centre and sees:

```
STARFLEET COMMAND CENTRE
NCC-170230

COMMAND                     OPERATIONS              SCIENCE
├─ Mission Registry        ├─ Slack Commander      ├─ Claude
│  • 12 active missions    │  Status: ONLINE       │  Status: ONLINE
│  • P0: 1 | P1: 3        │  • [LAUNCH]          │  • [LAUNCH]
│  • Blocked: 1           │                        │
│  Health: OPERATIONAL    │  [MORE...]            │ [MORE...]
├─ Daily Brief
│  • Top priority: MSN-32
│  • Escalations: 1 HIGH
│  • Work queue: 8 items
└─ [MORE...]

SHIP SYSTEMS
├─ Docker ........................ OPERATIONAL
├─ Monitoring ................... OPERATIONAL  
├─ Supabase ..................... OPERATIONAL
└─ GitHub ....................... OPERATIONAL

Last Updated: 2 seconds ago
Real-time updates: ACTIVE
```

This is what **operational intelligence** looks like.

---

**Ready to proceed with Phase 2 integration?**

Detailed specifications in: **MSN-0035-PHASE2-INTEGRATION-PLAN.md**
