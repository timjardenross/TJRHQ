# STARFLEET COMMAND CENTRE API Reference
## Complete API Contract Documentation

**Version**: 1.0.0  
**Status**: Phase 2 Day 1  
**Base URL**: `http://localhost:5000`  
**Port**: 5000

---

## Table of Contents

1. [Response Format](#response-format)
2. [Health & Utility](#health--utility)
3. [Mission Registry API](#mission-registry-api)
4. [Coordination Engine API](#coordination-engine-api)
5. [System Health API](#system-health-api)
6. [Agent Status API](#agent-status-api)
7. [Error Handling](#error-handling)
8. [Rate Limits & Caching](#rate-limits--caching)

---

## Response Format

All API responses follow a consistent structure:

### Success Response (200)
```json
{
  "status": "success",
  "data": { /* endpoint-specific data */ },
  "metadata": {
    "timestamp": "2026-06-08T12:30:45.123Z",
    "source": "cache|fresh",
    "cacheKey": "endpoint:specific:key",
    "message": "Success message"
  }
}
```

### Stale Cache Response (200)
```json
{
  "status": "stale",
  "data": { /* last known data */ },
  "metadata": {
    "timestamp": "2026-06-08T12:30:45.123Z",
    "source": "stale_cache",
    "ageSeconds": 65,
    "message": "Data is 65s old (may be stale)"
  }
}
```

### Error Response (4xx/5xx)
```json
{
  "status": "error",
  "data": null,
  "metadata": {
    "source": "placeholder",
    "message": "Data unavailable"
  },
  "error": {
    "message": "Human-readable error message",
    "code": "ERROR_CODE",
    "timestamp": "2026-06-08T12:30:45.123Z"
  }
}
```

---

## Health & Utility

### Server Health Check
```
GET /health
```

**Response** (200):
```json
{
  "status": "operational",
  "timestamp": "2026-06-08T12:30:45.123Z",
  "uptime": 3600,
  "environment": "development"
}
```

**Use Case**: Monitoring server availability, load balancer health checks

---

### API Documentation
```
GET /api
```

**Response** (200):
```json
{
  "service": "STARFLEET COMMAND CENTRE API",
  "version": "1.0.0",
  "mission": "MSN-0035 Phase 2",
  "endpoints": {
    "missions": {
      "summary": "GET /api/v1/missions/summary",
      "active": "GET /api/v1/missions/active",
      "blocked": "GET /api/v1/missions/blocked",
      "detail": "GET /api/v1/missions/:id/detail"
    },
    "coordination": { /* ... */ },
    "health": { /* ... */ },
    "agents": { /* ... */ }
  },
  "documentation": "See MSN-0035-PHASE2-INTEGRATION-PLAN.md",
  "health": "/health"
}
```

---

## Mission Registry API

### 1. Get Mission Summary
```
GET /api/v1/missions/summary
```

**Description**: High-level mission statistics and health status

**Cache TTL**: 30 seconds

**Response** (200):
```json
{
  "status": "operational",
  "total": 12,
  "active": 12,
  "completed": 0,
  "blocked": 1,
  "overdue": 0,
  "health": "OPERATIONAL",
  "byPriority": {
    "P0": 1,
    "P1": 3,
    "P2": 5,
    "P3": 3
  },
  "timestamp": "2026-06-08T12:30:45.123Z"
}
```

**Use Case**: Dashboard mission health card, command centre status widget

---

### 2. Get Active Missions
```
GET /api/v1/missions/active
```

**Description**: List of all active missions with current status

**Cache TTL**: 30 seconds

**Response** (200):
```json
[
  {
    "id": "MSN-0032",
    "title": "Semantic Routing Integration",
    "priority": "P0",
    "status": "IN_PROGRESS",
    "progress": 85,
    "owner": "Chief Engineer",
    "startDate": "2026-05-15",
    "estimatedCompletion": "2026-06-10",
    "blockers": 0
  },
  { /* more missions */ }
]
```

**Use Case**: Mission list view, filtering and sorting

---

### 3. Get Blocked Missions
```
GET /api/v1/missions/blocked
```

**Description**: Missions currently blocked with blocker details

**Cache TTL**: 30 seconds

**Response** (200):
```json
[
  {
    "id": "MSN-0033",
    "title": "Blocked Mission Example",
    "priority": "P1",
    "status": "BLOCKED",
    "blockedSince": "2026-06-05",
    "blockers": [
      {
        "id": "BLK-001",
        "description": "Awaiting external dependency",
        "blockedBy": "MSN-0032",
        "expectedResolution": "2026-06-10"
      }
    ],
    "owner": "Risk Officer",
    "escalationLevel": "MEDIUM"
  }
]
```

**Use Case**: Risk dashboard, escalation monitoring

---

### 4. Get Mission Detail
```
GET /api/v1/missions/:id/detail
```

**Parameters**:
- `id` (string, required): Mission identifier (e.g., `MSN-0035`)

**Description**: Comprehensive mission details and timeline

**Cache TTL**: 30 seconds

**Response** (200):
```json
{
  "id": "MSN-0035",
  "title": "STARFLEET COMMAND CENTRE",
  "description": "Detailed information about this mission",
  "priority": "P1",
  "status": "IN_PROGRESS",
  "progress": 75,
  "owner": "Captain TJR",
  "team": ["Chief Engineer", "Coder Agent", "Risk Officer"],
  "startDate": "2026-06-01",
  "estimatedCompletion": "2026-06-20",
  "actualCompletion": null,
  "blockers": [],
  "dependencies": ["MSN-0032"],
  "timeline": [
    {
      "date": "2026-06-01",
      "event": "Mission started",
      "status": "COMPLETED"
    },
    { /* more timeline events */ }
  ],
  "metrics": {
    "tasksCompleted": 24,
    "tasksRemaining": 8,
    "riskLevel": "LOW",
    "teamCapacity": "FULL"
  }
}
```

**Example**:
```bash
curl http://localhost:5000/api/v1/missions/MSN-0032/detail
```

**Use Case**: Mission drill-down page, detailed status view

---

## Coordination Engine API

### 1. Get Daily Coordination Brief
```
GET /api/v1/coordination/brief
```

**Description**: Daily brief with top priorities and recommendations

**Cache TTL**: 30 seconds

**Response** (200):
```json
{
  "status": "operational",
  "timestamp": "2026-06-08T12:30:45.123Z",
  "dayStarted": "2026-06-08",
  "systemHealth": "OPERATIONAL",
  "topPriorities": 3,
  "escalations": {
    "HIGH": 1,
    "MEDIUM": 0,
    "LOW": 0,
    "total": 1
  },
  "briefItems": [
    {
      "rank": 1,
      "priority": "P0",
      "mission": "MSN-0032",
      "title": "Semantic Routing Integration",
      "status": "IN_PROGRESS",
      "progress": 85,
      "blocker": false,
      "owner": "Chief Engineer",
      "recommendation": "Continue current pace - on track for completion"
    },
    { /* more brief items */ }
  ],
  "workQueueItems": 8,
  "blockedMissions": 0,
  "overdueMissions": 0,
  "recommendations": [
    "Continue focus on MSN-0032 completion",
    "Monitor MSN-0034 Phase 2 progress",
    "MSN-0035 Phase 2 integration on track",
    "No escalations pending"
  ],
  "generatedBy": "Number One v1.0.0",
  "nextUpdate": "2026-06-08T12:31:00.000Z"
}
```

**Use Case**: Executive briefing, command centre dashboard

---

### 2. Get Work Queue
```
GET /api/v1/coordination/queue
```

**Description**: Prioritized list of work items with task details

**Cache TTL**: 30 seconds

**Response** (200):
```json
{
  "status": "operational",
  "timestamp": "2026-06-08T12:30:45.123Z",
  "totalItems": 8,
  "items": [
    {
      "rank": 1,
      "itemId": "WQ-001",
      "title": "Complete MSN-0032 Phase 2",
      "mission": "MSN-0032",
      "priority": "P0",
      "assignedTo": "Chief Engineer",
      "daysRemaining": 2,
      "estimatedEffort": "16 hours",
      "blocker": false,
      "specialistRecommendation": "Chief Engineer"
    },
    { /* more work items */ }
  ],
  "summary": {
    "P0Count": 1,
    "P1Count": 3,
    "P2Count": 2,
    "P3Count": 2,
    "blockedCount": 0,
    "totalEstimatedEffort": "100 hours"
  }
}
```

**Use Case**: Work queue view, task planning

---

### 3. Get Escalations
```
GET /api/v1/coordination/escalations
```

**Description**: XO escalations requiring command decision

**Cache TTL**: 30 seconds

**Response** (200):
```json
{
  "status": "operational",
  "timestamp": "2026-06-08T12:30:45.123Z",
  "totalEscalations": 1,
  "levelSummary": {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 0,
    "LOW": 0
  },
  "escalations": [
    {
      "id": "ESC-001",
      "level": "HIGH",
      "mission": "MSN-0032",
      "title": "Semantic Routing Performance Target",
      "description": "Confidence band calculation exceeding performance SLA",
      "createdAt": "2026-06-07T14:30:00Z",
      "status": "PENDING_XO_DECISION",
      "owner": "Chief Engineer",
      "escalatedBy": "Number One Coordination Engine",
      "options": [
        {
          "option": "A",
          "description": "Optimize confidence calculation algorithm",
          "effort": "HIGH",
          "riskLevel": "MEDIUM",
          "timeline": "2-3 days"
        },
        { /* more options */ }
      ],
      "xoDecisionRequired": true,
      "deadlineForDecision": "2026-06-10T16:00:00Z"
    }
  ],
  "recommendations": [
    "XO decision required on ESC-001",
    "All other missions tracking normally",
    "No critical escalations at this time"
  ]
}
```

**Use Case**: Executive decision board, escalation alerts

---

## System Health API

### 1. Get Health Summary
```
GET /api/v1/health/summary
```

**Description**: Overall system health status

**Cache TTL**: 60 seconds

**Response** (200):
```json
{
  "status": "OPERATIONAL",
  "systemHealth": "OPERATIONAL",
  "timestamp": "2026-06-08T12:30:45.123Z",
  "uptime": 3600,
  "services": {
    "Mission Registry": "OPERATIONAL",
    "Number One": "OPERATIONAL",
    "Slack Commander": "OPERATIONAL",
    "Supabase": "OPERATIONAL",
    "GitHub": "OPERATIONAL",
    "Docker": "OPERATIONAL",
    "Monitoring": "OPERATIONAL"
  },
  "servicesSummary": {
    "operational": 7,
    "degraded": 0,
    "offline": 0,
    "total": 7
  },
  "alertCount": 0,
  "criticalCount": 0,
  "warningCount": 0,
  "responseTime": {
    "average": "245ms",
    "p95": "412ms",
    "p99": "523ms"
  },
  "lastHealthCheck": "2026-06-08T12:30:45.123Z",
  "nextHealthCheck": "2026-06-08T12:31:45.123Z"
}
```

**Use Case**: System status dashboard, operational centre display

---

### 2. Get Services Status
```
GET /api/v1/health/services
```

**Description**: Individual service health details

**Cache TTL**: 60 seconds

**Response** (200):
```json
{
  "status": "operational",
  "timestamp": "2026-06-08T12:30:45.123Z",
  "services": [
    {
      "name": "Mission Registry",
      "status": "OPERATIONAL",
      "uptime": "99.98%",
      "lastCheck": "2026-06-08T12:30:45.123Z",
      "responseTime": "142ms",
      "endpoint": "http://localhost:5001",
      "healthCheckUrl": "http://localhost:5001/health",
      "description": "Mission management and tracking",
      "criticalService": true
    },
    { /* more services */ }
  ],
  "summary": {
    "total": 7,
    "operational": 7,
    "degraded": 0,
    "offline": 0,
    "averageUptime": "99.94%"
  }
}
```

**Use Case**: Infrastructure dashboard, service monitoring

---

### 3. Get Health Alerts
```
GET /api/v1/health/alerts
```

**Description**: Active health alerts and warnings

**Cache TTL**: 60 seconds

**Response** (200):
```json
{
  "status": "operational",
  "timestamp": "2026-06-08T12:30:45.123Z",
  "totalAlerts": 0,
  "bySeverity": {
    "CRITICAL": 0,
    "HIGH": 0,
    "MEDIUM": 0,
    "LOW": 0
  },
  "alerts": [],
  "notes": [
    "All systems operational",
    "No active alerts at this time",
    "Last critical alert resolved 2026-06-05"
  ],
  "lastAlertTime": "2026-06-05T14:22:00Z",
  "averageResolutionTime": "1 hour 23 minutes"
}
```

**Use Case**: Alert dashboard, incident tracking

---

## Agent Status API

### 1. Get All Agents Status
```
GET /api/v1/agents/status
```

**Description**: Status of all specialists/agents

**Cache TTL**: 120 seconds

**Response** (200):
```json
{
  "status": "operational",
  "timestamp": "2026-06-08T12:30:45.123Z",
  "agents": [
    {
      "name": "Chief Engineer",
      "role": "Engineering Specialist",
      "status": "ACTIVE",
      "missions": 3,
      "availability": "FULL",
      "lastActivity": "2026-06-08T12:25:45.123Z",
      "estimatedFree": "3 days",
      "workload": "HIGH",
      "specializations": ["System Architecture", "Backend Development", "DevOps"]
    },
    { /* more agents */ }
  ],
  "summary": {
    "totalAgents": 5,
    "activeAgents": 3,
    "idleAgents": 2,
    "fullAvailability": 4,
    "limitedAvailability": 1,
    "totalMissionsAssigned": 11,
    "teamHealthScore": "GOOD"
  }
}
```

**Use Case**: Agent dashboard, team workload view

---

### 2. Get Agent Workload
```
GET /api/v1/agents/:agent/workload
```

**Parameters**:
- `agent` (string, required): Agent identifier (e.g., `chief-engineer`)

**Description**: Detailed workload for a specific agent

**Cache TTL**: 120 seconds

**Response** (200):
```json
{
  "status": "operational",
  "timestamp": "2026-06-08T12:30:45.123Z",
  "agent": "Chief Engineer",
  "role": "Engineering Specialist",
  "currentStatus": "ACTIVE",
  "assignedMissions": [
    {
      "mission": "MSN-0032",
      "title": "Semantic Routing Integration",
      "priority": "P0",
      "tasks": 5,
      "completedTasks": 4,
      "estimatedRemainingHours": 8,
      "daysRemaining": 1,
      "progress": 85
    },
    { /* more missions */ }
  ],
  "capacityAnalysis": {
    "totalAssignedHours": 36,
    "availableHoursThisWeek": 40,
    "utilizationRate": 90,
    "overallocated": false,
    "canAcceptMore": false
  },
  "nextAvailable": "2026-06-11T00:00:00Z",
  "recommendations": [
    "Agent at near-capacity",
    "MSN-0032 should complete first",
    "MSN-0035 can be deferred slightly if needed"
  ]
}
```

**Example**:
```bash
curl http://localhost:5000/api/v1/agents/chief-engineer/workload
```

**Use Case**: Agent detail page, workload planning

---

### 3. Get Agent Activity
```
GET /api/v1/agents/:agent/activity
```

**Parameters**:
- `agent` (string, required): Agent identifier (e.g., `chief-engineer`)

**Description**: Recent activity and status updates for agent

**Cache TTL**: 120 seconds

**Response** (200):
```json
{
  "status": "operational",
  "timestamp": "2026-06-08T12:30:45.123Z",
  "agent": "Chief Engineer",
  "recentActivities": [
    {
      "timestamp": "2026-06-08T12:25:45.123Z",
      "type": "TASK_COMPLETED",
      "mission": "MSN-0032",
      "description": "Completed semantic routing test suite",
      "details": "All 25 tests passing"
    },
    { /* more activities */ }
  ],
  "activitySummary": {
    "tasksCompletedToday": 1,
    "communicationsToday": 1,
    "tasksInProgress": 5,
    "currentMission": "MSN-0032"
  },
  "lastStatusCheck": "2026-06-08T12:30:45.123Z",
  "availability": "AVAILABLE_SOON"
}
```

**Example**:
```bash
curl http://localhost:5000/api/v1/agents/chief-engineer/activity
```

**Use Case**: Activity timeline, agent status updates

---

## Error Handling

### Common HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success (fresh or cached) | All successful requests |
| 304 | Not Modified | Not used (always returns data) |
| 400 | Bad Request | Invalid parameter |
| 404 | Not Found | Invalid agent ID or mission ID |
| 500 | Server Error | Unexpected error |

### Error Fallback Behavior

**When API fails**, response uses 3-tier fallback:

1. **Fresh Cache** (< TTL): Returns with `"source": "cache"`
2. **Stale Cache** (> TTL): Returns with `"source": "stale_cache"` and age
3. **Placeholder** (No cache): Returns `"data": null` with error message

**Never shows broken UI** — always shows something useful.

---

## Rate Limits & Caching

### Cache TTLs

| Domain | TTL | Reason |
|--------|-----|--------|
| Mission Registry | 30 sec | Changes frequently |
| Coordination Engine | 30 sec | Updated constantly |
| System Health | 60 sec | Slower to change |
| Agent Status | 120 sec | Least dynamic |

### Recommended Request Patterns

**Dashboard Display**:
- Load all endpoints on page load (parallel requests)
- Re-check every 30 seconds
- Use cache data until TTL expires

**Real-Time Updates** (Phase 3):
- Use WebSocket subscriptions
- Fall back to polling if WebSocket unavailable
- Poll interval: 15 seconds minimum

### Rate Limiting

**Phase 1 (Current)**: No rate limiting  
**Phase 2+**: Planned limits (100 req/min per client)

---

## Usage Examples

### JavaScript/Node.js
```javascript
// Using API client
const { apiClient } = require('./frontend/api-client.js');

// Get mission summary
const summary = await apiClient.getMissionSummary();
console.log(`Active missions: ${summary.data.total}`);

// Get daily brief
const brief = await apiClient.getCoordinationBrief();
console.log(`Top priorities: ${brief.data.topPriorities}`);

// Get agent workload
const workload = await apiClient.getAgentWorkload('chief-engineer');
console.log(`Chief Engineer workload: ${workload.data.capacityAnalysis.utilizationRate}%`);
```

### cURL
```bash
# Get mission summary
curl -s http://localhost:5000/api/v1/missions/summary | jq '.data'

# Get coordination brief
curl -s http://localhost:5000/api/v1/coordination/brief | jq '.data.briefItems'

# Get agent status
curl -s http://localhost:5000/api/v1/agents/status | jq '.data.agents | length'
```

### Batch Requests
```javascript
const endpoints = [
  '/api/v1/missions/summary',
  '/api/v1/coordination/brief',
  '/api/v1/health/summary',
  '/api/v1/agents/status'
];

const responses = await apiClient.batchFetch(endpoints);
```

---

## Versioning

**Current Version**: 1.0.0  
**API Path**: `/api/v1/*`

Future breaking changes will use `/api/v2/*`

---

## Support & Documentation

- **Quick Start**: `BACKEND-QUICKSTART.md`
- **Completion Report**: `PHASE2-DAY1-COMPLETION.md`
- **Phase 2 Plan**: `PHASE2-KICKOFF.md`
- **Test Suite**: `backend/tests/api.test.js`

---

**API Status**: ✅ Operational  
**Last Updated**: 2026-06-08  
**Maintainer**: STARFLEET COMMAND CENTRE Team
