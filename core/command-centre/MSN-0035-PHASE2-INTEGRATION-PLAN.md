# MSN-0035 Phase 2 Integration Plan
## STARFLEET COMMAND CENTRE Backend Integration Architecture

**Document Version**: 1.0  
**Date**: 2026-06-08  
**Status**: ARCHITECTURE DESIGN  
**Mission ID**: MSN-0035  
**Phase**: 2 (Integration)  
**Target Completion**: 3-5 days  

---

## Executive Summary

This document provides the detailed Phase 2 integration architecture for STARFLEET COMMAND CENTRE. Phase 1 delivered a static, fully-styled Dashy dashboard. Phase 2 will connect this dashboard to live operational data from MSN-0031 (Mission Registry), Number One (Coordination Engine), system health checks, and agent status monitoring.

**Key Objective**: Transform the command centre from a beautiful static interface into a real-time operational intelligence platform that reflects actual mission state, system health, and team availability.

**Constraints**:
- Reuse existing systems (no major rewrites)
- No new databases or external dependencies beyond what exists
- Maintain Phase 1 aesthetic and UX
- Dashboard load time < 2 seconds
- Graceful degradation when backends are unavailable

---

## Table of Contents

1. [API Endpoint Specifications](#1-api-endpoint-specifications)
2. [Integration Architecture Diagram](#2-integration-architecture-diagram)
3. [Dashy Widget Configuration Plan](#3-dashy-widget-configuration-plan)
4. [Error Handling and Fallback Strategy](#4-error-handling-and-fallback-strategy)
5. [Real-Time Update Mechanism](#5-real-time-update-mechanism)
6. [Implementation Roadmap](#6-implementation-roadmap)
7. [Open Questions and Risks](#7-open-questions-and-risks)

---

## 1. API Endpoint Specifications

### 1.1 Mission Registry API (MSN-0031 Integration)

These endpoints expose the existing SQLite-backed mission registry as a REST API.

#### Endpoint: GET /api/v1/missions/summary
**Purpose**: Provides aggregated mission counts and health status for the dashboard widget.

**Request**:
```http
GET /api/v1/missions/summary
Accept: application/json
```

**Response** (200 OK):
```json
{
  "timestamp": "2026-06-08T12:30:45Z",
  "total_missions": 12,
  "active_missions": 8,
  "by_priority": {
    "P0": 1,
    "P1": 3,
    "P2": 5,
    "P3": 3
  },
  "by_status": {
    "PROPOSED": 2,
    "TRIAGED": 1,
    "ACTIVE": 8,
    "BLOCKED": 1,
    "IN_REVIEW": 0,
    "COMPLETED": 0,
    "DEFERRED": 0,
    "CANCELLED": 0
  },
  "health_status": "OPERATIONAL",
  "blocked_missions": 1,
  "overdue_missions": 0,
  "next_critical_deadline": "2026-06-10T14:00:00Z"
}
```

**Response Time**: < 100ms  
**Cache Strategy**: Cache for 30 seconds  
**Fallback**: Return last known state from localStorage

---

#### Endpoint: GET /api/v1/missions/active
**Purpose**: List all active missions with details for dashboard display.

**Request**:
```http
GET /api/v1/missions/active?limit=10&sort=priority
Accept: application/json
```

**Response** (200 OK):
```json
{
  "timestamp": "2026-06-08T12:30:45Z",
  "count": 8,
  "missions": [
    {
      "mission_id": "MSN-0032",
      "title": "Slack Commander Voice Integration",
      "priority": "P0",
      "status": "ACTIVE",
      "assigned_role": "Chief Engineer",
      "assigned_specialists": ["Agent-Coder", "Agent-Risk"],
      "blockers": [],
      "next_action": "Implement voice-to-text module",
      "created_at": "2026-06-05T09:00:00Z",
      "last_updated": "2026-06-08T10:30:00Z",
      "domain": "operations",
      "metadata": {
        "estimated_completion": "2026-06-10",
        "progress_percent": 45
      }
    },
    {
      "mission_id": "MSN-0033",
      "title": "Dashy Dashboard Integration",
      "priority": "P1",
      "status": "ACTIVE",
      "assigned_role": "Operations",
      "assigned_specialists": ["Agent-Executive"],
      "blockers": [],
      "next_action": "Connect mission registry API",
      "created_at": "2026-06-06T08:00:00Z",
      "last_updated": "2026-06-08T11:00:00Z",
      "domain": "command",
      "metadata": {
        "estimated_completion": "2026-06-15",
        "progress_percent": 30
      }
    }
  ],
  "has_more": false
}
```

**Response Time**: < 200ms  
**Cache Strategy**: Cache for 60 seconds  
**Query Parameters**:
- `limit`: Max results (default: 10, max: 50)
- `sort`: Sort by priority/updated_at/created_at (default: priority)
- `status`: Filter by status (ACTIVE, BLOCKED, etc.)
- `priority`: Filter by priority (P0, P1, P2, P3)
- `domain`: Filter by domain (operations, science, intelligence, etc.)

---

#### Endpoint: GET /api/v1/missions/blocked
**Purpose**: List blocked missions for alert display.

**Request**:
```http
GET /api/v1/missions/blocked
Accept: application/json
```

**Response** (200 OK):
```json
{
  "timestamp": "2026-06-08T12:30:45Z",
  "count": 1,
  "blocked_missions": [
    {
      "mission_id": "MSN-0028",
      "title": "Security Audit",
      "priority": "P1",
      "status": "BLOCKED",
      "blockers": [
        "Waiting for Risk Officer approval on security framework",
        "Dependency: MSN-0027 must complete first"
      ],
      "assigned_role": "Intelligence",
      "blocked_since": "2026-06-07T14:00:00Z",
      "estimated_unblock": "2026-06-10T10:00:00Z"
    }
  ],
  "has_more": false
}
```

**Response Time**: < 100ms  
**Cache Strategy**: Cache for 30 seconds  
**Alert Trigger**: Display warning if count > 0

---

#### Endpoint: GET /api/v1/missions/:mission_id
**Purpose**: Detailed view of a specific mission (for modal/detail page).

**Request**:
```http
GET /api/v1/missions/MSN-0032
Accept: application/json
```

**Response** (200 OK):
```json
{
  "timestamp": "2026-06-08T12:30:45Z",
  "mission": {
    "mission_id": "MSN-0032",
    "title": "Slack Commander Voice Integration",
    "description": "Integrate voice input capabilities with Slack Commander...",
    "priority": "P0",
    "status": "ACTIVE",
    "domain": "operations",
    "division": "command",
    "assigned_role": "Chief Engineer",
    "assigned_specialists": ["Agent-Coder", "Agent-Risk"],
    "created_at": "2026-06-05T09:00:00Z",
    "updated_at": "2026-06-08T10:30:00Z",
    "due_date": "2026-06-10T17:00:00Z",
    "blockers": [],
    "dependencies": ["MSN-0031"],
    "next_action": "Implement voice-to-text module",
    "evidence_links": ["https://github.com/.../issues/1"],
    "metadata": {
      "estimated_completion": "2026-06-10",
      "progress_percent": 45,
      "effort_estimate_hours": 16,
      "effort_consumed_hours": 8
    },
    "history": [
      {
        "timestamp": "2026-06-08T10:30:00Z",
        "action": "status_updated",
        "old_status": "TRIAGED",
        "new_status": "ACTIVE",
        "notes": "Work commenced"
      }
    ]
  }
}
```

**Response Time**: < 150ms  
**Cache Strategy**: Cache for 120 seconds  

---

### 1.2 Number One Coordination API (Coordination Engine)

These endpoints expose Number One's work queue, escalation, and briefing functionality.

#### Endpoint: GET /api/v1/coordination/daily-brief
**Purpose**: Returns the daily coordination brief with system health, priorities, and escalations.

**Request**:
```http
GET /api/v1/coordination/daily-brief?date=2026-06-08
Accept: application/json
```

**Response** (200 OK):
```json
{
  "timestamp": "2026-06-08T12:30:45Z",
  "brief_date": "2026-06-08",
  "generated_at": "2026-06-08T08:00:00Z",
  "system_health": {
    "overall_status": "OPERATIONAL",
    "status_code": "green",
    "health_percent": 98,
    "services": {
      "mission_registry": "operational",
      "number_one": "operational",
      "slack_commander": "operational",
      "semantic_router": "operational",
      "github": "operational",
      "supabase": "operational"
    }
  },
  "work_queue": {
    "total_items": 12,
    "by_priority": {
      "P0": 1,
      "P1": 3,
      "P2": 5,
      "P3": 3
    },
    "top_5_by_priority": [
      {
        "mission_id": "MSN-0032",
        "title": "Slack Commander Voice Integration",
        "priority": "P0",
        "assigned_specialist": "Agent-Coder",
        "status": "ACTIVE",
        "confidence": 0.92,
        "next_action": "Implement voice-to-text module"
      }
    ]
  },
  "escalations": {
    "count": 1,
    "by_level": {
      "critical": 0,
      "high": 1,
      "medium": 0
    },
    "items": [
      {
        "escalation_type": "blocked_mission",
        "mission_id": "MSN-0028",
        "level": "high",
        "reason": "P1 mission blocked for 24+ hours awaiting Risk Officer approval",
        "recommended_action": "Executive Officer review and approval decision needed"
      }
    ]
  },
  "follow_ups": {
    "count": 3,
    "items": [
      {
        "type": "stale_mission",
        "mission_id": "MSN-0015",
        "last_update": "2026-06-01T10:00:00Z",
        "days_since_update": 7,
        "status": "ACTIVE",
        "recommended_action": "Request status update from assigned role"
      }
    ]
  },
  "xo_recommendations": [
    "Unblock MSN-0028 - Security Audit requires XO decision",
    "Review stale missions (7+ days without update)",
    "Consider P2 priority escalations if capacity allows"
  ]
}
```

**Response Time**: < 300ms  
**Cache Strategy**: Cache for 60 seconds  
**Generation**: Regenerate daily or on-demand  
**Query Parameters**:
- `date`: Brief date (default: today, format: YYYY-MM-DD)
- `include_details`: Include full mission details (default: false)

---

#### Endpoint: GET /api/v1/coordination/work-queue
**Purpose**: Current work queue ordered by priority and assignment.

**Request**:
```http
GET /api/v1/coordination/work-queue?specialist=all&include_blocked=true
Accept: application/json
```

**Response** (200 OK):
```json
{
  "timestamp": "2026-06-08T12:30:45Z",
  "total_items": 12,
  "queue": [
    {
      "position": 1,
      "mission_id": "MSN-0032",
      "priority": "P0",
      "status": "ACTIVE",
      "title": "Slack Commander Voice Integration",
      "assigned_specialist": "Agent-Coder",
      "confidence": 0.92,
      "confidence_band": "high",
      "blockers": [],
      "dependencies": ["MSN-0031"],
      "next_action": "Implement voice-to-text module",
      "rationale": "P0 priority, active, high confidence routing",
      "estimated_effort_hours": 16,
      "elapsed_hours": 8
    }
  ],
  "queue_stats": {
    "avg_priority": "P1.5",
    "unblocked_items": 11,
    "blocked_items": 1,
    "high_confidence_items": 8,
    "medium_confidence_items": 3,
    "low_confidence_items": 1
  }
}
```

**Response Time**: < 200ms  
**Cache Strategy**: Cache for 60 seconds  
**Query Parameters**:
- `specialist`: Filter by assigned specialist name or 'all'
- `include_blocked`: Include blocked missions (default: true)
- `sort`: Sort order (priority, assignment, confidence, default: priority)

---

#### Endpoint: GET /api/v1/coordination/escalations
**Purpose**: Current escalations requiring XO attention.

**Request**:
```http
GET /api/v1/coordination/escalations?level=all&include_resolved=false
Accept: application/json
```

**Response** (200 OK):
```json
{
  "timestamp": "2026-06-08T12:30:45Z",
  "total_escalations": 1,
  "by_level": {
    "critical": 0,
    "high": 1,
    "medium": 0
  },
  "escalations": [
    {
      "escalation_id": "ESC-001",
      "escalation_type": "blocked_mission",
      "mission_id": "MSN-0028",
      "level": "high",
      "created_at": "2026-06-07T14:00:00Z",
      "reason": "P1 mission blocked for 24+ hours awaiting Risk Officer approval",
      "context": {
        "mission_title": "Security Audit",
        "priority": "P1",
        "status": "BLOCKED",
        "blockers": ["Waiting for Risk Officer approval on security framework"]
      },
      "recommended_action": "Executive Officer review and approval decision needed",
      "snoozed_until": null
    }
  ]
}
```

**Response Time**: < 100ms  
**Cache Strategy**: Cache for 30 seconds  
**Query Parameters**:
- `level`: Filter by level (critical, high, medium, all; default: all)
- `include_resolved`: Include resolved escalations (default: false)

---

### 1.3 System Health API

These endpoints monitor operational status of all integrated services.

#### Endpoint: GET /api/v1/health/services
**Purpose**: Real-time status of all integrated services.

**Request**:
```http
GET /api/v1/health/services
Accept: application/json
```

**Response** (200 OK):
```json
{
  "timestamp": "2026-06-08T12:30:45Z",
  "overall_status": "operational",
  "overall_health": 98,
  "services": {
    "mission_registry": {
      "status": "operational",
      "health_percent": 100,
      "response_time_ms": 45,
      "last_check": "2026-06-08T12:30:30Z",
      "uptime_percent": 99.9,
      "endpoint": "http://localhost:5000/api/missions/status"
    },
    "number_one": {
      "status": "operational",
      "health_percent": 100,
      "response_time_ms": 120,
      "last_check": "2026-06-08T12:30:35Z",
      "uptime_percent": 99.8,
      "endpoint": "http://localhost:5000/api/number-one/status"
    },
    "slack_commander": {
      "status": "operational",
      "health_percent": 100,
      "response_time_ms": 200,
      "last_check": "2026-06-08T12:30:40Z",
      "uptime_percent": 99.5,
      "endpoint": "https://slack.com/api/auth.test"
    },
    "semantic_router": {
      "status": "operational",
      "health_percent": 100,
      "response_time_ms": 85,
      "last_check": "2026-06-08T12:30:25Z",
      "uptime_percent": 99.7,
      "endpoint": "http://localhost:5000/api/router/status"
    },
    "github": {
      "status": "operational",
      "health_percent": 100,
      "response_time_ms": 350,
      "last_check": "2026-06-08T12:30:20Z",
      "uptime_percent": 99.6,
      "endpoint": "https://api.github.com/repos/timjarden-ross/USSTJROS"
    },
    "supabase": {
      "status": "operational",
      "health_percent": 100,
      "response_time_ms": 150,
      "last_check": "2026-06-08T12:30:28Z",
      "uptime_percent": 99.9,
      "endpoint": "https://supabase.com/api/v1/status"
    }
  },
  "alerts": []
}
```

**Response Time**: < 2000ms (parallel health checks)  
**Cache Strategy**: Cache for 30 seconds  
**Health Check Interval**: Every 30 seconds  

---

#### Endpoint: GET /api/v1/health/overall
**Purpose**: Simplified health status for dashboard badge.

**Request**:
```http
GET /api/v1/health/overall
Accept: application/json
```

**Response** (200 OK):
```json
{
  "timestamp": "2026-06-08T12:30:45Z",
  "overall_status": "operational",
  "health_percent": 98,
  "status_code": "green",
  "message": "All systems operational",
  "last_degradation": "2026-06-08T08:15:00Z",
  "degradation_reason": "Brief Slack API connectivity issue (resolved)"
}
```

**Response Time**: < 100ms (cached)  
**Cache Strategy**: Cache for 30 seconds  
**Status Codes**:
- `green` (90-100%): Operational
- `yellow` (75-89%): Degraded
- `red` (< 75%): Critical

---

### 1.4 Agent Status API

These endpoints expose specialist agent availability and workload.

#### Endpoint: GET /api/v1/agents/status
**Purpose**: Current status and workload of all specialist agents.

**Request**:
```http
GET /api/v1/agents/status
Accept: application/json
```

**Response** (200 OK):
```json
{
  "timestamp": "2026-06-08T12:30:45Z",
  "agents": {
    "Chief Engineer": {
      "role": "Chief Engineer",
      "status": "active",
      "last_activity": "2026-06-08T12:15:00Z",
      "current_mission": "MSN-0032",
      "assigned_missions": ["MSN-0032"],
      "workload_percent": 75,
      "estimated_free_time": "2026-06-10T17:00:00Z"
    },
    "Coder Agent": {
      "role": "Coder Agent",
      "status": "idle",
      "last_activity": "2026-06-08T10:30:00Z",
      "current_mission": null,
      "assigned_missions": [],
      "workload_percent": 0,
      "estimated_free_time": "now"
    },
    "Risk Officer": {
      "role": "Risk Officer",
      "status": "active",
      "last_activity": "2026-06-08T12:20:00Z",
      "current_mission": "MSN-0028",
      "assigned_missions": ["MSN-0028", "MSN-0020"],
      "workload_percent": 50,
      "estimated_free_time": "2026-06-09T17:00:00Z"
    },
    "Executive Officer": {
      "role": "Executive Officer",
      "status": "active",
      "last_activity": "2026-06-08T12:30:00Z",
      "current_mission": null,
      "assigned_missions": [],
      "workload_percent": 15,
      "estimated_free_time": "now"
    }
  },
  "summary": {
    "total_agents": 7,
    "active_agents": 4,
    "idle_agents": 3,
    "avg_workload_percent": 34
  }
}
```

**Response Time**: < 200ms  
**Cache Strategy**: Cache for 60 seconds  
**Status Values**: active, idle, offline, busy, on_break

---

### 1.5 Error Responses

All endpoints should return consistent error responses:

#### Error Response Format (4xx/5xx):
```json
{
  "timestamp": "2026-06-08T12:30:45Z",
  "error": true,
  "status": 503,
  "error_code": "SERVICE_UNAVAILABLE",
  "message": "Mission Registry service is temporarily unavailable",
  "details": "Connection timeout after 5000ms",
  "retry_after": 30,
  "fallback_data": {
    "cached_at": "2026-06-08T12:28:45Z",
    "age_seconds": 120,
    "is_stale": true,
    "warning": "Data may be outdated"
  }
}
```

**Status Codes**:
- `200 OK`: Success
- `304 Not Modified`: No changes since last request
- `400 Bad Request`: Invalid parameters
- `401 Unauthorized`: Authentication required
- `404 Not Found`: Resource not found
- `503 Service Unavailable`: Backend service down
- `504 Gateway Timeout`: Backend timeout

---

## 2. Integration Architecture Diagram

### System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│          DASHY FRONTEND (MSN-0035 Phase 1)                  │
│   - 7 Sections, 42 Items, Custom Starfleet Theme            │
│   - Responsive, WCAG 2.1 AA compliant                       │
└─────────────────┬───────────────────────────────────────────┘
                  │
        ┌─────────┴─────────┬─────────────┬────────────────┬─────────┐
        │                   │             │                │         │
        v                   v             v                v         v
┌──────────────┐  ┌───────────────┐  ┌──────────┐  ┌────────────┐  ┌──────┐
│ Mission      │  │ Coordination  │  │ System   │  │ Agent      │  │ Real-│
│ Registry API │  │ Engine (N1)   │  │ Health   │  │ Status API │  │ time │
│ (MSN-0031)   │  │ (MSN-0034)    │  │ API      │  │            │  │ Sync │
└──────────────┘  └───────────────┘  └──────────┘  └────────────┘  └──────┘
        │                   │             │                │
        └─────────────────┬─┴─────────────┴────────────────┴──────────┘
                          │
                          v
        ┌──────────────────────────────────────────┐
        │     API Gateway / Integration Layer       │
        │  - Caching (Redis/LocalStorage)          │
        │  - Error handling & fallback              │
        │  - Rate limiting                         │
        │  - Request deduplication                 │
        └──────────────────────────────────────────┘
                          │
              ┌───────────┼────────────┐
              │           │            │
              v           v            v
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │Websocket │ │ Polling  │ │   SSE    │
        │Updates   │ │ Updates  │ │ Updates  │
        └──────────┘ └──────────┘ └──────────┘
              │           │            │
              └───────────┴────────────┘
                          │
                          v
                ┌──────────────────────┐
                │   Local Storage      │
                │ - Stale Data Cache   │
                │ - Last Known State   │
                │ - Settings Cache     │
                └──────────────────────┘
```

### Component Interaction Flow

```
USER OPENS DASHBOARD
        │
        v
DASHY LOADS (Phase 1 UI, CSS, Config)
        │
        v
┌──────────────────────────────────────────────┐
│  INITIAL DATA LOAD (Parallel Requests)       │
│  ┌──────────────────────────────────────────┐│
│  │ - /api/v1/missions/summary (30s cache)   ││
│  │ - /api/v1/coordination/daily-brief       ││
│  │ - /api/v1/health/services (30s cache)    ││
│  │ - /api/v1/agents/status (60s cache)      ││
│  │ - /api/v1/missions/blocked (30s cache)   ││
│  └──────────────────────────────────────────┘│
│  TIMEOUT: 5 seconds per request              │
│  FALLBACK: Use cached/stale data + error UI  │
└──────────────────────────────────────────────┘
        │
        v
    RENDER WIDGETS
    (with live data)
        │
        v
┌──────────────────────────────────────────────┐
│  START REAL-TIME UPDATES                     │
│  ┌──────────────────────────────────────────┐│
│  │ Option A: WebSocket (preferred)          ││
│  │  - Subscribe to mission.updated events   ││
│  │  - Subscribe to agent.status events      ││
│  │  - Subscribe to health.status events     ││
│  │                                          ││
│  │ Option B: Server-Sent Events (SSE)      ││
│  │  - EventSource from /api/v1/stream       ││
│  │  - Reconnect on disconnect              ││
│  │                                          ││
│  │ Option C: Polling (fallback)             ││
│  │  - Poll critical endpoints every 30s     ││
│  │  - Poll secondary endpoints every 60s    ││
│  └──────────────────────────────────────────┘│
└──────────────────────────────────────────────┘
        │
        v
 RECEIVE UPDATES
        │
        v
UPDATE WIDGETS IN PLACE
(smooth transitions, no page reload)
        │
        v
MAINTAIN STATE IN LOCALSTORAGE
(for offline access)
```

### Data Flow Example: Mission Status Update

```
1. Mission Status Changes
   Backend: Mission Registry DB updated
           mission_id: MSN-0032
           old_status: TRIAGED
           new_status: ACTIVE
           
2. Event Generated
   Real-time system detects change
   Event: { type: "mission.updated", mission_id: "MSN-0032" }
   
3. Event Broadcast
   WebSocket/SSE sends to all connected clients
   OR Polling client detects on next refresh
   
4. Dashboard Widget Updated
   COMMAND > Mission Queue widget
   Shows MSN-0032 as now ACTIVE
   Refresh color coding and status indicators
   
5. State Cached
   localStorage updated with new state
   Timestamp: 2026-06-08T12:30:45Z
   
6. User Sees Changes
   Smooth animation/transition
   Visual feedback (e.g., status badge color change)
   No full page reload
```

---

## 3. Dashy Widget Configuration Plan

### 3.1 Dynamic Widget Types Needed

#### Widget 1: Mission Registry Summary Card
**Location**: COMMAND section, top-left  
**Size**: 1x1 (large card)  
**Refresh**: 30 seconds

```yaml
- name: Mission Registry Summary
  icon: fas fa-flag
  type: StatCardWidget
  data:
    source: /api/v1/missions/summary
    fields:
      - label: "Total Active"
        value: "$.active_missions"
        icon: fas fa-tasks
      - label: "Blocked"
        value: "$.blocked_missions"
        icon: fas fa-lock-open
        warning: true
      - label: "Top Priority"
        value: "$.by_priority.P0"
        icon: fas fa-star
  actions:
    - label: "View Queue"
      url: /missions/queue
    - label: "Triage"
      url: /missions/triage
  refreshInterval: 30
  cacheDuration: 30
  fallback:
    message: "Unable to load mission data"
    useStaleData: true
    showTimestamp: true
```

**Rendering**:
```
┌──────────────────────────┐
│ MISSION REGISTRY         │
├──────────────────────────┤
│ Total Active: 8    │ ▲ 2 │
│ Blocked: 1         │ ▼ 1 │
│ Top Priority: P0 1 │     │
│                    │     │
│ [VIEW QUEUE] [TRIAGE]    │
└──────────────────────────┘
```

---

#### Widget 2: Active Missions List
**Location**: COMMAND section  
**Size**: 2x2 (medium card, scrollable)  
**Refresh**: 60 seconds

```yaml
- name: Active Missions
  icon: fas fa-list-check
  type: ListWidget
  data:
    source: /api/v1/missions/active
    limit: 5
    sort: priority
    fields:
      - key: mission_id
        label: ID
        format: badge
      - key: title
        label: Mission
        truncate: 30
      - key: priority
        label: Priority
        format: colored-badge
      - key: assigned_role
        label: Owner
        format: text
      - key: next_action
        label: Next Action
        format: text
        truncate: 20
  columns: [4, 10, 2, 5, 10]
  refreshInterval: 60
  cacheDuration: 60
  actions:
    - label: "Details"
      icon: fas fa-arrow-right
      url: /missions/{mission_id}
  fallback:
    message: "No active missions loaded"
    useStaleData: true
```

**Rendering**:
```
┌─────────────────────────────────────────────┐
│ ACTIVE MISSIONS (8 total)                   │
├─────────────────────────────────────────────┤
│ ID      | Mission Title         | Pri | Own │
├─────────────────────────────────────────────┤
│ MSN-32  | Slack Voice Int.       | P0  | Eng │ [Details]
│ MSN-33  | Dashy Integration      | P1  | Ops │ [Details]
│ MSN-20  | Security Framework     | P1  | Inf │ [Details]
│ MSN-21  | Documentation          | P2  | Doc │ [Details]
│ MSN-22  | Testing Suite          | P2  | QA  │ [Details]
│         | +3 more...                         │
└─────────────────────────────────────────────┘
```

---

#### Widget 3: Daily Brief Summary
**Location**: INTELLIGENCE section  
**Size**: 2x1 (medium card)  
**Refresh**: 60 seconds (or manual)

```yaml
- name: Daily Intelligence Brief
  icon: fas fa-envelope
  type: BriefWidget
  data:
    source: /api/v1/coordination/daily-brief
    sections:
      - title: System Health
        icon: fas fa-heartbeat
        field: system_health.overall_status
        format: health-badge
      - title: Work Queue
        icon: fas fa-tasks
        field: work_queue.total_items
        format: number
      - title: Escalations
        icon: fas fa-exclamation-triangle
        field: escalations.count
        format: warning-badge
      - title: Follow-ups
        icon: fas fa-clock
        field: follow_ups.count
        format: number
  refreshInterval: 60
  cacheDuration: 60
  actions:
    - label: "Full Brief"
      url: /briefing/daily
    - label: "Escalations"
      url: /escalations
  fallback:
    message: "Unable to load daily brief"
    useStaleData: true
```

**Rendering**:
```
┌──────────────────────────────────────────┐
│ DAILY INTELLIGENCE BRIEF                 │
│ Generated: 08:00 UTC                     │
├──────────────────────────────────────────┤
│ System Health: OPERATIONAL ● (98%)        │
│ Work Queue: 12 items                      │
│ Escalations: 1 HIGH (needs attention)     │
│ Follow-ups: 3 (stale missions)            │
│                                          │
│ [VIEW FULL BRIEF] [ESCALATIONS]          │
└──────────────────────────────────────────┘
```

---

#### Widget 4: Blocked Missions Alert
**Location**: COMMAND section (above mission list)  
**Size**: 2x0.5 (alert bar)  
**Refresh**: 30 seconds

```yaml
- name: Blocked Missions Alert
  icon: fas fa-exclamation-triangle
  type: AlertWidget
  data:
    source: /api/v1/missions/blocked
    visible_if: "$.count > 0"
  render:
    template: |
      <div class="alert alert-warning">
        <strong>⚠ {count} Mission(s) Blocked</strong>
        {#each blocked_missions}
          <div>{mission_id}: {reason}</div>
        {/each}
      </div>
  actions:
    - label: "Review Blockers"
      url: /missions/blocked
  refreshInterval: 30
  fallback:
    message: "Blocker status unavailable"
    hidden: true
```

**Rendering**:
```
┌──────────────────────────────────────────────────────┐
│ ⚠ 1 MISSION BLOCKED                                  │
│ MSN-0028: Waiting for Risk Officer approval          │
│ [REVIEW BLOCKERS]                                    │
└──────────────────────────────────────────────────────┘
```

---

#### Widget 5: System Health Dashboard
**Location**: SHIP SYSTEMS section  
**Size**: 2x2 (medium card)  
**Refresh**: 30 seconds

```yaml
- name: System Health
  icon: fas fa-heartbeat
  type: HealthWidget
  data:
    source: /api/v1/health/services
    services:
      - name: Mission Registry
        field: services.mission_registry.status
      - name: Number One
        field: services.number_one.status
      - name: Slack
        field: services.slack_commander.status
      - name: Router
        field: services.semantic_router.status
      - name: GitHub
        field: services.github.status
      - name: Supabase
        field: services.supabase.status
  statusColorMap:
    operational: "#4CAF50"
    degraded: "#D4A017"
    unavailable: "#C94C4C"
  refreshInterval: 30
  cacheDuration: 30
  fallback:
    message: "Health status unavailable"
    useStaleData: true
```

**Rendering**:
```
┌─────────────────────────────────────┐
│ SYSTEM HEALTH                       │
│ Overall: OPERATIONAL (98%)          │
├─────────────────────────────────────┤
│ ● Mission Registry    [45ms]        │
│ ● Number One         [120ms]        │
│ ● Slack              [200ms]        │
│ ● Router              [85ms]        │
│ ● GitHub             [350ms]        │
│ ● Supabase           [150ms]        │
│                                     │
│ Last Check: 2026-06-08 12:30:00     │
└─────────────────────────────────────┘
```

---

#### Widget 6: Agent Status
**Location**: MEDICAL section (or dedicated AGENTS section)  
**Size**: 2x1 (medium card)  
**Refresh**: 60 seconds

```yaml
- name: Agent Status
  icon: fas fa-users
  type: StatusWidget
  data:
    source: /api/v1/agents/status
    layout: compact
    showWorkload: true
  columns:
    - key: role
      label: Role
    - key: status
      label: Status
      format: status-badge
    - key: workload_percent
      label: Load
      format: progress-bar
    - key: current_mission
      label: Current Task
      format: mission-id
  refreshInterval: 60
  cacheDuration: 60
  fallback:
    message: "Agent status unavailable"
    useStaleData: true
```

**Rendering**:
```
┌──────────────────────────────────────────────┐
│ AGENT STATUS                                 │
├──────────────────────────────────────────────┤
│ Chief Engineer    ● Active   [████████░] 75% │
│ Coder Agent       ○ Idle      [░░░░░░░░░] 0% │
│ Risk Officer      ● Active   [█████░░░░] 50% │
│ Executive Officer ● Active   [██░░░░░░░] 15% │
│ Knowledge Officer ○ Idle      [░░░░░░░░░] 0% │
│                                              │
│ Summary: 4 Active / 3 Idle / Avg Load 34%  │
└──────────────────────────────────────────────┘
```

---

### 3.2 Dashy Configuration Extensions

Add to `dashy-config.yml` in the `appConfig` section:

```yaml
appConfig:
  # ... existing config ...
  
  # Integration Configuration
  integrations:
    enabled: true
    baseUrl: "http://localhost:5000"  # API Gateway endpoint
    
    # API Configuration
    apis:
      missions:
        endpoint: "/api/v1/missions"
        timeout: 5000
        cacheDuration: 30
        fallbackToStale: true
      
      coordination:
        endpoint: "/api/v1/coordination"
        timeout: 5000
        cacheDuration: 60
        fallbackToStale: true
      
      health:
        endpoint: "/api/v1/health"
        timeout: 2000
        cacheDuration: 30
        fallbackToStale: true
      
      agents:
        endpoint: "/api/v1/agents"
        timeout: 5000
        cacheDuration: 60
        fallbackToStale: true
    
    # Real-Time Configuration
    realtime:
      enabled: true
      type: "websocket"  # or "sse" or "polling"
      websocketUrl: "ws://localhost:5000/api/v1/stream"
      reconnectInterval: 5000
      reconnectMaxAttempts: 10
      fallbackToPoll: true
      pollInterval: 30
      
      # Subscriptions
      subscriptions:
        - event: "mission.updated"
          refresh: ["mission-registry", "work-queue"]
        - event: "mission.blocked"
          refresh: ["blocked-missions", "daily-brief"]
        - event: "agent.status"
          refresh: ["agent-status"]
        - event: "health.status"
          refresh: ["system-health"]
    
    # Caching Configuration
    cache:
      enabled: true
      backend: "localStorage"  # or "sessionStorage"
      ttl: 3600
      showStaleDataWarning: true
    
    # Error Handling
    errorHandling:
      retryOn: [503, 504, "timeout"]
      retryCount: 3
      retryDelay: 1000
      showErrorBanner: true
      showOfflineIndicator: true
```

---

### 3.3 Widget Update Lifecycle

```
┌────────────────────────────────────────┐
│ Widget Mount / Initial Load            │
├────────────────────────────────────────┤
│ 1. Check cache (localStorage)          │
│    - If valid (not expired), render    │
│    - Initiate background fetch        │
│    - Show cached data while loading    │
│                                        │
│ 2. Fetch from API                      │
│    - 5s timeout per request            │
│    - Parallel requests for efficiency  │
│    - On success → Update cache & UI    │
│    - On failure → Show error + cache   │
│                                        │
│ 3. Subscribe to real-time updates      │
│    - WebSocket / SSE / Polling         │
│    - Listen for relevant events        │
│    - Update on change                  │
│                                        │
└────────────────────────────────────────┘

┌────────────────────────────────────────┐
│ Real-Time Update Received              │
├────────────────────────────────────────┤
│ 1. Validate update (checksum/version)  │
│ 2. Merge with existing state           │
│ 3. Update localStorage cache           │
│ 4. Trigger widget re-render            │
│ 5. Animate change (smooth transition)  │
│ 6. Update last-refresh timestamp       │
│                                        │
└────────────────────────────────────────┘

┌────────────────────────────────────────┐
│ Scheduled Refresh (per interval)       │
├────────────────────────────────────────┤
│ 1. Check if data is still valid        │
│ 2. If expired, fetch from API          │
│ 3. Update cache if changed             │
│ 4. Update UI if changed                │
│                                        │
└────────────────────────────────────────┘

┌────────────────────────────────────────┐
│ Widget Unmount                         │
├────────────────────────────────────────┤
│ 1. Unsubscribe from real-time events   │
│ 2. Clear refresh timers                │
│ 3. Final state saved to cache          │
│                                        │
└────────────────────────────────────────┘
```

---

## 4. Error Handling and Fallback Strategy

### 4.1 Error Handling Hierarchy

```
API Request
    │
    ├─ SUCCESS (200 OK)
    │  └─ Update cache + UI
    │
    ├─ CACHED (304 Not Modified)
    │  └─ Use existing cache
    │
    ├─ CLIENT ERROR (4xx)
    │  ├─ Invalid params (400)
    │  │  └─ Show validation error
    │  ├─ Not found (404)
    │  │  └─ Show "No data" message
    │  └─ Other (401, 403)
    │     └─ Show auth error
    │
    ├─ SERVER ERROR (5xx) / TIMEOUT
    │  ├─ Has valid cache?
    │  │  ├─ YES → Show stale data + warning
    │  │  └─ NO → Show error placeholder
    │  │
    │  ├─ Retry logic:
    │  │  ├─ Attempt 1: wait 1s
    │  │  ├─ Attempt 2: wait 2s
    │  │  ├─ Attempt 3: wait 5s
    │  │  └─ Give up: use cache/offline
    │  │
    │  └─ Show offline/error UI
    │
    └─ NETWORK ERROR
       ├─ No cache available?
       │  └─ Show placeholder + retry button
       └─ Cache available?
          └─ Show cached data + "offline" badge
```

---

### 4.2 Fallback Data Strategy

#### Primary Fallback: localStorage Cache

```javascript
// Widget loads with cached data if available
function loadWidgetData(endpoint, cacheKey) {
  // 1. Check cache
  const cached = localStorage.getItem(cacheKey);
  if (cached) {
    const data = JSON.parse(cached);
    if (!isExpired(data.timestamp)) {
      renderWidget(data, { isStale: false });
      fetchFresh();  // Fetch in background
      return;
    }
  }
  
  // 2. Fetch from API
  try {
    const fresh = await fetchWithTimeout(endpoint, 5000);
    localStorage.setItem(cacheKey, JSON.stringify({
      data: fresh,
      timestamp: Date.now()
    }));
    renderWidget(fresh, { isStale: false });
  } catch (error) {
    // 3. Use stale cache if available
    if (cached) {
      renderWidget(JSON.parse(cached), {
        isStale: true,
        warning: `Data from ${formatTime(cached.timestamp)}`
      });
    } else {
      renderError(`Unable to load ${endpoint}`);
    }
  }
}
```

#### Secondary Fallback: Placeholder Data

```javascript
// If no cache available, show placeholder
const placeholders = {
  missions: {
    total_missions: '—',
    active_missions: '—',
    by_priority: { P0: '?', P1: '?', P2: '?', P3: '?' }
  },
  health: {
    overall_status: 'UNKNOWN',
    services: {}
  }
};
```

#### Tertiary Fallback: Error UI

```javascript
// If all else fails, show error widget
function renderErrorWidget(error, retryFn) {
  return `
    <div class="error-widget">
      <div class="error-icon">⚠</div>
      <div class="error-message">${error.message}</div>
      <div class="error-timestamp">Failed at ${new Date().toLocaleTimeString()}</div>
      <button onclick="${retryFn}">Retry</button>
    </div>
  `;
}
```

---

### 4.3 Specific Error Scenarios

#### Scenario 1: Mission Registry API Down

**User Experience**:
```
MISSION REGISTRY SUMMARY
(cached data from 2 hours ago - STALE)

Total Active: 8
Blocked: 1
Top Priority: P0: 1

⚠ Data from 10:30 UTC (Last updated 2 hours ago)
[Refresh Now]
```

**Backend Handling**:
- Return cached data with staleness warning
- Include last-known timestamp
- Provide manual refresh button
- Log error for monitoring

---

#### Scenario 2: Number One Coordination API Timeout

**User Experience**:
```
DAILY INTELLIGENCE BRIEF
System Health: (unable to load)
Work Queue: (unable to load)
Escalations: None known

⚠ Unable to reach coordination service
[Retry] [Load from yesterday's brief]
```

**Backend Handling**:
- Fall back to yesterday's brief if available
- Show "no recent data" rather than error
- Queue request for retry in 10 seconds
- Alert operations team after 3 failures

---

#### Scenario 3: Complete Offline (No Internet)

**User Experience**:
```
MISSION REGISTRY (OFFLINE MODE)
Last synced: 2026-06-08 10:30 UTC

Total Active: 8
Blocked: 1
Top Priority: P0: 1

⚠ Working with cached data - some features unavailable
Sync will resume when connection restored
```

**Backend Handling**:
- Display all available cached data
- Disable real-time updates
- Queue changes in local IndexedDB
- Sync on reconnection

---

### 4.4 Recovery Mechanisms

#### Automatic Recovery

```javascript
class ApiRecovery {
  // 1. Progressive backoff retry
  async retryWithBackoff(fn, maxAttempts = 3) {
    for (let i = 0; i < maxAttempts; i++) {
      try {
        return await fn();
      } catch (error) {
        const delay = Math.pow(2, i) * 1000;  // 1s, 2s, 4s
        console.log(`Retry attempt ${i+1} in ${delay}ms`);
        await sleep(delay);
      }
    }
    throw new Error('Max retries exceeded');
  }
  
  // 2. Fallback to secondary endpoint
  async fetchWithFallback(endpoints) {
    for (const endpoint of endpoints) {
      try {
        return await fetch(endpoint, { timeout: 5000 });
      } catch (error) {
        console.log(`Endpoint ${endpoint} failed, trying next`);
      }
    }
    throw new Error('All endpoints failed');
  }
  
  // 3. Use stale data with auto-refresh
  async loadWithFallback(endpoint, cacheKey) {
    try {
      const fresh = await fetch(endpoint);
      cache.set(cacheKey, fresh);
      return fresh;
    } catch (error) {
      const stale = cache.get(cacheKey);
      if (stale) {
        // Queue background refresh
        setTimeout(() => this.refresh(endpoint), 10000);
        return { ...stale, isStale: true };
      }
      throw error;
    }
  }
}
```

#### Manual Recovery

- **Retry Button**: Each error widget has "Retry Now" button
- **Refresh Widget**: Widget-level refresh in header
- **Dashboard Refresh**: Full dashboard refresh (F5 or button)
- **Clear Cache**: User option to clear all caches and reload fresh

---

## 5. Real-Time Update Mechanism

### 5.1 Design Decision: WebSocket vs SSE vs Polling

| Aspect | WebSocket | SSE | Polling |
|--------|-----------|-----|---------|
| **Latency** | <100ms | <500ms | 30-60s |
| **Overhead** | Low | Low | Medium-High |
| **Complexity** | Medium | Low | Low |
| **Browser Support** | 99%+ | 95%+ | 100% |
| **Firewall Issues** | Yes | No | No |
| **Fallback** | Polling | Polling | N/A |
| **Recommended** | Primary | Secondary | Fallback |

**Decision**: **WebSocket** as primary with **Polling** as fallback.

---

### 5.2 WebSocket Implementation

#### Server: WebSocket Event Stream

```python
# FastAPI example with WebSockets
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json

@app.websocket("/api/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.
    
    Client subscribes to events:
    {
      "action": "subscribe",
      "events": ["mission.updated", "health.status"]
    }
    
    Server sends updates:
    {
      "event": "mission.updated",
      "timestamp": "2026-06-08T12:30:45Z",
      "data": { "mission_id": "MSN-0032", ... }
    }
    """
    await websocket.accept()
    subscriptions = set()
    
    try:
        while True:
            message = await websocket.receive_text()
            msg = json.loads(message)
            
            if msg['action'] == 'subscribe':
                subscriptions.update(msg['events'])
                await websocket.send_json({
                    'event': 'subscribed',
                    'subscriptions': list(subscriptions)
                })
            
            elif msg['action'] == 'unsubscribe':
                subscriptions -= set(msg['events'])
    
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close()

# Event broadcasting
async def broadcast_event(event_type: str, data: dict):
    """
    Broadcast event to all subscribed clients.
    """
    message = {
        'event': event_type,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'data': data
    }
    
    for connection in active_connections:
        if event_type in connection.subscriptions:
            try:
                await connection.websocket.send_json(message)
            except Exception as e:
                print(f"Failed to send to client: {e}")

# Hook into mission updates
async def on_mission_updated(mission_id: str, old_status: str, new_status: str):
    """Called when mission status changes."""
    await broadcast_event('mission.updated', {
        'mission_id': mission_id,
        'old_status': old_status,
        'new_status': new_status,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })
```

#### Client: WebSocket Connection

```javascript
class DashboardWebSocket {
  constructor() {
    this.url = 'ws://localhost:5000/api/v1/stream';
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.reconnectDelay = 5000;
    this.subscriptions = new Set();
    this.eventHandlers = {};
  }
  
  connect() {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);
        
        this.ws.onopen = () => {
          console.log('WebSocket connected');
          this.reconnectAttempts = 0;
          
          // Re-subscribe to previous subscriptions
          this.subscribe([...this.subscriptions]);
          
          resolve();
        };
        
        this.ws.onmessage = (event) => {
          const message = JSON.parse(event.data);
          
          if (message.event === 'subscribed') {
            console.log('Subscriptions updated', message.subscriptions);
          } else {
            // Fire event handlers
            const handlers = this.eventHandlers[message.event] || [];
            handlers.forEach(handler => handler(message.data));
            
            // Update cache
            this.updateCache(message);
          }
        };
        
        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          reject(error);
        };
        
        this.ws.onclose = () => {
          console.log('WebSocket disconnected');
          this.attemptReconnect();
        };
      } catch (error) {
        reject(error);
      }
    });
  }
  
  subscribe(events) {
    events.forEach(event => this.subscriptions.add(event));
    
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        action: 'subscribe',
        events: events
      }));
    }
  }
  
  on(eventType, handler) {
    if (!this.eventHandlers[eventType]) {
      this.eventHandlers[eventType] = [];
    }
    this.eventHandlers[eventType].push(handler);
  }
  
  off(eventType, handler) {
    if (this.eventHandlers[eventType]) {
      this.eventHandlers[eventType] = 
        this.eventHandlers[eventType].filter(h => h !== handler);
    }
  }
  
  attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached, falling back to polling');
      enablePolling();
      return;
    }
    
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    
    setTimeout(() => this.connect().catch(() => {}), delay);
  }
  
  updateCache(message) {
    const cacheKey = `ws_${message.event}`;
    localStorage.setItem(cacheKey, JSON.stringify({
      data: message.data,
      timestamp: message.timestamp
    }));
  }
  
  disconnect() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

// Usage in dashboard
const dashboard = new DashboardWebSocket();

dashboard.on('mission.updated', (data) => {
  console.log('Mission updated:', data.mission_id);
  updateMissionWidget(data);
});

dashboard.on('health.status', (data) => {
  console.log('Health status:', data.overall_status);
  updateHealthWidget(data);
});

dashboard.subscribe([
  'mission.updated',
  'mission.blocked',
  'agent.status',
  'health.status'
]);

dashboard.connect();
```

---

### 5.3 Polling Fallback Implementation

```javascript
class PollingUpdater {
  constructor(config = {}) {
    this.endpoints = config.endpoints || {
      missions: { url: '/api/v1/missions/summary', interval: 30000 },
      health: { url: '/api/v1/health/services', interval: 30000 },
      agents: { url: '/api/v1/agents/status', interval: 60000 }
    };
    this.timers = {};
    this.lastValues = {};
  }
  
  start() {
    Object.entries(this.endpoints).forEach(([key, config]) => {
      this.poll(key, config);
    });
  }
  
  async poll(key, config) {
    try {
      const response = await fetch(config.url);
      const data = await response.json();
      
      // Compare with last value
      if (JSON.stringify(data) !== JSON.stringify(this.lastValues[key])) {
        this.lastValues[key] = data;
        
        // Fire event (same as WebSocket)
        window.dispatchEvent(new CustomEvent(`poll_${key}`, { detail: data }));
      }
    } catch (error) {
      console.error(`Poll failed for ${key}:`, error);
    }
    
    // Schedule next poll
    this.timers[key] = setTimeout(
      () => this.poll(key, config),
      config.interval
    );
  }
  
  stop() {
    Object.values(this.timers).forEach(timer => clearTimeout(timer));
  }
}

// Usage
const poller = new PollingUpdater();

window.addEventListener('poll_missions', (e) => {
  updateMissionWidget(e.detail);
});

poller.start();
```

---

### 5.4 Server-Sent Events (SSE) Alternative

```javascript
// Client: SSE Connection
const eventSource = new EventSource('/api/v1/stream?events=mission.updated,health.status');

eventSource.addEventListener('mission.updated', (event) => {
  const data = JSON.parse(event.data);
  updateMissionWidget(data);
});

eventSource.addEventListener('health.status', (event) => {
  const data = JSON.parse(event.data);
  updateHealthWidget(data);
});

eventSource.onerror = () => {
  console.error('SSE connection lost, falling back to polling');
  enablePolling();
};

// Server: SSE Stream
@app.get("/api/v1/stream")
async def sse_stream(request: Request, events: str = ""):
    """Server-Sent Events stream for real-time updates."""
    event_types = set(events.split(',')) if events else set()
    
    async def event_generator():
        queue = asyncio.Queue()
        
        # Subscribe to events
        for event_type in event_types:
            event_bus.subscribe(event_type, queue)
        
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=60)
                yield f"event: {event['type']}\n"
                yield f"data: {json.dumps(event['data'])}\n\n"
        except asyncio.TimeoutError:
            yield ": keep-alive\n\n"
        except GeneratorExit:
            for event_type in event_types:
                event_bus.unsubscribe(event_type, queue)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## 6. Implementation Roadmap

### Phase 2 Implementation Timeline: 3-5 Days

#### Day 1: API Gateway & Mission Registry Integration

**Tasks**:
- [ ] Create API Gateway wrapper around existing systems
- [ ] Implement `/api/v1/missions/summary` endpoint
- [ ] Implement `/api/v1/missions/active` endpoint
- [ ] Implement `/api/v1/missions/blocked` endpoint
- [ ] Add response caching (Redis or in-memory)
- [ ] Implement error handling and fallback responses

**Deliverables**:
- API Gateway running on port 5000
- Mission Registry endpoints tested and working
- Cache layer functional
- Error responses validated

**Testing**:
```bash
curl http://localhost:5000/api/v1/missions/summary
curl http://localhost:5000/api/v1/missions/active
curl http://localhost:5000/api/v1/missions/blocked?priority=P0
```

---

#### Day 2: Coordination Engine & Health Integration

**Tasks**:
- [ ] Implement `/api/v1/coordination/daily-brief` endpoint
- [ ] Implement `/api/v1/coordination/work-queue` endpoint
- [ ] Implement `/api/v1/coordination/escalations` endpoint
- [ ] Implement `/api/v1/health/services` endpoint
- [ ] Implement `/api/v1/health/overall` endpoint
- [ ] Integrate Number One data structures
- [ ] Add health check scheduling

**Deliverables**:
- Coordination endpoints tested
- Health monitoring running
- Real-time service health checks
- Daily brief generation working

**Testing**:
```bash
curl http://localhost:5000/api/v1/coordination/daily-brief
curl http://localhost:5000/api/v1/coordination/work-queue
curl http://localhost:5000/api/v1/health/services
```

---

#### Day 3: Agent Status & Real-Time Setup

**Tasks**:
- [ ] Implement `/api/v1/agents/status` endpoint
- [ ] Create WebSocket server (`/api/v1/stream`)
- [ ] Implement event broadcasting system
- [ ] Create polling fallback system
- [ ] Set up event subscriptions
- [ ] Test WebSocket connections and message delivery

**Deliverables**:
- Agent status endpoint working
- WebSocket server running
- Event broadcasting functional
- Fallback polling implemented

**Testing**:
```bash
# Test agent status
curl http://localhost:5000/api/v1/agents/status

# Test WebSocket
wscat -c ws://localhost:5000/api/v1/stream
```

---

#### Day 4: Dashy Integration & Widget Configuration

**Tasks**:
- [ ] Create dynamic widget components for Dashy
- [ ] Configure Mission Registry Summary widget
- [ ] Configure Active Missions list widget
- [ ] Configure Daily Brief widget
- [ ] Configure System Health widget
- [ ] Configure Agent Status widget
- [ ] Configure Blocked Missions alert
- [ ] Test cache integration with localStorage
- [ ] Test fallback rendering

**Deliverables**:
- All widgets rendering with live data
- Cache working correctly
- Fallback data displayed properly
- Real-time updates flowing through

**Testing**:
- Manual testing of each widget
- Browser console verification
- Cache inspection via DevTools
- Simulate API failures and verify fallback

---

#### Day 5: Error Handling, Testing & Documentation

**Tasks**:
- [ ] Implement comprehensive error handling
- [ ] Test all error scenarios (timeouts, crashes, offline)
- [ ] Verify fallback data rendering
- [ ] Performance testing (dashboard load < 2s)
- [ ] Load testing (concurrent users)
- [ ] Cross-browser testing
- [ ] Write integration documentation
- [ ] Create troubleshooting guide

**Deliverables**:
- All error scenarios handled
- Performance targets met
- Full test suite passing
- Documentation complete
- Phase 2 ready for production

**Testing**:
```bash
# Performance testing
lighthouse http://localhost:8080 --view

# Load testing
ab -n 100 -c 10 http://localhost:5000/api/v1/missions/summary

# Timeout testing
timeout --signal=KILL 2 curl http://localhost:5000/api/v1/health/services
```

---

### Deployment Checklist

- [ ] API Gateway deployed and running
- [ ] All endpoints tested and validated
- [ ] WebSocket/polling fallback tested
- [ ] Dashy configuration updated with new widgets
- [ ] Cache layer configured and tested
- [ ] Error handling verified
- [ ] Performance targets met
- [ ] Documentation complete
- [ ] Rollback plan prepared
- [ ] Monitoring alerts configured

---

## 7. Open Questions and Risks

### 7.1 Open Questions

#### Architecture

1. **API Gateway Location**
   - Question: Should the API Gateway be a separate process or integrated into existing backend?
   - Impact: Affects deployment complexity and failure modes
   - Decision Needed: Separate (recommended) vs Integrated

2. **Authentication/Authorization**
   - Question: Do we need auth for dashboard APIs, or is it internal-only?
   - Impact: Security, operational overhead
   - Current Plan: Internal-only, no auth required
   - Decision Needed: Confirm scope of access control

3. **Real-Time Technology**
   - Question: Will WebSocket work across all firewalls, or should we default to polling?
   - Impact: Latency and user experience
   - Recommendation: WebSocket with polling fallback (robust)
   - Decision Needed: Confirm firewall compatibility

#### Data & Integration

4. **Agent Status Source**
   - Question: How do we determine agent availability? (System events, heartbeats, manual status?)
   - Impact: Accuracy of agent status display
   - Current Assumption: From execution logs and heartbeats
   - Decision Needed: Confirm integration point

5. **Health Check Endpoints**
   - Question: Do all services have `/status` endpoints, or do we need to create them?
   - Impact: Health monitoring completeness
   - Current Assumption: Will need to add/standardize endpoints
   - Decision Needed: Create abstraction layer or update each service?

#### Operational

6. **Data Retention Policy**
   - Question: How long should cached data be retained in localStorage?
   - Impact: Storage usage, data freshness
   - Recommendation: 1 week for missions, 24 hours for health
   - Decision Needed: Confirm retention policy

7. **Monitoring & Alerting**
   - Question: What metrics should we monitor? (API latency, error rates, cache hits?)
   - Impact: Operational visibility
   - Recommendation: Log all API calls, monitor 95th percentile latency
   - Decision Needed: Set up monitoring infrastructure

---

### 7.2 Risks and Mitigation

#### Risk 1: API Latency Impact on Dashboard

**Risk**: If backend APIs are slow, dashboard becomes sluggish.

**Probability**: Medium  
**Impact**: High (poor user experience)

**Mitigation**:
- Cache all endpoints aggressively (30-60 second TTL)
- Implement request timeout (5 seconds max)
- Use stale data as fallback
- Parallel API requests, not sequential
- Monitor API response times

**Success Criteria**: Dashboard loads in < 2 seconds with cache hits

---

#### Risk 2: WebSocket Connection Failures

**Risk**: WebSocket may fail due to firewalls, proxies, or server issues.

**Probability**: Medium  
**Impact**: Medium (degrades to polling)

**Mitigation**:
- Implement automatic fallback to polling
- Exponential backoff for reconnection attempts
- Monitor WebSocket connection success rate
- Provide diagnostic info in browser console
- Alert operations team if WebSocket down > 5 minutes

**Success Criteria**: System remains functional even if WebSocket unavailable

---

#### Risk 3: Cache Invalidation Complexity

**Risk**: Stale data shown to users, especially around mission state changes.

**Probability**: Medium  
**Impact**: Medium (confusion, missed updates)

**Mitigation**:
- Use event-driven cache invalidation (WebSocket events)
- Implement cache versioning/checksums
- Show "Last Updated" timestamps
- Provide manual refresh button
- Warn users when data is stale (> 5 min old)

**Success Criteria**: Users see updated data within 30 seconds of change

---

#### Risk 4: Number One Integration Complexity

**Risk**: Number One system has complex state, may be difficult to expose via API.

**Probability**: Medium  
**Impact**: Medium (requires design adjustments)

**Mitigation**:
- Implement incremental integration (basic first, advanced later)
- Create adapter layer to translate Number One data to API format
- Start with daily brief (least complex)
- Add work queue and escalations next
- Async update Number One data independently

**Success Criteria**: All Number One APIs working by end of Phase 2

---

#### Risk 5: Concurrent State Updates

**Risk**: Multiple updates to same mission could cause race conditions.

**Probability**: Low  
**Impact**: High (data corruption)

**Mitigation**:
- Use optimistic locking with version numbers
- Implement conflict resolution (last-write-wins or user-prompted)
- Log all conflicts for debugging
- Test concurrent update scenarios
- Design idempotent operations

**Success Criteria**: No data corruption even with concurrent updates

---

#### Risk 6: Third-Party API Unavailability (GitHub, Slack, Supabase)

**Risk**: External services may be unavailable, breaking health dashboard.

**Probability**: Low  
**Impact**: Medium (incomplete status)

**Mitigation**:
- Cache health checks results (30 second TTL minimum)
- Skip non-critical services if down (don't fail dashboard)
- Show "last known status" for unavailable services
- Don't count external service failures against overall health
- Alert for external service issues separately

**Success Criteria**: Dashboard remains operational even if external services down

---

### 7.3 Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Dashboard Load Time | < 2 seconds | First paint with cached data |
| API Response Time (p95) | < 500ms | Mission Registry endpoints |
| WebSocket Latency | < 100ms | Event delivery to client |
| Cache Hit Rate | > 80% | Percentage of requests from cache |
| Real-Time Update Latency | < 1 second | From server event to UI update |
| Widget Refresh Jank | None | Smooth transitions, no frame drops |
| Memory Usage | < 50MB | Dashboard JavaScript runtime |
| Network Transfer | < 5MB/min | Average bandwidth usage |

---

### 7.4 Future Considerations (Phase 3+)

1. **Advanced Caching**
   - Implement IndexedDB for larger datasets
   - Service Worker for offline support
   - Automatic cache syncing on reconnect

2. **User Customization**
   - Custom dashboard layouts
   - Widget favoriting and pinning
   - Dark/Light theme toggle
   - Font size adjustment

3. **Advanced Analytics**
   - Mission completion metrics
   - Specialist utilization tracking
   - Team velocity tracking
   - Bottleneck analysis

4. **Mobile Support**
   - Responsive widgets
   - Mobile-optimized API endpoints
   - Touch-friendly interactions

5. **Notifications**
   - Browser push notifications
   - Email digests
   - Slack integration for alerts
   - In-dashboard toast notifications

6. **Audit & Compliance**
   - Full audit trail of all changes
   - User activity logging
   - Data export functionality
   - Compliance reporting

---

## Conclusion

Phase 2 Integration Architecture provides a comprehensive blueprint for connecting STARFLEET COMMAND CENTRE to live operational data. The design prioritizes:

1. **Robustness**: Multiple fallback mechanisms ensure dashboard works even when backends fail
2. **Performance**: Aggressive caching and parallel requests keep dashboard snappy
3. **User Experience**: Smooth updates, clear status indicators, minimal disruption
4. **Maintainability**: Clear API contracts, error handling standards, monitoring

**Timeline**: 3-5 days for full implementation  
**Status**: Ready to proceed with development  
**Next Step**: Begin Day 1 API Gateway implementation

---

**Document Status**: READY FOR IMPLEMENTATION  
**Created**: 2026-06-08  
**Phase 2 Start Target**: 2026-06-09  
**Phase 2 Completion Target**: 2026-06-13  

---

*Ad Astra Per Aspera* — Onwards to the stars

**STARFLEET COMMAND CENTRE — MSN-0035 Phase 2 Plan**
