# Control Engine API Reference

**Version:** 1.0 (Phase 1 MVP)  
**Mission:** M-20260609-000000  
**Base URL:** `http://localhost:8888/api`  
**Port:** 8888 (localhost only, Phase 1)

---

## Overview

The Control Engine is a lightweight HTTP API that wraps USS-TJR-Control shell scripts and provides REST endpoints for:
- Service lifecycle management (start, stop, restart, status)
- Real-time system health monitoring
- Mission tracking and awareness
- Dashboard integration

**Key Design Principles:**
- Wraps existing CLI infrastructure (no reimplementation)
- Reads from existing sources (logs, mission files, status.command)
- Stateless Phase 1 (read-only for missions, non-destructive for services)
- No authentication Phase 1 (localhost-only)
- No new databases (state from existing sources)

**Canonical launch path:** `USS-TJR-Control/scripts/start-control-engine.sh`

---

## API Endpoints

### Root & Health

#### GET `/` or `/api`
Get API information and available endpoints.

**Response:**
```json
{
  "name": "Control Engine",
  "version": "1.0",
  "mission": "M-20260609-000000",
  "status": "operational",
  "endpoints": {
    "health": {...},
    "lifecycle": {...},
    "logs": {...},
    "missions": {...},
    "dashboard": {...}
  },
  "timestamp": "2026-06-08T15:30:00Z"
}
```

#### GET `/healthz`
Kubernetes-style health check (always returns 200 OK if Control Engine is responsive).

**Response:**
```json
{
  "status": "ok"
}
```

---

## Health & Status Endpoints

### GET `/api/health`
Get overall system health by parsing USS-TJR-Control/status.command.

**Response:**
```json
{
  "status": "operational | degraded | offline",
  "services": {
    "Slack Bot": {
      "status": "operational",
      "timestamp": "2026-06-08T15:30:00Z"
    },
    "Commander": {
      "status": "operational",
      "timestamp": "2026-06-08T15:30:00Z"
    },
    "Ollama": {
      "status": "operational",
      "timestamp": "2026-06-08T15:30:00Z"
    }
  },
  "timestamp": "2026-06-08T15:30:00Z"
}
```

**Status Values:**
- `operational` — Service is running and healthy
- `degraded` — Service is running but at reduced capacity
- `offline` — Service is not running

---

### GET `/api/services/status`
Get status of all configured services.

**Response:**
```json
{
  "services": {
    "Slack Bot": {
      "status": "operational",
      "timestamp": "2026-06-08T15:30:00Z"
    },
    "Commander": {
      "status": "operational",
      "timestamp": "2026-06-08T15:30:00Z"
    },
    "Ollama": {
      "status": "operational",
      "timestamp": "2026-06-08T15:30:00Z"
    }
  },
  "timestamp": "2026-06-08T15:30:00Z"
}
```

---

### GET `/api/services/status/<service>`
Get status of a specific service.

**Path Parameters:**
- `service` — Service name (slack-bot, commander, ollama, etc.)

**Response (200 OK):**
```json
{
  "service": "slack-bot",
  "status": "operational",
  "timestamp": "2026-06-08T15:30:00Z"
}
```

**Response (404 Not Found):**
```json
{
  "error": "Service slack-bot not found in status",
  "timestamp": "2026-06-08T15:30:00Z"
}
```

---

## Service Lifecycle Endpoints

### POST `/api/services/start/<service>`
Start a service by running USS-TJR-Control/scripts/start-<service>.sh

**Returns immediately (202 Accepted) — service starts in background**

**Path Parameters:**
- `service` — Service name (slack-bot, commander, ollama, etc.)

**Response (202 Accepted):**
```json
{
  "message": "Service slack-bot starting...",
  "service": "slack-bot",
  "script": "/path/to/start-slack-bot.sh",
  "timestamp": "2026-06-08T15:30:00Z"
}
```

**Response (404 Not Found):**
```json
{
  "error": "Service slack-bot not found",
  "message": "Script ./scripts/start-slack-bot.sh does not exist",
  "timestamp": "2026-06-08T15:30:00Z"
}
```

**Response (500 Internal Server Error):**
```json
{
  "error": "Failed to start service",
  "service": "slack-bot",
  "message": "Error details...",
  "timestamp": "2026-06-08T15:30:00Z"
}
```

---

### POST `/api/services/stop/<service>`
Stop a service by killing its process (pgrep + kill pattern).

**Path Parameters:**
- `service` — Service name

**Response (200 OK):**
```json
{
  "message": "Service slack-bot stopped",
  "service": "slack-bot",
  "pids_killed": ["12345", "12346"],
  "timestamp": "2026-06-08T15:30:00Z"
}
```

**Response (404 Not Found):**
```json
{
  "error": "Service not running",
  "service": "slack-bot",
  "message": "No process found matching pattern: app.py",
  "timestamp": "2026-06-08T15:30:00Z"
}
```

---

### POST `/api/services/restart/<service>`
Restart a service (stop then start).

**Path Parameters:**
- `service` — Service name

**Response (202 Accepted):**
```json
{
  "message": "Service slack-bot restarting...",
  "service": "slack-bot",
  "timestamp": "2026-06-08T15:30:00Z"
}
```

---

## Service Logs Endpoints

### GET `/api/services/logs/<service>`
Get recent logs for a service from USS-TJR-Control/logs/<service>.log

**Path Parameters:**
- `service` — Service name

**Query Parameters:**
- `lines` — Number of lines to return (default 50, max 500)

**Response (200 OK):**
```json
{
  "service": "slack-bot",
  "lines": 50,
  "logs": [
    "2026-06-08 15:30:00 [INFO] Slack Bot started",
    "2026-06-08 15:30:01 [INFO] Connected to Slack",
    "...",
    "2026-06-08 15:31:45 [INFO] Received message: hello"
  ],
  "timestamp": "2026-06-08T15:31:50Z"
}
```

**Response (404 Not Found):**
```json
{
  "error": "Log file not found",
  "service": "slack-bot",
  "path": "/path/to/logs/slack-bot.log",
  "timestamp": "2026-06-08T15:31:50Z"
}
```

**Example Usage:**
```bash
# Get last 50 lines (default)
curl http://localhost:8888/api/services/logs/slack-bot

# Get last 100 lines
curl http://localhost:8888/api/services/logs/slack-bot?lines=100

# Get last 10 lines (useful for tailing)
curl http://localhost:8888/api/services/logs/slack-bot?lines=10
```

---

## Mission Management Endpoints

### GET `/api/missions/active`
Get list of active missions (from mission_manager.py).

**Response (200 OK):**
```json
{
  "missions": [
    {
      "mission_id": "M-20260609-000000",
      "timestamp": "2026-06-08 10:15",
      "domain": "Control Deck",
      "status": "Active",
      "title": "Control Deck v1.1 — Operational Usability Enhancements"
    },
    {
      "mission_id": "MSN-0040A-WP2",
      "timestamp": "2026-06-07 14:30",
      "domain": "Integration",
      "status": "Active",
      "title": "WP2 Integration & Automation"
    }
  ],
  "count": 2,
  "timestamp": "2026-06-08T15:31:50Z"
}
```

---

### GET `/api/missions/completed`
Get list of completed missions.

**Response (200 OK):**
```json
{
  "missions": [
    {
      "mission_id": "M-20260608-000000",
      "timestamp": "2026-06-08 09:00",
      "domain": "Control Deck",
      "status": "Completed",
      "title": "Command Layer Assessment"
    }
  ],
  "count": 42,
  "timestamp": "2026-06-08T15:31:50Z"
}
```

---

### GET `/api/missions/recent`
Get recent missions (most recent first).

**Query Parameters:**
- `limit` — Number of missions to return (default 10, max 100)

**Response (200 OK):**
```json
{
  "missions": [
    {
      "mission_id": "M-20260609-000000",
      "timestamp": "2026-06-08 10:15",
      "domain": "Control Deck",
      "status": "Active",
      "title": "Control Deck v1.1"
    },
    {
      "mission_id": "M-20260608-000000",
      "timestamp": "2026-06-08 09:00",
      "domain": "Control Deck",
      "status": "Completed",
      "title": "Command Layer Assessment"
    }
  ],
  "count": 10,
  "timestamp": "2026-06-08T15:31:50Z"
}
```

**Example Usage:**
```bash
# Get last 10 missions (default)
curl http://localhost:8888/api/missions/recent

# Get last 20 missions
curl http://localhost:8888/api/missions/recent?limit=20

# Get last 3 missions
curl http://localhost:8888/api/missions/recent?limit=3
```

---

### GET `/api/missions/this-week`
Get missions completed this week.

**Response (200 OK):**
```json
{
  "missions": [
    {
      "mission_id": "M-20260608-000000",
      "timestamp": "2026-06-08 09:00",
      "domain": "Control Deck",
      "status": "Completed",
      "title": "Command Layer Assessment"
    }
  ],
  "count": 7,
  "timestamp": "2026-06-08T15:31:50Z"
}
```

---

## Dashboard Integration Endpoints

### GET `/api/dashboard/summary`
Get a comprehensive summary for Control Deck dashboard display.

**Response (200 OK):**
```json
{
  "status": "operational",
  "services": {
    "operational": 5,
    "degraded": 0,
    "offline": 0,
    "total": 5
  },
  "missions": {
    "active": 3,
    "completed_this_week": 7
  },
  "recent_missions": [
    {
      "mission_id": "M-20260609-000000",
      "timestamp": "2026-06-08 10:15",
      "domain": "Control Deck",
      "status": "Active",
      "title": "Control Deck v1.1"
    },
    {
      "mission_id": "MSN-0040A-WP2",
      "timestamp": "2026-06-07 14:30",
      "domain": "Integration",
      "status": "Active",
      "title": "WP2 Integration"
    },
    {
      "mission_id": "M-20260608-000000",
      "timestamp": "2026-06-08 09:00",
      "domain": "Control Deck",
      "status": "Completed",
      "title": "Command Layer Assessment"
    }
  ],
  "timestamp": "2026-06-08T15:31:50Z"
}
```

**Use Case:** Dashboard queries this single endpoint to get all data needed for operational awareness display.

---

## HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Successful read/write operation |
| 202 | Accepted | Service start request accepted (starts in background) |
| 400 | Bad Request | Invalid request format |
| 404 | Not Found | Service/resource not found |
| 500 | Internal Server Error | Server-side error (script execution failure, I/O error, etc.) |

---

## Error Handling

All error responses include:
- `error` — Error type/code
- `message` — Human-readable error message
- `timestamp` — ISO 8601 timestamp

**Example Error Response:**
```json
{
  "error": "Service not running",
  "service": "slack-bot",
  "message": "No process found matching pattern: app.py",
  "timestamp": "2026-06-08T15:31:50Z"
}
```

---

## Usage Examples

### Bash/curl

**Check system health:**
```bash
curl http://localhost:8888/api/health
```

**Start Slack Bot:**
```bash
curl -X POST http://localhost:8888/api/services/start/slack-bot
```

**Get service logs:**
```bash
curl http://localhost:8888/api/services/logs/slack-bot?lines=20
```

**Get active missions:**
```bash
curl http://localhost:8888/api/missions/active
```

**Get dashboard summary:**
```bash
curl http://localhost:8888/api/dashboard/summary
```

---

### JavaScript/fetch

**Check system health:**
```javascript
const response = await fetch('http://localhost:8888/api/health');
const health = await response.json();
console.log(`System status: ${health.status}`);
```

**Start service:**
```javascript
const response = await fetch('http://localhost:8888/api/services/start/slack-bot', {
  method: 'POST'
});
const result = await response.json();
console.log(result.message);
```

**Get dashboard data:**
```javascript
const response = await fetch('http://localhost:8888/api/dashboard/summary');
const summary = await response.json();

// Update UI with service counts
document.getElementById('operational').textContent = summary.services.operational;
document.getElementById('offline').textContent = summary.services.offline;

// Display recent missions
summary.recent_missions.forEach(mission => {
  console.log(`${mission.mission_id}: ${mission.title}`);
});
```

---

## Integration with Control Deck Dashboard

**Phase 2 Plan:** Integrate Control Engine API with Dashy v1.1 dashboard:

1. **Service Status Cards** — Fetch from `/api/health` and refresh every 30 seconds
2. **Recent Missions** — Fetch from `/api/missions/recent?limit=3` and refresh every 60 seconds
3. **Start/Stop Buttons** — Call `/api/services/start/<service>` and `/api/services/stop/<service>`
4. **Dashboard Summary** — Fetch from `/api/dashboard/summary` for at-a-glance operational awareness

---

## Configuration & Startup

### Starting Control Engine

**Manual startup:**
```bash
cd ~/Documents/GitHub/USSTJROS/USS-TJR-Control
bash scripts/start-control-engine.sh
```

**Integrated startup (in USS-TJR-Control):**
```bash
./start.command  # Starts all services including Control Engine
```

### Configuration Files

- `USS-TJR-Control/config/services.conf` — Service definitions (loaded by Control Engine)
- `core/command-centre/control_engine.py` — Main Control Engine code
- `USS-TJR-Control/scripts/start-control-engine.sh` — Startup script

### Logs

- `USS-TJR-Control/logs/control-engine.log` — Control Engine application log
- `USS-TJR-Control/logs/slack-bot.log` — Slack Bot service logs
- `USS-TJR-Control/logs/commander.log` — Commander service logs
- etc.

---

## Limitations (Phase 1)

- **No authentication** — Localhost only (authentication in Phase 2)
- **No service restart safety checks** — Kill/restart happen immediately (safety checks in Phase 2)
- **No service dependency ordering** — Can start/stop services in any order (orchestration in Phase 2)
- **No health polling** — Status is point-in-time from `status.command` (polling in Phase 3)
- **No automatic recovery** — Failed services not automatically restarted (monitoring in Phase 3)

---

## Future Enhancements (Phase 2+)

- Token-based authentication
- Service dependency graphs
- Background health polling with alerting
- Automatic service restart on failure
- WebSocket support for real-time updates
- Service metrics (CPU, memory, uptime)
- Slack integration for service alerts

---

**Version:** 1.0 (Phase 1 MVP)  
**Last Updated:** June 8, 2026  
**Mission:** M-20260609-000000
