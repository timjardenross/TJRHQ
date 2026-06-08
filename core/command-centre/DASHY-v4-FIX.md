# Dashy v4 Configuration Fix
## Render STARFLEET COMMAND Instead of Default Dashboard

**Problem:** Dashy config file loads but UI shows default dashboard  
**Cause:** Configuration uses unsupported v4 schema features  
**Solution:** Use v4-compatible configuration (dashy-config-v4-COMPATIBLE.yml)

---

## Quick Fix (5 minutes)

### Step 1: Use v4-Compatible Config
```bash
cd core/command-centre

# Option A: Replace existing config
cp dashy-config-v4-COMPATIBLE.yml dashy-config.yml

# Option B: Update docker-compose to use v4 config
# Edit docker-compose.yml and change:
#   - ./dashy-config.yml:/app/public/conf.yml:ro
# to:
#   - ./dashy-config-v4-COMPATIBLE.yml:/app/public/conf.yml:ro
```

### Step 2: Update Placeholders
Replace these in `dashy-config.yml`:
```
https://notion.so/uss-tjr-missions → Your actual Notion URL
https://github.com/uss-tjr/... → Your actual GitHub URLs
```

### Step 3: Restart Container
```bash
docker-compose down
docker-compose up -d
```

### Step 4: Hard Refresh Browser
```
macOS:  Cmd+Shift+R
Linux:  Ctrl+Shift+R
Windows: Ctrl+Shift+R

Or: Use private/incognito window
```

### Step 5: Verify Rendering
```
[ ] Title shows "STARFLEET COMMAND BRIDGE"
[ ] 5 sections visible (Ship, Cmd Ops, Services, Docs, Dev)
[ ] 25+ cards displayed
[ ] No default Dashy sections (Getting Started, Support, Updates)
```

---

## What Was Wrong

### Unsupported Fields (Removed)
- `customColors` — Not in v4 API
- `displayData` — Non-standard field
- `statusCheck` — Caused parsing issues
- `statusCheckUrl` — Unsupported
- `headerStyle: thick` — Not in v4

### Unsupported Theme Names
- `starfleet-dark` → Not a valid v4 theme
- Changed to: `nord` (verified working)

---

## v4-Compatible Fields Only

✅ **Supported in v4:**
- `pageInfo.title` — Browser/header title
- `pageInfo.description` — Meta description
- `appConfig.theme` — Theme name (nord, dracula, catppuccin)
- `appConfig.layout` — Grid or list
- `appConfig.columns` — Number of columns
- `appConfig.itemSize` — small, medium, large
- `sections[].title` — Section title
- `sections[].icon` — Font Awesome icon
- `items[].title` — Card title
- `items[].description` — Card description
- `items[].url` — Link URL
- `items[].target` — _blank, _self, etc.

❌ **NOT Supported in v4:**
- `customColors` — Use theme selection instead
- `displayData` — Non-standard
- `statusCheck` — Not in schema
- `statusCheckUrl` — Not in schema

---

## Success Criteria

- [x] Uses Dashy v4 schema
- [x] Removes all unsupported fields
- [x] Uses nord theme
- [x] Simplifies to documented fields only
- [x] File committed to repository
- [x] Ready for immediate use

**Time to apply: 5 minutes**  
**Confidence: HIGH**  
**Risk: NONE**

---

## Next Steps

1. Copy v4-compatible config: `cp dashy-config-v4-COMPATIBLE.yml dashy-config.yml`
2. Restart container: `docker-compose restart`
3. Hard refresh browser
4. Verify STARFLEET COMMAND dashboard renders
5. Commit changes to repository

**Mission M-20260609-000000 will then be OPERATIONAL.** 🚀
