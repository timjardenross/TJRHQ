# Engineering Officer — Graphify Query Templates

Standard queries for architectural discovery using the Graphify knowledge graph.  
Graph: `graphify-out/merged-graph.json` | Established: MSN-0204 (2026-07-01)

```bash
GRAPHIFY=~/.local/share/uv/tools/graphifyy/bin/graphify
GRAPH=~/Documents/GitHub/USSTJROS/graphify-out/merged-graph.json
```

---

## Dependency Queries

```bash
# What depends on Supabase?
$GRAPHIFY query "which components depend on supabase" --graph $GRAPH

# What depends on Command Memory?
$GRAPHIFY query "what depends on command memory" --graph $GRAPH

# What calls the Telegram bot?
$GRAPHIFY query "telegram bot interactions and integrations" --graph $GRAPH

# What touches the health data layer?
$GRAPHIFY query "health data access and scoring" --graph $GRAPH

# What depends on the Number One orchestrator?
$GRAPHIFY query "NumberOne coordination and routing" --graph $GRAPH
```

---

## Impact Analysis

```bash
# What breaks if supabase client changes?
$GRAPHIFY affected "supabase" --graph $GRAPH

# What is impacted by changes to command_memory_integration?
$GRAPHIFY affected "command_memory_integration" --graph $GRAPH

# What calls triage_package?
$GRAPHIFY affected "triage_package" --graph $GRAPH --relation calls
```

---

## Path Queries (Cross-Service)

```bash
# How does a Slack command reach the database?
$GRAPHIFY path "app.py" "supabase" --graph $GRAPH

# Path from XO bot to Number One
$GRAPHIFY path "xo" "NumberOne" --graph $GRAPH

# How does research reach the Slack surface?
$GRAPHIFY path "SlackResearchIntegration" "app.py" --graph $GRAPH
```

---

## Component Explanation

```bash
# Core orchestration
$GRAPHIFY explain "NumberOne" --graph $GRAPH
$GRAPHIFY explain "ProgramPortfolio" --graph $GRAPH
$GRAPHIFY explain "ExecutionPackage" --graph $GRAPH

# Health layer
$GRAPHIFY explain "HealthScore" --graph $GRAPH
$GRAPHIFY explain "capacity_gate" --graph $GRAPH

# Memory adapters
$GRAPHIFY explain "NumberOneMemoryAdapter" --graph $GRAPH
$GRAPHIFY explain "CommanderMemoryAdapter" --graph $GRAPH

# LCARS portal
$GRAPHIFY explain "command-centre.ts" --graph $GRAPH
$GRAPHIFY explain "supabase.ts" --graph $GRAPH
```

---

## Architectural Questions

```bash
# Entry points
$GRAPHIFY query "main entry point and orchestration hub" --graph $GRAPH

# Authentication / authority
$GRAPHIFY query "authority validation and governance enforcement" --graph $GRAPH

# Error handling
$GRAPHIFY query "error handling and escalation paths" --graph $GRAPH

# Data flow from capture to storage
$GRAPHIFY query "capture pipeline to supabase storage" --graph $GRAPH

# ADR implementation tracing
$GRAPHIFY query "which components implement mission lifecycle" --graph $GRAPH
```

---

## ADR Traceability (once governance indexed)

```bash
# After running: $GRAPHIFY ./core/governance
$GRAPHIFY query "ADR-009 supabase operational data layer" --graph $GRAPH
$GRAPHIFY query "ADR-013 number one orchestrator" --graph $GRAPH
$GRAPHIFY query "ADR-031 agent orchestration" --graph $GRAPH
```

---

## Benchmark & Health

```bash
# Token reduction benchmark
$GRAPHIFY benchmark $GRAPH

# Graph diagnostics
$GRAPHIFY diagnose multigraph --graph $GRAPH
```

---

*Query template library — Engineering Officer — MSN-0204*
