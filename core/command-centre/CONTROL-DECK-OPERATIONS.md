# Control Deck Launchpad - Operations Manual

**Mission:** M-20260609-000000  
**System:** STARFLEET COMMAND BRIDGE (Control Deck Launchpad)  
**Version:** v1.0 (MVP - Stable)  
**Classification:** USS TJR Operational Documentation  
**Last Updated:** June 8, 2026

---

## Executive Summary

The Control Deck Launchpad is a read-only visibility layer dashboard that displays real-time status of mission-critical services and operational infrastructure. Built on Dashy v4, it provides a unified command center interface for STARFLEET COMMAND operations.

**Primary Function:** Monitor service health and quickly access operational tools  
**Target Users:** Captain TJR, Executive Officers, Operations Team  
**Update Frequency:** Real-time (service-based)  
**Availability:** Always-on (depends on Docker availability)

---

## System Architecture

### Technology Stack
- **Framework:** Dashy v4 (self-hosted dashboard)
- **Containerization:** Docker & Docker Compose
- **Theme:** Nord (dark blue/gray professional UI)
- **Port:** 8081 (localhost)
- **Assets:** SVG logos, Font Awesome icons

### Design Principles
1. **Read-only visibility** — No operational controls (pure monitoring)
2. **Quick access** — Links to all operational systems in one place
3. **Service agnostic** — References existing services, doesn't duplicate them
4. **Low overhead** — Minimal CPU/memory footprint
5. **Easy to extend** — Simple YAML configuration

---

## Dashboard Overview

### Layout Structure
```
┌─────────────────────────────────────────────────┐
│         STARFLEET COMMAND BRIDGE                │
│    Starship Endeavour | NCC-170230             │
└─────────────────────────────────────────────────┘

┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│  COMMAND STATUS  │  CORE OPERATIONS │ RUNTIME SERVICES │  DOCUMENTATION   │
│  (Status Info)   │  (Mission Mgmt)  │  (Backend Svcs)  │  (Technical Docs) │
├──────────────────┼──────────────────┼──────────────────┼──────────────────┤
│ • Starship Info  │ • Mission Reg.   │ • Ollama LLM     │ • Architecture    │
│ • Captain Status │ • Number One Bot │ • Supabase DB    │ • API Reference   │
│ • Op Status      │ • Decision Log   │ • OpenClaw Box   │ • Setup Guide     │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘

┌──────────────────┐
│   DEVELOPMENT    │
│  (Code/Repos)    │
├──────────────────┤
│ • Main Repo      │
│ • Control Deck   │
│ • Launchpad Src  │
└──────────────────┘
```

### Grid Layout
- **Columns:** 4 cards per row
- **Size:** Small cards for compact view
- **Theme:** Nord (professional dark theme)
- **Responsive:** Adapts to screen size

---

## Section Descriptions

### 1. Command Status (Shield Icon)
**Purpose:** Display ship and command information  
**Status Type:** Informational (non-clickable)

| Card | Purpose | Type |
|------|---------|------|
| Starship Endeavour | Ship identity | Info |
| Captain TJR | Commander status | Info |
| Status Operational | Operational status | Info |

**Use Case:** Verify command authority and operational state at a glance

---

### 2. Core Operations (Chess Board Icon)
**Purpose:** Access mission management and command interfaces  
**Status Type:** Operational (clickable links to running services)

| Card | Service | Port | Lifecycle |
|------|---------|------|-----------|
| Mission Registry | REST API | 5000 | Always-on |
| Number One Bot | Slack interface | 3001 | On-demand |
| Decision Log | Decision records | N/A | Static |

**Services:**
- **Mission Registry (5000)** — Core mission management API, always running
- **Number One (3001)** — Slack bot runtime, starts when needed via Control CLI
- **Decision Log** — Static reference to decision records (no service)

**Use Case:** Launch operational systems and track active missions

---

### 3. Runtime Services (Server Icon)
**Purpose:** Monitor backend service availability  
**Status Type:** Operational (clickable to service interfaces)

| Card | Service | Port | Type | Dependency |
|------|---------|------|------|------------|
| Ollama LLM | Language Model | 11434 | Always-on | Optional (AI features) |
| Supabase DB | PostgreSQL Database | 5432 | Always-on | Core |
| OpenClaw Sandbox | Code Execution | 8000 | On-demand | Optional |

**Ollama Health Monitoring:**
- Dashboard label includes 🟢 indicator when Ollama is running
- Test endpoint: `http://localhost:11434/api/tags`
- Required for: AI-powered features in Number One and other systems
- Optional: System can run without Ollama (degraded AI capabilities)

**Use Case:** Verify backend services are responsive and accessible

---

### 4. Documentation (Book Icon)
**Purpose:** Quick access to technical documentation  
**Status Type:** Reference (external GitHub links)

| Card | Purpose | Location |
|------|---------|----------|
| Architecture Decisions | ADRs and design patterns | GitHub |
| API Reference | REST API documentation | GitHub |
| Setup Guide | Configuration and deployment | Local |

**Use Case:** Browse architectural decisions and API documentation

---

### 5. Development (Terminal Icon)
**Purpose:** Access code repositories and source  
**Status Type:** Reference (external GitHub links)

| Card | Purpose | Location |
|------|---------|----------|
| Main Repository | Full USS TJR monorepo | GitHub |
| Control Deck Foundation | Service orchestration CLI | GitHub |
| Control Deck Launchpad | This dashboard source | GitHub |

**Use Case:** Access source code for debugging or contributions

---

## Service States

### Always-On Services (Critical)
These services run continuously and are essential to operations:

1. **Mission Registry (5000)**
   - Status: Always running
   - Purpose: Core mission management
   - Failure Impact: **Critical** — Operations cannot continue
   - Recovery: Restart via Control CLI

2. **Supabase Database (5432)**
   - Status: Always running (Docker container)
   - Purpose: Persistent data storage
   - Failure Impact: **Critical** — Data loss risk
   - Recovery: Restart Docker container

3. **Ollama LLM (11434)**
   - Status: Always running (when enabled)
   - Purpose: Local AI/LLM capabilities
   - Failure Impact: **Medium** — Degraded AI features only
   - Recovery: Restart via docker-compose

### On-Demand Services (Optional)
These services start when needed and don't impact baseline operations:

1. **Number One (3001)**
   - Status: Starts on-demand
   - Purpose: Slack bot runtime
   - Failure Impact: **Low** — Can retry later
   - Recovery: `./control start slack-bot`

2. **OpenClaw (8000)**
   - Status: Starts on-demand
   - Purpose: Code execution sandbox
   - Failure Impact: **Low** — Feature unavailable
   - Recovery: `./control start openclaw`

### Reference Services (External)
These are not managed by this system but are accessed via links:

1. **GitHub Repositories**
   - Status: External (GitHub.com)
   - Purpose: Source code access
   - Failure Impact: **None** to local system
   - Recovery: Check internet connectivity

---

## Managing Services

### Check Status

```bash
# View all service status
./control status

# Check specific service
./control status ollama

# View Docker containers
docker ps
docker-compose ps
```

**Expected output for healthy system:**
```
SERVICE          STATUS      PORT
mission-registry running     5000
supabase         running     5432
ollama           running     11434
slack-bot        stopped     3001 (on-demand)
openclaw         stopped     8000 (on-demand)
```

### Start Services

```bash
# Start all services
./control start all

# Start specific service
./control start ollama

# Start multiple services
./control start ollama supabase
```

### Stop Services

```bash
# Stop all services
./control stop all

# Stop specific service
./control stop ollama

# Stop dashboard only
docker-compose down
```

### Restart Services

```bash
# Restart all
./control restart all

# Restart specific service
./control restart ollama

# Restart Docker container
docker-compose restart
```

---

## Updating Configuration

### Modify Dashboard Cards

Edit `dashy-config.yml`:

```yaml
sections:
  - title: My Section
    icon: fas fa-icon
    items:
      - title: My Card
        description: Card description
        icon: fas fa-card-icon
        url: http://localhost:PORT
        target: _blank
```

**File structure:**
- One section per dashboard column (up to 4 displayed)
- Up to 12 items per section (3 rows × 4 columns)
- Icons: Font Awesome 6 (fas/fab prefix)

### Apply Changes

```bash
# Edit config
nano dashy-config.yml

# Restart container
docker-compose restart

# Hard-refresh browser (Cmd+Shift+R or Ctrl+Shift+R)
```

### Revert to Defaults

```bash
# Restore from backup
cp dashy-config-v4-COMPATIBLE.yml dashy-config.yml

# Restart container
docker-compose restart
```

---

## Monitoring

### Health Checks

The dashboard container includes automatic health monitoring:

```bash
# View health status
docker inspect starfleet-command-centre | grep -A 5 Health
```

**Expected status:** `healthy` (after ~40 seconds startup)

**Health check command:** `curl -f http://localhost` (inside container)

### Logs

```bash
# View recent logs
docker logs starfleet-command-centre

# Follow logs in real-time
docker logs -f starfleet-command-centre

# View logs with timestamps
docker logs -t starfleet-command-centre

# View last 100 lines
docker logs --tail 100 starfleet-command-centre
```

### Performance Monitoring

Dashboard system resources (typical):
- **CPU:** 1-2% idle, <5% active use
- **Memory:** 100-150 MB
- **Disk:** ~300 MB (Docker image)
- **Startup time:** ~30-40 seconds

Monitor with:
```bash
docker stats starfleet-command-centre
```

---

## Troubleshooting

### Issue: Dashboard shows default Dashy interface

**Symptoms:** See generic Dashy demo instead of STARFLEET COMMAND

**Causes:**
- Configuration not loaded
- Browser caching old version
- Mount path incorrect

**Resolution:**
```bash
# 1. Hard-refresh browser
# Cmd+Shift+R (macOS) or Ctrl+Shift+R (Linux/Windows)

# 2. Check container is running
docker ps | grep starfleet

# 3. Check logs for errors
docker logs starfleet-command-centre

# 4. Verify config file exists
ls -la dashy-config.yml

# 5. Restart container
docker-compose restart
```

### Issue: Service links return "Connection refused"

**Symptoms:** Clicking a service link returns error

**Causes:**
- Service not running
- Wrong port number
- Service crashed

**Resolution:**
```bash
# 1. Check if service is running
./control status

# 2. Start missing service
./control start ollama

# 3. Test port directly
curl http://localhost:11434

# 4. Check service logs
docker logs mission-registry

# 5. Restart all services
./control restart all
```

### Issue: Icons not displaying

**Symptoms:** Cards show empty/missing icons

**Causes:**
- Font Awesome not loading
- Invalid icon name
- Network issue

**Resolution:**
```bash
# 1. Hard-refresh browser
# Cmd+Shift+R (macOS) or Ctrl+Shift+R (Linux/Windows)

# 2. Check browser console
# Press F12, go to Console tab, look for errors

# 3. Verify internet connectivity
ping cloudflare.com

# 4. Check icon names in config
grep "icon:" dashy-config.yml

# 5. Restart dashboard
docker-compose restart
```

### Issue: Dashboard won't start

**Symptoms:** `docker-compose up` fails or container exits immediately

**Causes:**
- Port 8081 already in use
- Docker daemon not running
- Configuration syntax error

**Resolution:**
```bash
# 1. Check if port is in use
lsof -i :8081

# 2. Free the port or use different port
# Edit docker-compose.yml, change port 8081 to 8082

# 3. Verify Docker is running
docker ps

# 4. Validate YAML syntax
python -m yaml dashy-config.yml

# 5. Check Docker logs
docker logs starfleet-command-centre

# 6. Try full rebuild
docker-compose down -v
docker-compose up -d
```

---

## Maintenance

### Daily Operations
- Verify dashboard loads: `http://localhost:8081`
- Check service status: `./control status`
- Review any error logs: `docker logs starfleet-command-centre`

### Weekly Tasks
- Backup configuration: `cp dashy-config.yml dashy-config.backup.yml`
- Test service links (click each card)
- Verify Ollama is running if AI features needed

### Monthly Tasks
- Update Docker image: `docker pull lissy93/dashy:latest`
- Verify all documentation links are current
- Review and clean old container images: `docker image prune`

### As-Needed
- Update dashboard cards: Edit `dashy-config.yml`
- Add new services: Add to `sections` in config
- Change theme: Update `theme: nord` to different theme

---

## Advanced Configuration

### Using Custom Themes

Dashy v4 supports these themes:
- `nord` — Dark blue/gray (default)
- `dracula` — Dark purple/red
- `catppuccin` — Dark pastel
- `monochrome` — Black/white
- `high-contrast` — Maximum accessibility

Change in `dashy-config.yml`:
```yaml
appConfig:
  theme: dracula  # Change here
```

### Adding Custom CSS

Edit `dashy-config.yml`:
```yaml
appConfig:
  theme: nord
  # ... other settings
  # Custom CSS injected here if needed
```

### Icons Available

Font Awesome 6 icons with prefixes:
- `fas` — Solid icons (fas fa-icon-name)
- `fab` — Brand logos (fab fa-brand-name)

Examples:
- `fas fa-rocket` — Rocket
- `fas fa-database` — Database cylinder
- `fab fa-github` — GitHub logo
- `fas fa-terminal` — Terminal/console

Browse available icons: https://fontawesome.com/icons

---

## Disaster Recovery

### Backup Procedure

```bash
# Backup configuration
cp dashy-config.yml dashy-config.backup.$(date +%Y%m%d).yml

# Backup all assets
cp -r assets/ assets.backup/

# Full backup
tar czf control-deck-backup.tar.gz \
  dashy-config.yml \
  docker-compose.yml \
  assets/ \
  theme-starfleet.css
```

### Restore Procedure

```bash
# Restore from backup
cp dashy-config.backup.20260608.yml dashy-config.yml

# Restart container
docker-compose restart

# Verify
curl http://localhost:8081
```

### Factory Reset

```bash
# Stop and remove everything
docker-compose down -v

# Reset to defaults
cp dashy-config-v4-COMPATIBLE.yml dashy-config.yml

# Restart with defaults
docker-compose up -d
```

---

## Support & Escalation

### Diagnostics Commands

```bash
# Full system check
./control status
docker ps
docker logs starfleet-command-centre
curl -v http://localhost:8081

# Service connectivity test
curl http://localhost:5000    # Mission Registry
curl http://localhost:11434   # Ollama
curl http://localhost:5432    # Supabase
curl http://localhost:18789    # OpenClaw
curl http://localhost:3001    # Number One

# Configuration validation
cat dashy-config.yml | head -30
```

### Escalation Path

1. **Check status:** `./control status`
2. **Review logs:** `docker logs starfleet-command-centre`
3. **Test service connectivity:** `curl http://localhost:PORT`
4. **Restart service:** `./control restart SERVICE`
5. **Contact operations:** If still failing, escalate with diagnostics

---

## FAQ

**Q: Can I add more services to the dashboard?**  
A: Yes! Edit `dashy-config.yml` and add new items to sections.

**Q: What if a service is not responding?**  
A: Check status with `./control status` and restart with `./control restart SERVICE`.

**Q: How do I change the dashboard port?**  
A: Edit docker-compose.yml, change `"8081:80"` to desired port, restart.

**Q: Can I run multiple dashboards?**  
A: Yes, but use different ports and container names.

**Q: Is the dashboard secure?**  
A: It's localhost-only by default (no authentication). Do not expose to internet without security.

**Q: What theme should I use?**  
A: Nord (default) is recommended for professional operations.

---

## References

- **Dashy Documentation:** https://dashy.to/docs/
- **Docker Documentation:** https://docs.docker.com/
- **Font Awesome Icons:** https://fontawesome.com/icons
- **USSTJROS Repository:** https://github.com/timjarden-ross/USSTJROS

---

**Mission Status: OPERATIONAL** ✓

The Control Deck Launchpad is designed for stable, long-term operational use with minimal maintenance.

Ad Astra Per Aspera 🚀

---

*Last Updated: June 8, 2026*  
*Version: 1.0 (MVP Stable)*  
*Classification: USS TJR Operational Documentation*

