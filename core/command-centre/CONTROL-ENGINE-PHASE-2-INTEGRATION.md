# Control Engine - Phase 2 Integration Guide

**Phase:** 2 - Dashboard Integration  
**Mission:** M-20260609-000000  
**Effort:** 1-2 days  
**Status:** Ready for Implementation

---

## Overview

Phase 2 integrates the Control Engine API (Phase 1) with the Control Deck dashboard (Dashy v1.1). This enables:

1. **Live Service Status** — Service Status cards fetch from `/api/health`
2. **Live Mission Display** — Recent Missions cards fetch from `/api/missions/recent`
3. **Service Controls** — Start/stop buttons for service lifecycle
4. **Real-Time Updates** — 30-second refresh interval for health metrics

**No backend changes required** — Phase 1 Control Engine API is complete and stable.

---

## Phase 2 Deliverables

### 1. control-engine-client.js (JavaScript API Client)
**Location:** `core/command-centre/frontend/control-engine-client.js`  
**Lines:** 200+  
**Purpose:** Lightweight fetch wrapper with error handling and timeout

**Features:**
- Constructor: `new ControlEngineClient('http://localhost:8888')`
- 11 methods covering all Control Engine endpoints
- Timeout handling (default 5 seconds)
- Error handling with structured responses
- Works in browser and Node.js

**Methods:**
```javascript
// Health & Status
await client.getHealth()
await client.getServicesStatus()
await client.getServiceStatus(service)

// Service Control
await client.startService(service)
await client.stopService(service)
await client.restartService(service)
await client.getServiceLogs(service, lines)

// Missions
await client.getMissionsActive()
await client.getMissionsRecent(limit)
await client.getMissionsThisWeek()

// Dashboard
await client.getDashboardSummary()
```

### 2. Updated dashy-config.yml
**Changes:** Add API binding to Service Status and Recent Missions sections

**Before (Static):**
```yaml
- title: Service Status
  icon: fas fa-heartbeat
  items:
    - title: Control Deck
      description: "✅ Operational"
      url: "#"
```

**After (Dynamic):**
```yaml
- title: Service Status
  icon: fas fa-heartbeat
  items:
    - title: Control Deck
      description: "Auto-update from /api/health"
      url: "http://localhost:8888/api/health"
      customData: { apiBinding: 'status', field: 'status' }
```

**Implementation Strategy:**
- For Dashy v4 compatibility, use `statusCheckUrl` (if available) or
- Use custom dashboard HTML/JavaScript to fetch API data

### 3. Service Status Live Cards (JavaScript)
**Purpose:** Update Service Status cards with live data every 30 seconds

**Pseudocode:**
```javascript
const client = new ControlEngineClient('http://localhost:8888');

async function updateServiceStatus() {
  try {
    const health = await client.getHealth();
    
    // Update each service card
    health.services.forEach(svc => {
      const card = document.querySelector(`[data-service="${svc.name}"]`);
      if (card) {
        const statusEmoji = svc.status === 'operational' ? '✅' : '⚠️';
        card.querySelector('.description').textContent = statusEmoji + ' ' + svc.status;
      }
    });
  } catch (err) {
    console.error('Failed to update service status:', err);
  }
}

// Update immediately and every 30 seconds
updateServiceStatus();
setInterval(updateServiceStatus, 30000);
```

### 4. Recent Missions Live Cards (JavaScript)
**Purpose:** Update Recent Missions with live data every 60 seconds

**Pseudocode:**
```javascript
async function updateRecentMissions() {
  try {
    const response = await client.getMissionsRecent(3);
    const missions = response.missions;
    
    // Update mission cards
    const missionCards = document.querySelectorAll('[data-section="recent-missions"] .card');
    missions.forEach((mission, index) => {
      if (missionCards[index]) {
        missionCards[index].querySelector('h3').textContent = mission.mission_id;
        missionCards[index].querySelector('p').textContent = mission.title;
      }
    });
  } catch (err) {
    console.error('Failed to update missions:', err);
  }
}

// Update immediately and every 60 seconds
updateRecentMissions();
setInterval(updateRecentMissions, 60000);
```

### 5. Service Control Buttons (JavaScript)
**Purpose:** Add start/stop buttons to Service Status cards

**HTML (in dashboard):**
```html
<div class="service-card" data-service="slack-bot">
  <h3>Slack Bot</h3>
  <p id="slack-bot-status">✅ Operational</p>
  <button class="start-btn" onclick="startService('slack-bot')">Start</button>
  <button class="stop-btn" onclick="stopService('slack-bot')">Stop</button>
</div>
```

**JavaScript:**
```javascript
async function startService(service) {
  try {
    const result = await client.startService(service);
    alert(`${service} starting...`);
    // Refresh status after 2 seconds
    setTimeout(updateServiceStatus, 2000);
  } catch (err) {
    alert(`Error starting ${service}: ${err.message}`);
  }
}

async function stopService(service) {
  if (!confirm(`Stop ${service}?`)) return;
  try {
    const result = await client.stopService(service);
    alert(`${service} stopped`);
    updateServiceStatus();
  } catch (err) {
    alert(`Error stopping ${service}: ${err.message}`);
  }
}
```

---

## Implementation Steps

### Step 1: Deploy control-engine-client.js
1. Copy `control-engine-client.js` to frontend directory (already created)
2. Load in dashboard HTML:
   ```html
   <script src="/frontend/control-engine-client.js"></script>
   ```

### Step 2: Update dashy-config.yml
1. Update Service Status cards with API endpoint references
2. Update Recent Missions cards with API bindings
3. Verify YAML syntax is valid

### Step 3: Add Dashboard JavaScript
1. Create `core/command-centre/frontend/dashboard-integration.js`
2. Implement `updateServiceStatus()` function
3. Implement `updateRecentMissions()` function
4. Implement `startService()` and `stopService()` functions
5. Set up `setInterval()` timers for auto-refresh

### Step 4: Testing
1. Start Control Engine: `python3 control_engine.py`
2. Open Control Deck dashboard: `http://localhost:8081`
3. Verify Service Status cards update
4. Verify Recent Missions cards update
5. Test start/stop buttons
6. Check browser console for errors

### Step 5: Deployment
1. Commit all Phase 2 changes to git
2. Test full startup sequence (Control Engine + dashboard)
3. Document any issues in CONTROL-DECK-OPERATIONS.md
4. Plan Phase 3 (monitoring & alerts)

---

## File Locations

### Phase 2 Files to Create
- `core/command-centre/frontend/dashboard-integration.js` — Main dashboard update logic

### Phase 2 Files to Modify
- `core/command-centre/dashy-config.yml` — Add API bindings to Service Status/Missions
- `core/command-centre/CONTROL-DECK-OPERATIONS.md` — Add Phase 2 integration notes

### Phase 2 Files Already Created (Phase 1)
- `core/command-centre/frontend/control-engine-client.js` — API client (✅ done)
- `core/command-centre/control_engine.py` — Control Engine API (✅ done)

---

## API Integration Points

### Service Status Cards
**Current:** Static labels (✅ Operational, ⏸ On Demand, ⏳ Pending)  
**After Phase 2:** Live from `/api/health` (updated every 30 seconds)

**Update Process:**
1. Client calls `client.getHealth()`
2. Response includes services array with status
3. JavaScript updates card descriptions
4. Visual indicator changes color/emoji based on status

### Recent Missions Cards
**Current:** Static entries (M-20260609-000000, MSN-0040A-WP2, MSN-0035)  
**After Phase 2:** Live from `/api/missions/recent` (updated every 60 seconds)

**Update Process:**
1. Client calls `client.getMissionsRecent(3)`
2. Response includes recent missions array
3. JavaScript updates mission titles
4. New/completed missions appear automatically

### Service Control
**Current:** No controls (informational only)  
**After Phase 2:** Start/stop buttons available (optional feature)

**User Flow:**
1. User clicks "Start Slack Bot" button
2. Dashboard calls `client.startService('slack-bot')`
3. Control Engine runs `start-slack-bot.sh` in background
4. Dashboard refreshes status after 2 seconds
5. Card shows "✅ Operational" once service is ready

---

## Refresh Intervals

### Service Status
- **Interval:** 30 seconds
- **Endpoint:** `/api/health`
- **Why:** Health changes frequently; 30s is responsive without overloading
- **Fallback:** If API unavailable, card shows "⚠️ API Unavailable"

### Recent Missions
- **Interval:** 60 seconds
- **Endpoint:** `/api/missions/recent?limit=3`
- **Why:** Missions change less frequently; less urgent than health
- **Fallback:** If API unavailable, show last known value with timestamp

### Service Logs (On-Demand)
- **Trigger:** User clicks "View Logs" button
- **Endpoint:** `/api/services/logs/<service>?lines=50`
- **Display:** Modal popup with last 50 lines
- **Refresh:** User clicks refresh button (manual, not auto)

---

## Error Handling

### Network Errors
```javascript
try {
  const health = await client.getHealth();
  // Update UI
} catch (err) {
  console.error('API error:', err);
  card.style.opacity = '0.5';
  card.classList.add('api-unavailable');
  card.title = 'Control Engine API unavailable';
}
```

### Timeout Errors
```javascript
// Client automatically times out after 5 seconds
// Falls back to last known value
const lastHealth = sessionStorage.getItem('lastHealth');
if (!health && lastHealth) {
  health = JSON.parse(lastHealth);
}
```

### Invalid Response
```javascript
if (health && health.status) {
  // Valid response
} else {
  // Invalid response - show error state
  card.classList.add('error');
}
```

---

## Styling Considerations

### Service Status Card States
```css
/* Operational */
.service-card.operational {
  border-left: 4px solid #4CAF50; /* Green */
}

/* Degraded */
.service-card.degraded {
  border-left: 4px solid #FFC107; /* Yellow */
}

/* Offline */
.service-card.offline {
  border-left: 4px solid #F44336; /* Red */
}

/* API Unavailable */
.service-card.api-unavailable {
  opacity: 0.5;
  background-color: #f5f5f5;
}
```

### Loading States
```css
/* During API call */
.service-card.loading {
  opacity: 0.7;
  pointer-events: none;
}

.service-card.loading::after {
  content: '⟳';
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
```

---

## Testing Checklist

### Unit Tests (JavaScript)
- [ ] `ControlEngineClient` constructor initializes correctly
- [ ] `getHealth()` returns valid health object
- [ ] `startService()` makes POST request with correct endpoint
- [ ] Timeout triggers after 5 seconds
- [ ] Error responses are properly caught

### Integration Tests (Dashboard)
- [ ] Service Status cards update every 30 seconds
- [ ] Recent Missions cards update every 60 seconds
- [ ] Start button triggers service startup
- [ ] Stop button triggers service shutdown
- [ ] Error states display correctly
- [ ] Refresh works when API unavailable then becomes available

### End-to-End Tests
- [ ] Control Engine starts successfully
- [ ] Control Deck loads without console errors
- [ ] All cards visible and styled correctly
- [ ] Service Status shows correct state
- [ ] Recent Missions show actual missions
- [ ] Start/stop buttons work (if enabled)
- [ ] Auto-refresh works for 5+ minutes

---

## Phase 2 Effort Breakdown

| Task | Effort | Dependencies |
|------|--------|--------------|
| control-engine-client.js | 1 hour | None (Phase 1 API complete) |
| dashboard-integration.js | 2 hours | control-engine-client.js |
| Update dashy-config.yml | 30 min | Phase 1 complete |
| Service Status update logic | 1 hour | dashboard-integration.js |
| Recent Missions update logic | 1 hour | dashboard-integration.js |
| Service control buttons (optional) | 1 hour | dashboard-integration.js |
| Testing & debugging | 2 hours | All above |
| **Total** | **8.5 hours** | Start after Phase 1 ✅ |

**Estimated Timeline:** 1-2 days (depending on testing/debugging needed)

---

## Phase 3 Preview

Once Phase 2 is complete, Phase 3 can begin:

1. **Background Health Polling** — Control Engine polls service health every 30 seconds
2. **Automatic Service Restart** — Services auto-restart on failure
3. **Slack Alerts** — `/control-status` command in Slack
4. **Metrics Collection** — CPU, memory, uptime per service

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| control-engine-client.js created | ✅ Done (Phase 1) |
| All 11 API client methods working | ✅ Done (Phase 1) |
| dashy-config.yml updated with API bindings | ⏳ Phase 2 |
| Service Status cards fetch live health | ⏳ Phase 2 |
| Recent Missions cards fetch live data | ⏳ Phase 2 |
| 30-second refresh interval working | ⏳ Phase 2 |
| Start/stop buttons operational (optional) | ⏳ Phase 2 |
| Error states handled gracefully | ⏳ Phase 2 |
| All tests passing | ⏳ Phase 2 |
| Phase 2 deployment complete | ⏳ Phase 2 |

---

## Resources

- Control Engine API Reference: `CONTROL-ENGINE-API-REFERENCE.md`
- Control Engine Code: `control_engine.py`
- Control Engine Client: `frontend/control-engine-client.js` ✅
- Dashy Documentation: https://dashy.to/docs/
- Phase 1 Complete: `CONTROL-ENGINE-PHASE-1-COMPLETE.md` ✅

---

**Phase 2 Status:** Ready for Implementation  
**Start Date:** After Phase 1 completion ✅  
**Estimated Completion:** 1-2 days  
**Mission:** M-20260609-000000
