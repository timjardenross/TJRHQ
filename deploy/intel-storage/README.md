Package B: isolated local intelligence store (fixtures only). `install.sh` / `teardown.sh [--purge]` as root; scripts run from /opt/tjrhq-intel.
`python3 -I fixtures.py N` and `embed.py` as tjrhq-intel-ingest; `store.py verify|orphans|gc|search` ; `backup.py run|check-fresh` and `restore.py DIR` as root.
Enable `tjrhq-intel-backup.timer` and `tjrhq-intel-freshness.timer` only once the store holds data (after a restore, not before it).
No network listener: the database container has no network and is reached only through /run/tjrhq-intel.
