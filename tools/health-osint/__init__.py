# noqa: N999 - the "health-osint" directory name (hyphen) predates this
# ruff-triage pass and is referenced by path (not dotted-import) across
# cron/systemd units and other scripts (see tools/health-osint/*.py and
# its parsers/ subpackage). Renaming it to a valid module name would be a
# real cross-cutting change with production-invocation risk, out of scope
# for MSN-0370 (a lint-triage mission) — flagged here rather than renamed.
