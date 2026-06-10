# Control Deck Launchpad - Startup Guide

**Mission:** M-20260609-000000  
**System:** Control Deck Launchpad (Dashy v4 Dashboard)  
**Status:** MVP v1 (Stable)  
**Last Updated:** June 8, 2026

---

## Quick Start (3 minutes)

### Step 1: Navigate to the Command Centre directory

```bash
cd core/command-centre
```

### Step 2: Start the Docker container

```bash
docker-compose up -d
```

**Expected output:**
```
Creating starfleet-command-centre ... done
```

### Step 3: Access the dashboard

Open your browser to:
```
http://localhost:8081
```

You should see **STARFLEET COMMAND BRIDGE** with 5 sections of cards.

### Step 4: Hard-refresh the browser

If you see the default Dashy dashboard instead:

- **macOS:** `Cmd+Shift+R`
- **Linux/Windows:** `Ctrl+Shift+R`
- **Alternative:** Open in private/incognito window

---

## What You Should See

The Control Deck Launchpad displays 5 operational sections:

### Section 1: Command Status
- Starship Endeavour (NCC-170230)
- Captain TJR (In Command)
- Status Operational (Stardate 2026.160)

### Section 2: Core Operations
- Mission Registry (localhost:5000) — Active missions
- Number One Slack Bot (localhost:3001) — Command interface
- Decision Log — Captured decisions

### Section 3: Runtime Services
- Ollama LLM (localhost:11434) — Local inference engine 🟢
- Supabase Database (localhost:5432) — Backend storage
- OpenClaw Sandbox (localhost:8000) — Code execution

### Section 4: Documentation
- Architecture Decisions (GitHub)
- API Reference (GitHub)
- Setup Guide

### Section 5: Development
- Main Repository (GitHub)
- Control Deck Foundation (GitHub)
- Control Deck Launchpad (GitHub)

---

## Accessing Services

### Internal Services (Localhost)

All services can be accessed via the dashboard cards:

| Service | Port | Type | Status |
|---------|------|------|--------|
| Mission Registry | 5000 | Always-on | Core API |
| Number One Bot | 3001 | On-demand | Start as needed |
| Supabase | 5432 | Always-on | Database backend |
| OpenClaw | 8000 | On-demand | Code sandbox |
| Ollama | 11434 | Always-on | LLM inference |

### Starting Services

Services can be started from the Control CLI:

```bash
# From the main repo directory
./control start all              # Start all services
./control start ollama          # Start specific service
./control status                # Check service status
```

### External Links (GitHub)

All GitHub links open in new tabs. They require:
- Internet connectivity
- GitHub account access (for private repos)

---

## Troubleshooting

### Dashboard shows default Dashy interface

**Cause:** Configuration file not loaded or cached version displayed

**Solution:**
1. Hard-refresh browser: `Cmd+Shift+R` (macOS) or `Ctrl+Shift+R` (Linux/Windows)
2. Clear browser cache completely
3. Try opening in private/incognito window
4. Check Docker logs: `docker logs starfleet-command-centre`

### Localhost service links return errors

**Cause:** Service not running on expected port

**Solution:**
1. Check service status: `./control status`
2. Start missing services: `./control start ollama` (example)
3. Verify port mapping in docker-compose.yml
4. Check Docker logs: `docker logs starfleet-command-centre`

### Icons not displaying

**Cause:** Font Awesome icons not loaded (rare, usually cache issue)

**Solution:**
1. Hard-refresh browser
2. Check browser console for errors (F12 → Console tab)
3. Verify internet connectivity for Font Awesome CDN

### "Connection refused" on localhost links

**Cause:** Service not running or wrong port

**Solution:**
1. Verify service is running: `docker ps`
2. Check service port in docker-compose: `cat docker-compose.yml`
3. Test port directly: `curl http://localhost:11434` (example)
4. Restart Docker: `docker-compose restart`

---

## Port Mapping

The dashboard container runs on port 8081 (mapped to container port 80).

All service links use localhost with service-specific ports:

```yaml
Dashboard:    http://localhost:8081
Mission API:  http://localhost:5000
Number One:   http://localhost:3001
Ollama:       http://localhost:11434
```

**Note:** If you change the dashboard port in docker-compose.yml, update your browser bookmarks.

---

## Configuration

The dashboard is configured in `dashy-config.yml`.

**Key settings:**
- `theme: nord` — Dark Nordic theme (blue/gray)
- `layout: grid` — 4-column grid layout
- `columns: 4` — Cards per row
- `itemSize: small` — Compact card size

To modify the dashboard:
1. Edit `dashy-config.yml`
2. Restart container: `docker-compose restart`
3. Hard-refresh browser

---

## Docker Operations

### View logs

```bash
docker logs starfleet-command-centre
docker logs -f starfleet-command-centre  # Follow logs (Ctrl+C to exit)
```

### Restart container

```bash
docker-compose restart
```

### Stop container

```bash
docker-compose down
```

### Rebuild container

```bash
docker-compose up -d --force-recreate
```

### Check container status

```bash
docker ps | grep starfleet
docker-compose ps
```

---

## Health Checks

The container includes a built-in health check:

```bash
docker inspect starfleet-command-centre | grep -A 5 Health
```

Expected status: `healthy` after ~40 seconds

Health check command:
```
curl -f http://localhost (inside container)
```

---

## Stopping and Starting

### Stop the dashboard

```bash
docker-compose down
```

**This stops the container but keeps the configuration.**

### Start the dashboard

```bash
docker-compose up -d
```

**The container will restart with the same configuration.**

### Reset to defaults

```bash
docker-compose down -v
docker-compose up -d
```

**Note:** The `-v` flag removes volumes (resets state)

---

## Performance Notes

- **CPU:** Minimal (idle ~1-2% on modern systems)
- **Memory:** ~100-150 MB at startup
- **Startup time:** ~30-40 seconds (health check time)
- **UI response:** <100ms (instant clicks/navigation)

---

## Next Steps

After startup verification:

1. **Verify all services** are running: `./control status`
2. **Test a service link** — Click Mission Registry (localhost:5000)
3. **Check Ollama health** — Label shows 🟢 when running
4. **Review logs** if any issues: `docker logs starfleet-command-centre`

---

## Support

For issues or questions:

1. Check troubleshooting section above
2. Review Docker logs: `docker logs starfleet-command-centre`
3. Check service status: `./control status`
4. Review configuration: `cat dashy-config.yml`

---

**Mission Status: OPERATIONAL** ✓

The Control Deck Launchpad is ready for use as your STARFLEET COMMAND visibility layer.

Ad Astra Per Aspera 🚀

