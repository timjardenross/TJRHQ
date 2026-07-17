#!/bin/bash
# Weekly health intelligence chain: fresh wellness articles -> synthesis -> article enrichment.
# Each step is best-effort (matches this pipeline's existing graceful-degradation
# philosophy) — a failure in one step is logged but doesn't block the next.
set -uo pipefail
cd /opt/starship-endeavour
PY=/opt/starship-endeavour/platform-runtime/.venv/bin/python

echo "=== $(date -u +%FT%TZ) wellness_rss_import ==="
"$PY" -m tools.intelligence.wellness_rss_import --limit 20 || echo "[run_weekly_intelligence] wellness_rss_import failed (non-fatal, continuing)"

echo "=== $(date -u +%FT%TZ) weekly_synthesis ==="
"$PY" core/health/weekly_synthesis.py || echo "[run_weekly_intelligence] weekly_synthesis failed (non-fatal, continuing)"

echo "=== $(date -u +%FT%TZ) source_article_enricher ==="
"$PY" core/health/source_article_enricher.py --days 7 || echo "[run_weekly_intelligence] source_article_enricher failed"

echo "=== $(date -u +%FT%TZ) done ==="
