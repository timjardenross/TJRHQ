# STARFLEET COMMAND CENTRE — Setup Guide

## Quick Start (Docker - Recommended)

```bash
# Clone the repository
git clone https://github.com/timjarden-ross/USSTJROS.git
cd USSTJROS/core/command-centre

# Start the command centre
docker-compose up -d

# Access at: http://localhost:8080
```

## Prerequisites

### Option 1: Docker (Recommended)
- Docker Desktop or Docker Engine
- Docker Compose 1.29+
- 512MB RAM available
- Port 8080 available

### Option 2: Local Development
- Node.js 16+ and npm
- Port 8080 available
- 1GB RAM available

## Installation

### Docker Deployment

```bash
# 1. Build and start
docker-compose up -d

# 2. View logs
docker-compose logs -f command-centre

# 3. Verify it's running
curl http://localhost:8080

# 4. Stop
docker-compose down

# 5. Clean up (remove all data)
docker-compose down -v
```

### Local Development

```bash
# 1. Install Dashy globally
npm install -g @lissy93/dashy

# 2. Run with config
dashy --config ./dashy-config.yml --port 8080

# 3. Access at http://localhost:8080
```

## Configuration

### Directory Structure

```
command-centre/
├── docker-compose.yml              # Container orchestration
├── dashy-config.yml                # Main configuration
├── theme-starfleet.css             # Custom theme
├── assets/
│   ├── starfleet-logo.svg         # Logo placeholder
│   ├── favicon.ico                # Favicon
│   ├── fonts/                     # Custom fonts
│   └── backgrounds/               # Background images
├── data/                          # Persistent data (created by Docker)
├── SETUP.md                       # This file
├── USAGE.md                       # Usage guide
├── MSN-0035-ASSESSMENT.md         # Design document
└── README.md                      # Overview
```

### Custom Configuration

Edit `dashy-config.yml` to:
- Change title and branding
- Add/remove sections
- Configure status checks
- Adjust layout and appearance
- Set keyboard shortcuts

### Custom Theme

Edit `theme-starfleet.css` to:
- Adjust colors (CSS variables at top)
- Modify fonts and typography
- Change animations and transitions
- Customize component styling
- Add new styles

## Accessing the Command Centre

### Local Access
```
http://localhost:8080
```

### Through Reverse Proxy
```
https://starfleet.endeavour.local/
```
(Requires NGINX/Apache configuration)

## Features

### Sections
1. **COMMAND** — Missions, queues, executive updates
2. **OPERATIONS** — Slack, workflows, infrastructure
3. **SCIENCE** — AI assistants and research tools
4. **ARCHIVES** — Documentation and knowledge base
5. **INTELLIGENCE** — Briefings and monitoring
6. **MEDICAL** — Health tracking and wellness
7. **SHIP SYSTEMS** — Docker, monitoring, backups

### Interactive Elements
- Live status checks (green/yellow/red indicators)
- Keyboard shortcuts for quick access
- Search functionality across sections
- Responsive layout (desktop/tablet/mobile)
- Dark mode optimized

### Performance
- Lightweight and fast
- ~5 second load time
- Real-time status updates every 60 seconds
- Optimized for modern browsers

## Customization

### Adding New Sections

Edit `dashy-config.yml`:

```yaml
- name: NEW SECTION
  icon: fas fa-icon-name
  displayData:
    rows: 2
    cols: 3
  items:
    - title: Item Title
      icon: fas fa-icon
      url: https://example.com
      statusCheck: true
      statusCheckUrl: https://example.com/health
```

### Changing Colors

Edit `theme-starfleet.css`:

```css
:root {
  --color-bg-primary: #0B0F1A;      /* Your color */
  --color-primary: #4D5A94;         /* Your color */
  /* ... etc */
}
```

### Adding Custom Icons

Place SVG files in `assets/icons/` and reference in config:

```yaml
icon: /assets/icons/my-icon.svg
```

## Integration Setup

### Phase 2: Dynamic Content

To connect live data sources, configure API endpoints in `dashy-config.yml`:

```yaml
statusCheckUrl: http://localhost:5000/api/missions/status
```

And implement the APIs in your backend:

```python
@app.route('/api/missions/status')
def missions_status():
    return {
        "status": "operational",
        "total": 12,
        "active": 12
    }
```

## Troubleshooting

### Port Already in Use
```bash
# Find process using port 8080
lsof -i :8080

# Use different port
docker-compose down
# Edit docker-compose.yml, change ports: ["8081:80"]
docker-compose up -d
```

### Configuration Not Loading
```bash
# Check volume mounting
docker-compose logs command-centre

# Verify file exists
ls -la dashy-config.yml
theme-starfleet.css

# Restart with fresh config
docker-compose down
docker-compose up -d --force-recreate
```

### Slow Performance
```bash
# Check container resources
docker stats command-centre

# Increase allocated memory (edit docker-compose.yml)
# Restart container
docker-compose restart command-centre
```

### Status Checks Not Working
```bash
# Test endpoint directly
curl -I http://localhost:5000/api/missions/status

# Check firewall rules
sudo ufw allow 5000/tcp
```

## Backup and Restore

### Backup Configuration
```bash
# Backup all configuration
tar czf starfleet-backup-$(date +%Y%m%d).tar.gz \
  dashy-config.yml \
  theme-starfleet.css \
  assets/

# Store backup safely
mv starfleet-backup-*.tar.gz /path/to/backups/
```

### Restore from Backup
```bash
# Extract backup
tar xzf starfleet-backup-YYYYMMDD.tar.gz

# Restart container
docker-compose down
docker-compose up -d
```

## Production Deployment

### Security Checklist
- [ ] Enable HTTPS/TLS
- [ ] Set up authentication
- [ ] Configure firewall rules
- [ ] Use environment variables for secrets
- [ ] Enable access logs
- [ ] Set up monitoring and alerts
- [ ] Regular backups

### High Availability
```yaml
# Use multiple replicas
services:
  command-centre-1:
    # ...
  command-centre-2:
    # ...
  nginx:
    # Load balancer
```

### Monitoring

Set up monitoring for:
- Container uptime
- API response times
- Status check failures
- Resource usage
- Error logs

## Maintenance

### Regular Tasks
- Monthly configuration review
- Quarterly security updates
- Backup verification
- Performance optimization
- Documentation updates

### Updates
```bash
# Update Dashy image
docker-compose pull
docker-compose down
docker-compose up -d
```

## Support and Documentation

- **Design Document**: MSN-0035-ASSESSMENT.md
- **Usage Guide**: USAGE.md
- **Dashy Docs**: https://dashy.io
- **Issues**: GitHub Issues in USSTJROS

## Next Steps

1. ✅ Deploy command centre (this guide)
2. ⬜ Customize branding and colors (USAGE.md)
3. ⬜ Integrate with APIs (Phase 2)
4. ⬜ Set up monitoring and alerts
5. ⬜ Deploy to production

---

**Status**: Ready for deployment  
**Version**: 1.0  
**Last Updated**: 2026-06-08
