# Runbook: Graphify Knowledge Graph Maintenance

**Tool:** Graphify v0.9.3  
**Binary:** `~/.local/share/uv/tools/graphifyy/bin/graphify`  
**Merged graph:** `graphify-out/merged-graph.json`  
**Established:** MSN-0203 / MSN-0204 (2026-07-01)

---

## Quick Reference

```bash
# All commands run from repo root
cd ~/Documents/GitHub/USSTJROS
GRAPHIFY=~/.local/share/uv/tools/graphifyy/bin/graphify
GRAPH=graphify-out/merged-graph.json
```

---

## 1. Regenerate the Full Merged Graph

Run this after significant code changes, or when a service graph is stale.

```bash
GEMINI_API_KEY already set via .zshrc — no manual export needed.

# Step 1 — Re-index changed service(s)
$GRAPHIFY ./slack-bot
$GRAPHIFY ./core/coordination
$GRAPHIFY ./core/advisory
$GRAPHIFY ./core/engineering
$GRAPHIFY ./core/context-assembly
$GRAPHIFY ./core/health
$GRAPHIFY ./core/knowledge_navigation
$GRAPHIFY ./core/intelligence
$GRAPHIFY ./core/capture
$GRAPHIFY ./core/inbox
$GRAPHIFY ./telegram-bot
$GRAPHIFY ./xo-bot
$GRAPHIFY ./lcars-portal/src

# Step 2 — Rebuild merged graph
$GRAPHIFY merge-graphs \
  slack-bot/graphify-out/graph.json \
  lcars-portal/src/graphify-out/graph.json \
  telegram-bot/graphify-out/graph.json \
  xo-bot/graphify-out/graph.json \
  core/coordination/graphify-out/graph.json \
  core/health/graphify-out/graph.json \
  core/knowledge_navigation/graphify-out/graph.json \
  core/advisory/graphify-out/graph.json \
  core/engineering/graphify-out/graph.json \
  core/context-assembly/graphify-out/graph.json \
  core/intelligence/graphify-out/graph.json \
  core/capture/graphify-out/graph.json \
  core/inbox/graphify-out/graph.json \
  core/governance/graphify-out/graph.json \
  --out graphify-out/merged-graph.json
```

**Cost:** ~$0.05 per full regeneration (Gemini Flash, doc files only).  
**Time:** ~2–3 minutes for all 14 services.

---

## 2. Update a Single Service Graph

When only one service changes:

```bash
$GRAPHIFY ./slack-bot          # re-indexes, overwrites slack-bot/graphify-out/graph.json
# Then rebuild merged graph (Step 2 above)
```

Git hooks (`post-commit`, `post-checkout`) trigger `graphify update` automatically on commits — they update individual service graphs but do not rebuild the merged graph. Run Step 2 manually after a batch of commits.

---

## 3. Query the Graph

```bash
# Architectural question
$GRAPHIFY query "which components depend on supabase" --graph $GRAPH

# Dependency fan-in
$GRAPHIFY query "what depends on command memory" --graph $GRAPH

# Specific node explanation
$GRAPHIFY explain "NumberOne" --graph $GRAPH
$GRAPHIFY explain "ProgramPortfolio" --graph $GRAPH

# Shortest path between two components
$GRAPHIFY path "SlackResearchIntegration" "NumberOne" --graph $GRAPH

# Impact of a change
$GRAPHIFY affected "supabase" --graph $GRAPH
```

---

## 4. Benchmark Token Reduction

```bash
$GRAPHIFY benchmark $GRAPH
```

Current baseline: **182× token reduction** (10,049 nodes, 18,266 edges).

---

## 5. Check Git Hook Status

```bash
$GRAPHIFY hook status
```

Hooks installed: `post-commit`, `post-checkout` in `.git/hooks/`.  
Note: a known `.git/config` parsing warning appears (`github-pr-owner-number` duplicate) — this is harmless, hooks install and fire correctly.

---

## 6. Directories NOT Currently Indexed (doc-heavy, low code value)

| Directory | Reason skipped |
|---|---|
| `core/architecture/` | 0 code, 17 docs — pure design docs |
| `core/crew/` | 0 code, 47 docs — crew profiles |
| `core/infrastructure/` | 0 code, 45 docs — migration SQL files |
| `core/mission-control/` | 0 code, 22 docs — mission docs |
| `core/product/` | 0 code, 33 docs — product specs |

`core/governance/` (ADRs + authority matrix) is **included** in the merged graph as of MSN-0204.

---

## 7. Upgrade Graphify

```bash
~/.hermes/bin/uv tool install "graphifyy[gemini]" --force
```

---

*Runbook owner: Engineering Officer — last updated 2026-07-01*
