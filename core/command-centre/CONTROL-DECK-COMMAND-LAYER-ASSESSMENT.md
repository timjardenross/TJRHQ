# Control Deck Command Layer Assessment

**Mission:** M-20260609-000000  
**Assessment Date:** June 8, 2026  
**Status:** COMPLETE  
**Recommendation:** **PROCEED**

---

## Executive Summary

The USS TJR control infrastructure is ready for a lightweight API wrapper that will enable the Control Deck dashboard to launch and monitor services. Existing components (USS-TJR-Control shell scripts, mission manager, Slack Bot foundation) provide a solid base. A minimal HTTP API (Flask/FastAPI, ~500 lines) will bridge the gap between the dashboard and existing CLI.

**Recommendation:** PROCEED with Control Engine MVP (Phase 1)

**Estimated Effort:**
- Phase 1 (MVP): 2-3 days
- Phase 2 (Monitoring): 1-2 days
- Total for basic operational capability: 3-5 days

---

## 1. Current State Assessment

### 1.1 Existing CLI Infrastructure

**Location:** `USS-TJR-Control/`  
**Status:** Fully functional, well-hardened (MSN-0013)

| Component | File | Purpose | Status |
|-----------|------|---------|--------|
| Service Config | `config/services.conf` | Central config: paths, ports, commands | ✅ Complete |
| Startup Scripts | `scripts/start-*.sh` (5 total) | Launch Slack Bot, Commander, Paperclip, etc. | ✅ Complete |
| Control Commands | `start.command`, `stop.command`, `restart.command` | User-facing macOS actions | ✅ Complete |
| Status Command | `status.command` | Real-time health checks | ✅ Complete |
| Logging | `logs/` directory | Persistent output per service | ✅ Complete |

**Assessment:** The CLI is production-ready. All paths are corrected, environment loading is hardened, and health checks use real process/port verification.

### 1.2 Slack Bot & Commander Architecture

**Location:** `slack-bot/`  
**Status:** Mature, extensible

| Component | File | Purpose | Status |
|-----------|------|---------|--------|
| Entry Point | `app.py` | Slack Bolt application, command routing | ✅ Live |
| Mission Manager | `mission_manager.py` | Mission lifecycle queries (active, completed, recent) | ✅ Live |
| Commander Bridge | `commander_bridge.py` | LLM integration layer | ✅ Live |
| Response Formatting | `commander_response_formatter.py` | Structured Slack message output | ✅ Live |
| Specialized Handlers | `commands/` (6 modules) | /mission-brief, /ask-specialist, etc. | ✅ Live |

**Assessment:** The Slack Bot has a mature command routing system and mission awareness. Can be reused via direct imports or HTTP calls.

### 1.3 Command Centre Backend (Partial)

**Location:** `core/command-centre/backend/api/`  
**Status:** Exploratory

| Module | Lines | Purpose | Completeness |
|--------|-------|---------|--------------|
| `agents.js` | 350 | Agent lifecycle (spawn, stop, health) | ⚠️ Skeleton |
| `missions.js` | 200 | Mission CRUD (create, list, update) | ⚠️ Skeleton |
| `health.js` | 280 | System health aggregation | ⚠️ Skeleton |
| `coordination.js` | 220 | Service orchestration | ⚠️ Skeleton |

**Assessment:** These are design sketches (JavaScript, Node.js style) not yet integrated with actual services. Can inform design; recommend Python/Flask instead for tighter integration with Slack Bot and existing CLI.

### 1.4 Service Lifecycle Management

**Existing State:**
- OpenClaw: Started via Docker (verified working, port 18789)
- Ollama: Started via Docker (verified working, port 11434)
- Number One (Slack Bot): Started via `start-slack-bot.sh` (working)
- Mission Registry: Backend-only (via Supabase, no web UI)
- Supabase: Docker container (running, port 5432 internal)

**Assessment:** All target services have clear startup mechanisms. CLI scripts handle them; need API wrapper to expose via HTTP.

---

## 2. Reuse Opportunities

### 2.1 Shell Script Reuse

**Direct reuse:**
- `start-slack-bot.sh` — Call this directly from Python subprocess
- `start-commander.sh` — Call this directly from Python subprocess
- `status.command` — Parse its output or call directly and parse stdout
- `services.conf` — Source this in Python to read port/path config

**Benefit:** Zero duplication; use existing hardened scripts as-is

**Example:**
```python
import subprocess
import os

# Load services.conf
services_conf = {}
with open('USS-TJR-Control/config/services.conf', 'r') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            services_conf[k.strip()] = v.strip()

# Start Slack Bot
result = subprocess.run(
    ['bash', 'USS-TJR-Control/scripts/start-slack-bot.sh'],
    env={**os.environ, **services_conf}
)
```

### 2.2 Mission Manager Reuse

**Direct import:**
```python
import sys
sys.path.insert(0, 'slack-bot/')
from mission_manager import get_recent_missions, get_active_missions, get_completed_missions

# Use in API endpoint
@app.get('/api/missions/active')
def list_active_missions():
    return {'missions': get_active_missions()}
```

**Benefit:** No reimplementation of mission tracking; reuse existing logic

### 2.3 Commander Bridge Reuse

**Direct import:**
```python
from commander_bridge import handle_slack_message

# In API endpoint, delegate LLM processing
response = handle_slack_message(user_prompt, context={})
```

**Benefit:** Leverage existing LLM integration; don't rewrite

### 2.4 Status Command Integration

**Parser for existing status.command:**
```python
def get_system_status():
    """Parse USS-TJR-Control/status.command output."""
    result = subprocess.run(
        ['bash', 'USS-TJR-Control/status.command'],
        capture_output=True, text=True
    )
    # Parse ✅/⚠️/❌ symbols and service names
    return parse_status_output(result.stdout)
```

**Benefit:** Real-time system health without reimplementing checks

---

## 3. Architecture Design: Control Engine MVP

### 3.1 Overview

**Name:** Control Engine  
**Framework:** Flask (lightweight, works in tmux pane)  
**Port:** 8888 (configurable, non-conflicting)  
**Entry Point:** New file `core/command-centre/control_engine.py`  
**Startup:** Added to `USS-TJR-Control/scripts/start-control-engine.sh`

### 3.2 API Endpoints (Phase 1: MVP)

#### Service Lifecycle

```
POST   /api/services/start/<service>        Start service (slack-bot, commander, ollama, etc.)
POST   /api/services/stop/<service>         Stop service
POST   /api/services/restart/<service>      Restart service
GET    /api/services/status                 Get all service statuses
GET    /api/services/status/<service>       Get single service status
GET    /api/services/logs/<service>         Tail service logs (last 50 lines)
```

#### Mission Management (Reuse mission_manager.py)

```
GET    /api/missions/active                 List active missions
GET    /api/missions/completed              List completed missions
GET    /api/missions/recent?limit=10        List recent missions
GET    /api/missions/<mission_id>           Get mission details
```

#### System Health (Parse status.command)

```
GET    /api/health                          Overall system status
GET    /api/health/detailed                 Detailed per-service health
```

#### Dashboard Integration

```
GET    /api/dashboard/summary               Quick overview for Control Deck display
```

### 3.3 Minimal Implementation

**Estimated Lines of Code:**

| Component | Lines | Notes |
|-----------|-------|-------|
| Flask app setup + error handling | 100 | Config, logging, CORS |
| Service lifecycle endpoints | 150 | start/stop/restart/status |
| Mission management endpoints | 80 | Reuse mission_manager.py |
| Health aggregation | 100 | Parse status.command output |
| Logging + utilities | 50 | Helper functions |
| **Total** | **~480** | Lean, focused MVP |

**Key Design Principle:** Wrap existing CLI; don't reimplement.

### 3.4 Security & Constraints

**No authentication (Phase 1):**
- Control Engine runs on localhost:8888 (internal network only)
- Dashboard and Control Engine in same Docker network
- Future phases can add token-based auth

**No database (MVP):**
- State sourced from:
  - Service process status (via `pgrep`, `lsof`)
  - Logs on disk (USS-TJR-Control/logs/)
  - Mission files (slack-bot/missions/)
  - Supabase queries via existing integrations

**No new dependencies (preferred):**
- Flask is already in Slack Bot venv
- Reuse subprocess for script calls
- Parse text output from existing tools

---

## 4. Integration Points

### 4.1 Control Deck Dashboard (Dashy v1.1)

**Current State:** Static links + informational cards  
**Future State (with Control Engine):**
- Service Status cards fetch from `/api/health`
- Recent Missions cards fetch from `/api/missions/recent`
- Start/stop buttons call `/api/services/start/<name>`

**Effort:** ~100 lines JavaScript/HTML in command-centre frontend

### 4.2 USS-TJR-Control Startup Integration

**Add Control Engine to startup sequence:**

```bash
# In start.command, after Slack Bot and Commander start:
echo "Starting Control Engine on localhost:8888..."
bash scripts/start-control-engine.sh
```

**Control Engine runs in same tmux session as other services.**

### 4.3 Slack Bot Integration (Optional, Phase 2)

**Add Slack commands:**
- `/control-status` — Show system health via API
- `/control-start <service>` — Start service via API
- `/control-logs <service>` — Show service logs

**Enables:** Voice-driven service management via Slack

---

## 5. Risk Assessment

### 5.1 Low Risk

| Risk | Mitigation |
|------|-----------|
| Script execution failures | Reuse hardened `start-*.sh` scripts; wrap error handling |
| Port conflicts | Use port 8888 (not in current use); configurable in code |
| Logging I/O overhead | Read log files only on demand; tail last N lines |
| Mission file corruption | Read-only access; never modify mission files from API |

### 5.2 Medium Risk

| Risk | Mitigation |
|------|-----------|
| Supabase connection failures | Handle gracefully; return "backend unavailable" message |
| Concurrent service starts | Lock file (`/tmp/control-engine.lock`) to prevent double-start |
| Status command hanging | Timeout subprocess calls (5 seconds) |

### 5.3 Mitigation Strategy

- **Phase 1:** Stateless (read-only for missions/status)
- **Phase 2:** Add service restart logic with safety checks
- **Phase 3:** Add monitoring and alerting

---

## 6. Risks by Service

### OpenClaw (Low Risk)
- Docker container; start/stop via `docker-compose`
- Already working; Control Engine just wraps existing commands
- **Mitigation:** Verify Docker is running before attempting start

### Ollama (Low Risk)
- Docker container; `docker ps` shows status
- No state to corrupt
- **Mitigation:** Check `lsof -i :11434` before declaring operational

### Number One/Slack Bot (Low-Medium Risk)
- Python process; `start-slack-bot.sh` is hardened
- Creates log files; Control Engine reads them (non-destructive)
- **Mitigation:** Check .venv and .env exist before attempting start

### Mission Registry (Medium Risk)
- Backend-only (no web UI)
- No direct Control Engine interaction (queried via existing mission_manager.py)
- **Mitigation:** Use existing mission queries; don't write to mission files

### Commander (Low Risk)
- Python process; same startup pattern as Slack Bot
- Optional service (bot degrades gracefully without it)
- **Mitigation:** Make startup optional in API (return 202 "accepted" even if already running)

---

## 7. Implementation Plan

### Phase 1: MVP (Days 1-3)
**Goal:** Wrap CLI, expose service start/stop/status over HTTP

**Deliverables:**
1. `core/command-centre/control_engine.py` (Flask app, ~480 lines)
2. `USS-TJR-Control/scripts/start-control-engine.sh` (startup wrapper)
3. Integration with `services.conf` and `status.command`
4. Documentation: API endpoint reference, usage examples

**Acceptance:**
- Flask app starts on localhost:8888
- `/api/services/status` returns accurate service states
- `/api/services/start/slack-bot` starts Slack Bot via existing script
- Logs available at `/api/services/logs/slack-bot`

### Phase 2: Dashboard Integration (Days 4-5)
**Goal:** Connect Control Deck dashboard to Control Engine API

**Deliverables:**
1. JavaScript API client in `command-centre/frontend/`
2. Update Service Status cards to fetch from `/api/health`
3. Add start/stop buttons (if desired)
4. Update Recent Missions cards to fetch from `/api/missions/recent`

**Acceptance:**
- Control Deck loads service status live from API
- Mission cards update without page reload

### Phase 3: Monitoring & Alerts (Future)
**Goal:** Add health polling, service restart on failure

**Deliverables:**
1. Background health polling (every 30 seconds)
2. Automatic restart logic for failed services
3. Alert notifications via Slack

---

## 8. Files to Create/Modify

### New Files
- `core/command-centre/control_engine.py` — Main Flask API
- `USS-TJR-Control/scripts/start-control-engine.sh` — Startup wrapper
- `core/command-centre/CONTROL-ENGINE-API-REFERENCE.md` — API docs

### Modified Files
- `USS-TJR-Control/start.command` — Add Control Engine to startup
- `core/command-centre/dashy-config.yml` — Link Service Status to API (Phase 2)
- `core/command-centre/frontend/api-client.js` — Add Control Engine client (Phase 2)

### No Changes Needed
- `USS-TJR-Control/config/services.conf` — Can be reused as-is
- `USS-TJR-Control/scripts/start-*.sh` — Call directly from Python
- `slack-bot/mission_manager.py` — Import directly
- `USS-TJR-Control/status.command` — Parse output

---

## 9. Design Principles

1. **Wrap, don't reimplement**
   - Use existing CLI scripts as subprocess calls
   - Parse `status.command` output instead of reimplementing checks
   - Import `mission_manager.py` directly into Python

2. **Local-first, minimal dependencies**
   - Flask only; no additional libraries
   - Read from disk (logs, missions) when possible
   - No new databases or authentication (Phase 1)

3. **Non-destructive**
   - API is read-only for missions and logs
   - Service start/stop go through existing hardened scripts
   - No direct file modifications

4. **Docker-compatible**
   - Control Engine runs in same tmux session as other services
   - No separate container needed (Phase 1)
   - Configured via `services.conf` (which is already in Docker mount)

---

## 10. Success Criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Existing CLI scripts remain unchanged | ✅ | Wrapping, not modifying |
| Control Engine MVP takes <500 lines | ✅ | Estimated 480 lines |
| Phase 1 takes <3 days | ✅ | Feasible scope |
| No new databases required | ✅ | State from existing sources |
| No authentication in Phase 1 | ✅ | Localhost-only |
| All target services supported | ✅ | OpenClaw, Ollama, Number One, Mission Registry |
| Reuses mission_manager.py | ✅ | Direct import |
| Reuses status.command | ✅ | Parse output |
| Reuses hardened start-*.sh scripts | ✅ | Subprocess calls |

---

## 11. Recommendation

### **PROCEED with Control Engine MVP**

**Rationale:**
1. **Strong foundation:** Existing CLI (MSN-0013) is production-ready and hardened
2. **Minimal rewrite:** Can wrap existing components without reimplementation
3. **Low risk:** Stateless Phase 1; read-only for missions and logs
4. **Quick delivery:** 2-3 days to MVP; adds immediate value to Control Deck
5. **Clear path forward:** Phase 2 connects dashboard; Phase 3 adds monitoring
6. **No infrastructure expansion:** Runs in existing tmux, no new containers

**Next Steps:**
1. Create `control_engine.py` skeleton (Flask app + 3-4 endpoint groups)
2. Implement service lifecycle endpoints (wrap start-*.sh)
3. Implement health aggregation (parse status.command)
4. Test locally with Control Deck startup
5. Document API endpoints
6. Plan Phase 2 dashboard integration

**Timeline:**
- **Week of June 10:** Phase 1 MVP (2-3 days work)
- **Week of June 17:** Phase 2 dashboard integration (1-2 days work)
- **Week of June 24+:** Phase 3 monitoring & alerts (future)

---

## Appendix A: Service Target Matrix

| Service | Startup Script | Stop Method | Status Check | Logs |
|---------|---|---|---|---|
| Slack Bot | `start-slack-bot.sh` | `pgrep` kill | `pgrep -f app.py` | `logs/slack-bot.log` |
| Commander | `start-commander.sh` | `pgrep` kill | `pgrep -f commander.py` | `logs/commander.log` |
| OpenClaw | Docker (external) | `docker stop` | `docker ps` | `docker logs` |
| Ollama | Docker (external) | `docker stop` | `lsof -i :11434` | Docker logs |
| Supabase | Docker (external) | `docker stop` | `curl` to URL | Docker logs |
| Paperclip | `start-paperclip.sh` (optional) | `pgrep` kill | `lsof -i :3100` | `logs/paperclip.log` |

---

## Appendix B: Reference Implementation Outline

```python
# core/command-centre/control_engine.py

from flask import Flask, jsonify, request
import subprocess
import os
import sys
from pathlib import Path

app = Flask(__name__)

# Load services.conf
def load_services_config():
    config = {}
    with open('USS-TJR-Control/config/services.conf') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.strip().split('=', 1)
                config[k.strip()] = v.strip()
    return config

# Import mission manager
sys.path.insert(0, 'slack-bot/')
from mission_manager import get_recent_missions, get_active_missions

SERVICES_CONFIG = load_services_config()

@app.get('/api/services/status')
def get_service_status():
    """Get status of all services."""
    # Call USS-TJR-Control/status.command, parse output
    result = subprocess.run(['bash', 'USS-TJR-Control/status.command'], 
                          capture_output=True, text=True, timeout=5)
    return {'status': parse_status_output(result.stdout)}

@app.post('/api/services/start/<service>')
def start_service(service):
    """Start a service."""
    script = f'USS-TJR-Control/scripts/start-{service}.sh'
    if not Path(script).exists():
        return {'error': f'Service {service} not found'}, 404
    
    # Run in background (don't wait for completion)
    subprocess.Popen(['bash', script])
    return {'message': f'Starting {service}...'}, 202

@app.get('/api/missions/active')
def list_active_missions():
    """List active missions."""
    return {'missions': get_active_missions()}

@app.get('/api/missions/recent')
def list_recent_missions():
    """List recent missions."""
    limit = request.args.get('limit', 10, type=int)
    return {'missions': get_recent_missions(limit)}

@app.get('/api/health')
def system_health():
    """Overall system health."""
    status = subprocess.run(['bash', 'USS-TJR-Control/status.command'],
                          capture_output=True, text=True, timeout=5)
    return parse_status_output(status.stdout)

def parse_status_output(output):
    """Parse status.command output (✅/⚠️/❌ format)."""
    # Implementation: parse the status output format
    pass

if __name__ == '__main__':
    app.run(host='localhost', port=8888, debug=False)
```

---

**Assessment Completed:** June 8, 2026  
**Next Meeting:** Implementation kickoff (Phase 1 planning)

