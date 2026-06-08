# Control Engine - Phases 2 & 3 Deployment Checklist

**Mission:** M-20260609-000000  
**Status:** ✅ IMPLEMENTATION COMPLETE - READY FOR TESTING  
**Date:** June 8, 2026

---

## Phase 2 Deployment (Dashboard Integration)

### Pre-Deployment Verification

- [x] **control-engine-client.js** created and syntax-validated
  - Location: `core/command-centre/frontend/control-engine-client.js`
  - Lines: 193
  - Status: ✅ Compiles without errors
  - Methods: 11 (health, services, missions, logs, dashboard)

- [x] **dashboard-integration.js** created and syntax-validated
  - Location: `core/command-centre/frontend/dashboard-integration.js`
  - Lines: 520+
  - Status: ✅ Compiles without errors
  - Features: Auto-refresh, service controls, error handling, offline mode

- [x] **control_engine.py** (Phase 1) verified functional
  - Location: `core/command-centre/control_engine.py`
  - Lines: 760
  - Status: ✅ Compiles without errors
  - Endpoints: 15 REST endpoints

### Phase 2 Deployment Steps

#### Step 1: Verify Control Engine Running
```bash
# Start Control Engine on localhost:8888
cd ~/Documents/GitHub/USSTJROS/core/command-centre
python3 control_engine.py

# In another terminal, verify health endpoint
curl http://localhost:8888/api/health
# Expected: { "status": "operational", "services": {...} }
```

- [ ] Control Engine starts without errors
- [ ] `/api/health` endpoint responds
- [ ] Service status data is valid
- [ ] Mission data is available

#### Step 2: Load JavaScript Libraries into Dashboard
```bash
# Ensure libraries are in frontend directory
ls -la core/command-centre/frontend/control-engine-client.js
ls -la core/command-centre/frontend/dashboard-integration.js
```

- [ ] Both JavaScript files exist in frontend directory
- [ ] Files are readable (644 permissions minimum)

#### Step 3: Update Dashboard HTML
In Control Deck HTML (index.html or dashboard template):

```html
<!-- Add before closing </body> tag -->
<script src="/frontend/control-engine-client.js"></script>
<script src="/frontend/dashboard-integration.js"></script>

<!-- Optional: auto-initialization -->
<div data-dashboard-auto-init data-control-engine-url="http://localhost:8888"></div>
```

- [ ] Script tags added to dashboard HTML
- [ ] Correct paths to frontend directory
- [ ] Auto-init div present (or manual init in dashboard code)

#### Step 4: Verify HTML Structure
Ensure Service Status cards have required data attributes:

```html
<!-- Service Status Cards -->
<div data-section="service-status">
  <div data-service="slack-bot" class="service-card">
    <h3>Slack Bot</h3>
    <p data-field="description" class="description">Loading...</p>
    <button onclick="dashboard.startService('slack-bot', this)">Start</button>
    <button onclick="dashboard.stopService('slack-bot', this)">Stop</button>
  </div>
  <!-- More service cards... -->
</div>

<!-- Recent Missions -->
<div data-section="recent-missions">
  <div data-card="mission">
    <h3 data-field="title">Mission ID</h3>
    <p data-field="description">Title</p>
    <span data-field="status" class="status-badge">Status</span>
  </div>
  <!-- More mission cards... -->
</div>
```

- [ ] Service Status cards have `data-service` attributes
- [ ] Recent Missions section has `data-section="recent-missions"`
- [ ] Mission cards have required `data-field` attributes
- [ ] Error container exists (optional): `<div data-error-container></div>`

#### Step 5: Browser Testing
1. Open Control Deck: `http://localhost:8081`
2. Open browser console (F12 → Console tab)
3. Verify no JavaScript errors

**Checklist:**
- [ ] Dashboard loads without JavaScript errors
- [ ] Console shows "Dashboard Integration initialized successfully"
- [ ] Service Status cards visible
- [ ] Recent Missions cards visible

#### Step 6: Live Update Testing
1. Wait 30 seconds
2. Verify Service Status cards update (emoji/color changes)
3. Wait 60 seconds
4. Verify Recent Missions update (different data)

**Checklist:**
- [ ] Service Status updates every 30 seconds
- [ ] Recent Missions updates every 60 seconds
- [ ] Timestamps show correct update times
- [ ] No API errors in console

#### Step 7: Service Control Testing (if buttons enabled)
1. Click "Start" button on a stopped service
2. Verify button shows "Starting..." state
3. Wait 2 seconds
4. Verify service shows "✅ Operational"
5. Click "Stop" button
6. Confirm dialog appears
7. Verify service shows "❌ Offline"

**Checklist:**
- [ ] Start button works without errors
- [ ] Service status updates after start
- [ ] Stop button shows confirmation
- [ ] Service status updates after stop
- [ ] Success notification appears (toast)
- [ ] No API errors in console

#### Step 8: Error State Testing
1. Stop Control Engine (^C in terminal)
2. Wait 30 seconds
3. Verify Service Status cards show reduced opacity
4. Verify error message appears
5. Restart Control Engine
6. Wait 30 seconds
7. Verify cards return to normal opacity
8. Verify error message disappears

**Checklist:**
- [ ] Error state shows when API unavailable
- [ ] Cards show cached data with "(cached)" label
- [ ] Error notification appears
- [ ] Recovery works when API comes back
- [ ] Cached data prevents blank cards

### Phase 2 Completion Sign-Off
- [ ] All files created and validated
- [ ] Control Engine API working
- [ ] Dashboard loads without errors
- [ ] Live updates working (30s/60s)
- [ ] Service controls functional
- [ ] Error handling working
- [ ] Testing checklist passed

---

## Phase 3 Deployment (Monitoring & Auto-Restart)

### Pre-Deployment Verification

- [x] **control_engine_monitor.py** created and syntax-validated
  - Location: `core/command-centre/control_engine_monitor.py`
  - Lines: 450+
  - Status: ✅ Compiles without errors
  - Features: Health polling, auto-restart, Slack alerts, persistent state

### Phase 3 Deployment Steps

#### Step 1: Configure Environment
```bash
# Set Slack webhook (optional, for alerts)
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Or skip if you don't want Slack alerts
# Monitor will still work, just without alerts
```

- [ ] Slack webhook URL obtained (if alerts desired)
- [ ] Webhook URL set in environment
- [ ] Or proceed without alerts

#### Step 2: Verify Control Engine Still Running
```bash
# Ensure Control Engine is running on localhost:8888
curl http://localhost:8888/api/health
# Expected: { "status": "...", "services": {...} }
```

- [ ] Control Engine running on localhost:8888
- [ ] `/api/health` endpoint responding
- [ ] Service data valid

#### Step 3: Start Service Monitor
```bash
# In new terminal, start monitor process
cd ~/Documents/GitHub/USSTJROS/core/command-centre
python3 control_engine_monitor.py --poll-interval 30

# Or with Slack alerts:
python3 control_engine_monitor.py \
  --poll-interval 30 \
  --slack-webhook $SLACK_WEBHOOK_URL
```

- [ ] Monitor starts without errors
- [ ] Logs show "Starting monitoring loop"
- [ ] Health polling occurs every 30 seconds
- [ ] No Python errors

#### Step 4: Verify Monitor State File
```bash
# Monitor should create .monitor_state.json
ls -la core/command-centre/.monitor_state.json

# Check contents
cat core/command-centre/.monitor_state.json
# Expected: { "last_restart_time": {...}, "failure_count": {...} }
```

- [ ] `.monitor_state.json` file created
- [ ] File contains valid JSON
- [ ] Structure includes failure_count and last_restart_time

#### Step 5: Test Service Failure Detection
```bash
# In another terminal, stop a service manually
# Example: stop slack-bot service
cd ~/Documents/GitHub/USSTJROS/USS-TJR-Control
./scripts/stop-slack-bot.sh

# Monitor should detect offline status within 30 seconds
# Check logs for: "slack-bot: offline"
```

- [ ] Monitor detects service offline
- [ ] Logs show detection message
- [ ] Failure count increments in `.monitor_state.json`
- [ ] No errors in monitor logs

#### Step 6: Test Auto-Restart (After Failure Threshold)
```bash
# Wait for failure count to reach max_failures (default: 3)
# Monitor will wait 30 seconds, then auto-restart service
# Watch logs for: "Restarting service: slack-bot"

# After restart, verify service is operational
curl http://localhost:8888/api/health | grep slack-bot
# Expected: "status": "operational"
```

- [ ] Monitor initiates auto-restart after threshold reached
- [ ] Logs show restart message
- [ ] Service comes back online
- [ ] Failure count resets to 0
- [ ] Cooldown timer starts

#### Step 7: Test Cooldown (Restart Prevention)
```bash
# Stop the service again immediately
./USS-TJR-Control/scripts/stop-slack-bot.sh

# Monitor should NOT restart again (still in cooldown)
# Check logs for: "Still in cooldown period"

# Wait for cooldown to expire (default: 5 minutes)
# Then monitor will restart again
```

- [ ] Monitor respects cooldown period
- [ ] Logs show cooldown message
- [ ] No restart attempts during cooldown
- [ ] Restart resumes after cooldown expires

#### Step 8: Test Slack Alerts (if configured)
```bash
# Watch Slack channel for alerts:
# - "🔄 Service restarted: slack-bot" (orange)
# - "❌ Service offline: slack-bot" (red)
# - "⚠️ Monitor error: ..." (red, if errors occur)
```

- [ ] Slack alerts appear when service offline
- [ ] Restart alert appears when service restarted
- [ ] Error alerts appear if problems occur
- [ ] Color coding matches alert level

#### Step 9: Test Monitor Restart Persistence
```bash
# Stop and restart monitor process
# (Press Ctrl+C to stop)
# Then restart: python3 control_engine_monitor.py

# Monitor should load persisted state
# Check logs for: "Loaded persisted monitor state"
# Failure counts and restart times should be preserved
```

- [ ] Monitor loads saved state on startup
- [ ] Failure counts preserved across restart
- [ ] Last restart times preserved
- [ ] No loss of monitoring data

#### Step 10: Verify Non-Blocking Operation
```bash
# Control Engine should still respond while monitor runs
curl http://localhost:8888/api/health
# Should respond quickly even if monitor is running

# Dashboard should still update
# Open http://localhost:8081
# Verify Service Status and Missions cards still update
```

- [ ] Control Engine performance not impacted
- [ ] Dashboard updates still occur
- [ ] No blocking between monitor and API
- [ ] Both processes work independently

### Phase 3 Completion Sign-Off
- [ ] Monitor created and validated
- [ ] Monitor starts without errors
- [ ] Health polling working (every 30 seconds)
- [ ] Service failure detection working
- [ ] Auto-restart working (after threshold + cooldown)
- [ ] Slack alerts working (if configured)
- [ ] State persistence working
- [ ] Non-blocking operation verified
- [ ] Testing checklist passed

---

## Integrated System Testing

### Full Stack Test

#### Startup Sequence
```bash
# Terminal 1: Control Deck Dashboard
cd ~/Documents/GitHub/USSTJROS/core/command-centre
dashy  # or python3 -m http.server 8081

# Terminal 2: Control Engine API
cd ~/Documents/GitHub/USSTJROS/core/command-centre
python3 control_engine.py

# Terminal 3: Service Monitor (optional)
cd ~/Documents/GitHub/USSTJROS/core/command-centre
python3 control_engine_monitor.py --poll-interval 30
```

#### Integration Checklist
- [ ] All 3 processes start without errors
- [ ] Dashboard loads (http://localhost:8081)
- [ ] Service Status cards show live data
- [ ] Recent Missions cards show live data
- [ ] Service controls work (start/stop)
- [ ] Monitor detects service failures
- [ ] Monitor auto-restarts services
- [ ] No performance degradation

### Stress Testing

#### Monitor Stress Test (Optional)
```bash
# Run monitor with shorter poll interval for stress testing
python3 control_engine_monitor.py --poll-interval 5  # Poll every 5 seconds instead of 30

# Monitor should handle rapid polling without CPU spikes
# Watch system resources: `top` or `Activity Monitor`
```

- [ ] Monitor uses <5% CPU with 5-second polling
- [ ] Memory usage stable (no leaks)
- [ ] API responds normally under monitor load
- [ ] Dashboard updates not affected

### Cleanup

After testing, reset to production intervals:
```bash
# Default: 30-second polling
python3 control_engine_monitor.py --poll-interval 30
```

---

## Troubleshooting

### Dashboard Not Updating

**Problem:** Service Status cards don't update after 30 seconds  
**Solution:**
1. Check browser console for errors (F12 → Console)
2. Verify Control Engine is running: `curl http://localhost:8888/api/health`
3. Check network tab (F12 → Network) for failed API calls
4. Ensure Service Status cards have `data-service` attributes
5. Verify localhost:8888 is accessible from dashboard

### Auto-Restart Not Triggering

**Problem:** Service is offline but monitor doesn't restart it  
**Solution:**
1. Check monitor logs for "offline" detection message
2. Verify failure count hasn't hit max: `cat .monitor_state.json`
3. Check cooldown period: `cat .monitor_state.json` for `last_restart_time`
4. Verify service is in `SERVICE_RESTART_CONFIG` with `enabled: true`
5. Restart monitor to reset state: `python3 control_engine_monitor.py`

### Slack Alerts Not Sending

**Problem:** Monitor runs but no Slack alerts appear  
**Solution:**
1. Verify webhook URL is set: `echo $SLACK_WEBHOOK_URL`
2. Test webhook manually:
   ```bash
   curl -X POST $SLACK_WEBHOOK_URL \
     -H "Content-Type: application/json" \
     -d '{"text":"test"}'
   ```
3. Check monitor logs for "Slack alert failed" error
4. Verify firewall allows HTTPS to Slack

### Monitor High CPU Usage

**Problem:** Monitor process using >10% CPU  
**Solution:**
1. Increase poll interval: `python3 control_engine_monitor.py --poll-interval 60`
2. Check if API endpoint is slow: `time curl http://localhost:8888/api/health`
3. Monitor API logs for performance issues
4. Check system load: `uptime` or Activity Monitor

---

## File Summary

### Phase 2 Files
| File | Status | Tests |
|------|--------|-------|
| control-engine-client.js | ✅ Created | Syntax checked |
| dashboard-integration.js | ✅ Created | Syntax checked |
| control_engine.py (Phase 1) | ✅ Complete | API working |

### Phase 3 Files
| File | Status | Tests |
|------|--------|-------|
| control_engine_monitor.py | ✅ Created | Syntax checked |

### Documentation
| File | Status | Content |
|------|--------|---------|
| CONTROL-ENGINE-PHASES-2-3-IMPLEMENTATION.md | ✅ Created | Complete guide |
| PHASES-2-3-DEPLOYMENT-CHECKLIST.md | ✅ This file | Deployment steps |
| CONTROL-ENGINE-API-REFERENCE.md | ✅ Complete | API documentation |
| CONTROL-ENGINE-PHASE-2-INTEGRATION.md | ✅ Complete | Integration guide |

---

## Success Criteria

### Phase 2 Success
- [x] control-engine-client.js compiles without errors
- [x] dashboard-integration.js compiles without errors
- [ ] Dashboard loads without JavaScript errors
- [ ] Service Status cards update every 30 seconds
- [ ] Recent Missions cards update every 60 seconds
- [ ] Service controls work (start/stop)
- [ ] Error notifications appear
- [ ] Cached data displays when API unavailable
- [ ] All manual tests pass

### Phase 3 Success
- [x] control_engine_monitor.py compiles without errors
- [ ] Monitor starts without errors
- [ ] Health polling occurs every 30 seconds
- [ ] Service failure detected correctly
- [ ] Auto-restart triggered after threshold
- [ ] Cooldown prevents restart loops
- [ ] Slack alerts send correctly
- [ ] State persists across restarts
- [ ] No performance impact on API
- [ ] All manual tests pass

---

## Next Steps

1. **Deploy Phase 2** (Dashboard Integration)
   - Start Control Engine
   - Load dashboard-integration.js into Control Deck
   - Run manual testing checklist
   - Verify all features working

2. **Deploy Phase 3** (Monitoring & Auto-Restart)
   - Start Service Monitor alongside Control Engine
   - Run manual testing checklist
   - Test failure scenarios
   - Configure Slack alerts

3. **Phase 4** (Future Enhancement)
   - Service metrics collection
   - Uptime analytics
   - Performance dashboards
   - Advanced orchestration

---

**Implementation Status:** ✅ COMPLETE  
**Deployment Status:** Ready for Testing  
**Testing Status:** Manual checklist provided  
**Mission:** M-20260609-000000

---

**Generated:** June 8, 2026  
**Version:** 1.0 (Phases 2 & 3 Complete)
