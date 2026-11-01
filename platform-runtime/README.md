# platform-runtime

## On-demand tool venvs

2026-09-26 (HQ Consolidation Audit): `.venv-garak`, `.venv-docling`, and
`.venv-ragas` were removed from this directory to reclaim ~8.8GB. Confirmed
before removal: none of the three has any cron/timer/scheduled invocation —
they're manual/on-demand CLI tools only (garak red-team sweep, docling
document ingestion, ragas quality eval), unlike `.venv-llmsec` (the live
per-request PII/prompt-injection guardrail gate, called from
`core/model-router/app.py` on every cloud dispatch — that one stays resident,
do not remove it the same way).

If you need one of the three, recreate it first:

```bash
# garak
python3 -m venv platform-runtime/.venv-garak
platform-runtime/.venv-garak/bin/pip install -r core/quality/requirements-garak.txt

# docling
python3 -m venv platform-runtime/.venv-docling
platform-runtime/.venv-docling/bin/pip install -r core/knowledge/requirements-docling.txt

# ragas
python3 -m venv platform-runtime/.venv-ragas
platform-runtime/.venv-ragas/bin/pip install -r core/quality/requirements-ragas.txt
```

`tools/garak_sweep.sh` and `core/quality/garak_gate.py` already detect a
missing `.venv-garak` and print these exact commands (exit code 2) rather
than crashing. `docling_processor.py`/`ragas_eval.py` are invoked directly
under their own venv's interpreter — a missing venv fails immediately and
obviously (file not found) rather than silently.
