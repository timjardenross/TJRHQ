Package B: isolated local intelligence store (fixtures only). `install.sh` / `teardown.sh [--purge]` as root; scripts run from /opt/tjrhq-intel.
`python3 -I fixtures.py N` and `embed.py` as tjrhq-intel-ingest; `store.py verify|orphans|gc|search` ; `backup.py run|check-fresh` and `restore.py DIR` as root.
Enable `tjrhq-intel-backup.timer` and `tjrhq-intel-freshness.timer` only once the store holds data (after a restore, not before it).
After a restore, database, documents, provenance and full-text search are the 24-hour recovery target. Vectors follow: `embed.py 1000000 24` rebuilds active\ninvestigations and recent evidence first, then `embed.py` for the rest; `store.py coverage` states how degraded semantic search is meanwhile.\nPackage C pilot: `package_c.py` (synthetic | plan | import | verify | compare | rollback) and `deletions.py` for deletions that must survive a restore.
A purge removes the local deletion ledger; the off-host copy is merged back and applied by every restore.
No network listener: the database container has no network and is reached only through /run/tjrhq-intel.
