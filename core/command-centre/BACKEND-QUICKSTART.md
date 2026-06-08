# STARFLEET COMMAND CENTRE Backend — Quick Start Guide

## 30-Second Setup

```bash
cd core/command-centre/backend
npm install
npm start
```

**Server will be available at**: `http://localhost:5000`

---

## Immediate Verification

### Health Check
```bash
curl http://localhost:5000/health
```
Should return: `{ "status": "operational", ... }`

### API Documentation
```bash
curl http://localhost:5000/api
```
Shows all available endpoints.

### Test All Endpoints
```bash
npm test
```
Should show: `31 passing`

---

## Quick API Tests (Copy & Paste)

### Mission Registry
```bash
curl http://localhost:5000/api/v1/missions/summary
curl http://localhost:5000/api/v1/missions/active
curl http://localhost:5000/api/v1/missions/blocked
curl http://localhost:5000/api/v1/missions/MSN-0032/detail
```

### Coordination Engine
```bash
curl http://localhost:5000/api/v1/coordination/brief
curl http://localhost:5000/api/v1/coordination/queue
curl http://localhost:5000/api/v1/coordination/escalations
```

### System Health
```bash
curl http://localhost:5000/api/v1/health/summary
curl http://localhost:5000/api/v1/health/services
curl http://localhost:5000/api/v1/health/alerts
```

### Agent Status
```bash
curl http://localhost:5000/api/v1/agents/status
curl http://localhost:5000/api/v1/agents/chief-engineer/workload
curl http://localhost:5000/api/v1/agents/chief-engineer/activity
```

---

## Development Mode

### Watch Mode (Auto-Restart on Changes)
```bash
npm run dev
```

### With Logging
```bash
DEBUG=true npm start
```

### Run Tests in Watch Mode
```bash
npm run test:watch
```

---

## Environment Configuration

### Create `.env` file (optional for defaults)
```bash
cp .env.example .env
```

### Customize Settings
```
NODE_ENV=development
PORT=5000
CORS_ORIGIN=http://localhost:8080,http://localhost:3000
LOG_LEVEL=debug
```

---

## Frontend Integration

### Use API Client in Your HTML/JS
```javascript
// Import the client
const { apiClient } = require('./frontend/api-client.js');

// Or use directly in browser (after bundling)
// const apiClient = window.apiClient;

// Make API calls
const summary = await apiClient.getMissionSummary();
const brief = await apiClient.getCoordinationBrief();
const health = await apiClient.getHealthSummary();
const agents = await apiClient.getAgentStatus();
```

---

## Common Commands

| Command | Purpose |
|---------|---------|
| `npm start` | Start server (port 5000) |
| `npm run dev` | Start with auto-reload |
| `npm test` | Run all tests (31 tests) |
| `npm run test:watch` | Run tests in watch mode |
| `npm run lint` | Lint code (if configured) |
| `npm run health-check` | Quick health endpoint test |

---

## Expected Responses

All API responses follow this structure:
```json
{
  "status": "success",
  "data": { /* actual data */ },
  "metadata": {
    "timestamp": "2026-06-08T...",
    "source": "cache",
    "message": "..."
  }
}
```

---

## Default Data

### Missions
- 12 total missions
- 1 P0 (MSN-0032)
- 3 P1 (MSN-0034, MSN-0035, etc)
- 5 P2
- 3 P3
- 1 blocked

### Coordination
- 8 work queue items
- 3 top priorities
- 1 HIGH escalation
- 0 blockers

### Health
- 7 services (all OPERATIONAL)
- 0 alerts
- 99.9%+ uptime

### Agents
- 5 specialists
- 3 ACTIVE, 2 IDLE
- 11 total missions assigned

---

## Troubleshooting

### Port Already in Use
```bash
# Kill process on port 5000
lsof -i :5000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Or use different port
PORT=5001 npm start
```

### CORS Issues
Edit `backend/app.js` line 23:
```javascript
origin: ['http://localhost:8080', 'http://your-domain.com']
```

### Tests Failing
```bash
# Clear and reinstall
rm -rf node_modules package-lock.json
npm install
npm test
```

### Can't Connect to Backend
1. Verify server is running: `curl http://localhost:5000/health`
2. Check firewall: `sudo ufw allow 5000/tcp`
3. Try different port: `PORT=5001 npm start`

---

## Next Steps

1. **Start the backend**: `npm start`
2. **Verify it works**: `curl http://localhost:5000/api`
3. **Run tests**: `npm test`
4. **Integrate with dashboard** (Day 2+)
5. **Connect to real APIs** (Phase 2)

---

## Documentation

- **Full API Specs**: `PHASE2-DAY1-COMPLETION.md`
- **Architecture Overview**: `PHASE2-KICKOFF.md`
- **Test Coverage**: `backend/tests/api.test.js`
- **Code Comments**: See individual files for implementation details

---

## Quick Checklist

- [ ] `npm install` completed
- [ ] `npm start` runs without errors
- [ ] `curl http://localhost:5000/health` returns operational
- [ ] `npm test` shows 31 passing tests
- [ ] API client imported successfully
- [ ] Ready to integrate with Dashy widgets

---

**Server Ready**: ✅  
**Tests Passing**: ✅ (31/31)  
**Documentation**: ✅  
**Ready for Day 2**: ✅

---

Questions? See `PHASE2-DAY1-COMPLETION.md` for detailed documentation.
