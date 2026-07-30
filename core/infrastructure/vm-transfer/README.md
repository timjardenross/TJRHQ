# Secure File Transfer to VM — USS-TJR-MSN-0205B

Moves eligible files named in a Mac Collector Agent
([MSN-0205A](../mac-collector/README.md)) manifest to the VM's inbox over
rsync-over-SSH, verifies SHA256 checksums remotely, and reconciles each
file to `inbox/received` (checksum OK) or `inbox/failed` (mismatch or
transfer error).

## Scope

**In scope:** rsync-over-SSH transfer, retry with backoff, remote checksum
verification, transfer logging, the `inbox/{pending,received,failed,archive}`
folder structure, a transfer-time exclude blocklist.

**Out of scope:** document parsing, OCR, LLM processing, memory ingestion —
this only moves bytes and verifies they arrived intact.

## Setup

```bash
cd core/infrastructure/vm-transfer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml: remote host/user/ssh_key/base_path
```

`config.yaml` is gitignored. Auth is SSH-key-only (no password auth,
`BatchMode=yes`) — the configured key must already be authorized on the VM
and, ideally, loaded in an agent or passphrase-less for unattended runs.
The `ssh`/`rsync` binaries must be on `PATH`; the VM needs GNU `sha256sum`.

## Usage

```bash
# Produce a manifest first, from mac-collector:
#   (cd ../mac-collector && python cli.py export-manifest)

# Preview — runs rsync --dry-run per source, touches nothing else
python cli.py transfer-dry-run --manifest ../mac-collector/manifests/manifest-<ts>.json

# Real transfer
python cli.py transfer --manifest ../mac-collector/manifests/manifest-<ts>.json

# Resume the checksum/move step if a prior run was interrupted after rsync
# succeeded but before verification completed
python cli.py verify-transfer

# Retry files currently marked failed (rsync error or checksum mismatch),
# up to retry.max_attempts from config.yaml
python cli.py retry-failed
```

All commands default to JSON output (`--format json`); pass `--format text`
for a plain Python repr.

## How it works

1. **Select** — every file in the manifest is checked against
   `exclude_patterns` (a second, transfer-time blocklist on top of whatever
   mac-collector already excluded — use it to hold back files still under
   review) and against local state: a file already `verified` with a
   matching SHA256 is skipped as already delivered. Everything else is
   queued `pending` in `transfer.db`.
2. **rsync** — files are grouped by source and pushed with
   `rsync -az --files-from=<rel paths> <source_root>/ vm:<base_path>/pending/<source>/`,
   which preserves the relative path structure exactly. Failures retry up
   to `retry.max_attempts` with linear backoff; after retries are
   exhausted the whole group is marked `failed` and logged — the checksum
   step is never reached for a group that didn't rsync successfully.
3. **Verify** — after a successful rsync, files are marked `transferred`
   and a per-batch metadata manifest (`pending/_manifests/manifest-<id>-
   <source>.json`) is pushed alongside them. A single `sha256sum -c -`
   command runs remotely (checksums piped over stdin — no extra remote
   file needed) against everything just transferred.
4. **Move** — checksum matches move `pending/<source>/<rel>` →
   `received/<source>/<rel>`; mismatches (or files missing from the
   `sha256sum -c` output) move to `failed/<source>/<rel>` and are marked
   `failed` with an incremented `attempts` counter, making them eligible
   for `retry-failed`. All moves for a batch run as one remote script (one
   SSH round trip), not one call per file.
5. **`archive`** is created under the inbox root for completeness but is
   not populated by this agent — it's for whatever downstream ingestion
   process consumes `received/` next.

`transfer-dry-run` runs the same selection logic and calls `rsync
--dry-run` for a realistic preview, but never calls `ensure_remote_dirs`,
never verifies checksums, never moves anything, and rolls back its SQLite
transaction — nothing is persisted or mutated remotely.

`verify-transfer` re-runs step 3–4 for files stuck in `transferred` status
(rsync succeeded, but the process died before verification completed) —
this is the resume path for an interrupted run, without re-sending
anything.

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Tests run against a `FakeTransport` test double (see `tests/fake_transport.py`)
with no real network or subprocess calls — they exercise selection,
exclude filtering, idempotent skipping, dry-run non-persistence, checksum
OK/FAILED routing, rsync-failure retry exhaustion, `retry-failed`, and the
`verify-transfer` resume path.
