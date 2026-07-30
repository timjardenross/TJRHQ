# Mission ID Minting — Architecture & Client Guide

**MSN-0147 | Single Mission Minting Service**

All canonical Mission IDs (`USS-TJR-MSN-NNNN`) are allocated by a single Python writer to eliminate cross-language lock contention. This document explains the architecture and how each client type mints a new ID.

---

## Architecture

```
┌────────────────────┐    subprocess    ┌─────────────────────┐
│  LCARS portal      │ ─────────────►  │  tools/mint_id.py   │
│  (TypeScript/Next) │                 └──────────┬──────────┘
└────────────────────┘                            │
                                                  │  import
┌────────────────────┐    POST /mint   ┌──────────▼──────────┐
│  Future clients    │ ─────────────►  │  tools/mint_server  │ (optional)
│  (any language)    │                 └──────────┬──────────┘
└────────────────────┘                            │
                                                  │  import
┌────────────────────┐    direct call  ┌──────────▼──────────┐
│  Slack bot         │ ─────────────►  │   id_registry.py    │ ◄── single writer
│  (Python)          │                 └──────────┬──────────┘
└────────────────────┘                            │
                                             .id-counters.json
                                        (fcntl.LOCK_EX atomic)
```

**Single writer rule**: `id_registry.py` is the **only** process that writes to `.id-counters.json`. All other clients route through it — either directly (Python), via subprocess (TypeScript), or via the HTTP service (any language).

---

## Counter File

`.id-counters.json` at the repository root tracks the high-water mark per prefix:

```json
{"MSN": 147, "BREQ": 17, "DEC": 31}
```

`id_registry.py` holds a `fcntl.LOCK_EX` file lock during every read-increment-write cycle, making it safe for concurrent Python processes. Non-Python callers use subprocess or HTTP to serialise through the same lock.

---

## Clients

### Slack bot (Python — direct)

```python
import id_registry
mission_id = id_registry.next_id("MSN")  # → USS-TJR-MSN-NNNN
```

### LCARS portal (TypeScript — subprocess)

```typescript
import { nextId } from '@/lib/id-registry';
const missionId = await nextId('MSN');   // → USS-TJR-MSN-NNNN
```

`lcars-portal/src/lib/id-registry.ts` calls `python3 tools/mint_id.py MSN` via `child_process.execFile`. The `REPO_ROOT` env var must point to the repository root if the portal is not run from `lcars-portal/`.

```bash
REPO_ROOT=/path/to/USSTJROS npx next start
```

### Any language — HTTP service

Start the mint server:

```bash
python3 tools/mint_server.py          # default port 5052
MINT_PORT=5053 python3 tools/mint_server.py
```

Mint an ID:

```bash
curl -s -X POST http://localhost:5052/mint \
     -H 'Content-Type: application/json' \
     -d '{"type": "MSN"}'
# → {"mission_id": "USS-TJR-MSN-0148", "type": "MSN", "status": "allocated"}
```

Health check:

```bash
curl -s http://localhost:5052/health
# → {"status": "ok", "counter_file": "/path/to/.id-counters.json"}
```

---

## CLI wrapper

```bash
python3 tools/mint_id.py MSN    # → USS-TJR-MSN-0148
python3 tools/mint_id.py BREQ   # → BREQ-0018
python3 tools/mint_id.py DEC    # → DEC-0032
```

---

## Canonical format

| Prefix | Format | Example |
|--------|--------|---------|
| MSN | `USS-TJR-MSN-NNNN` | `USS-TJR-MSN-0148` |
| BREQ | `BREQ-NNNN` | `BREQ-0018` |
| DEC | `DEC-NNNN` | `DEC-0032` |

Short aliases (`MSN-NNNN`) and legacy timestamp IDs (`M-YYYYMMDD-*`) are preserved for backwards compatibility but are never emitted for new missions.

---

## Tests

```bash
python3 tools/test_mint.py
```

Covers: sequential uniqueness, concurrent uniqueness (10 threads), non-MSN prefix formats, CLI wrapper output, HTTP server `/mint` and `/health` endpoints.

---

## Fallback behaviour

If `id_registry.py` fails (e.g., filesystem unavailable), each client degrades gracefully:

- **Python direct**: `id_registry.next_id()` returns a timestamp-based ID (`USS-TJR-MSN-HHMMSSFFFF`)
- **TypeScript**: `nextId()` catch block returns `USS-TJR-MSN-${Date.now()}`
- **HTTP service**: returns HTTP 500 with `{"error": "..."}`

Fallback IDs are valid for tracking but will not appear in the authoritative counter sequence. They should be updated to a canonical ID once the filesystem recovers.
