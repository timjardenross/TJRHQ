# Mac File Collector Agent — USS-TJR-MSN-0205A

Local Mac-side agent that scans configured OneDrive and iCloud Drive local
sync folders, fingerprints files with SHA256, applies ignore rules, tracks
new/changed/deleted files in a local SQLite DB, and exports a manifest of
eligible files for secure transfer to the VM.

## Scope

**In scope:** local filesystem scanning of already-synced OneDrive/iCloud
folders, SHA256 fingerprinting, YAML ignore rules, SQLite change tracking,
dry-run mode, manifest export.

**Out of scope:** OCR, embeddings, summarisation, memory ingestion, direct
OneDrive/iCloud API integration, and the actual file transfer itself — this
agent only prepares the manifest.

## Setup

```bash
cd core/infrastructure/mac-collector
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml: confirm source paths, adjust ignore rules
```

`config.yaml` is gitignored — it's machine-specific and may reference
personal folder paths.

## Usage

```bash
# Dry run — see what would change without touching the tracking DB
python cli.py scan --dry-run

# Real scan — updates collector.db
python cli.py scan

# Scan only one source
python cli.py scan --source onedrive

# Summary of tracked files
python cli.py status

# Files marked new / changed in the latest scan (or --scan-id N)
python cli.py list-new
python cli.py list-changed

# Export a manifest of all currently-eligible (non-ignored, active) files
python cli.py export-manifest
python cli.py export-manifest --output /tmp/manifest.json --source onedrive

# Curate a manifest to specific folders within a source (USS-TJR-MSN-0207D)
python cli.py export-manifest --source onedrive-starship-intake \
    --include-path "Operational Resilience/" \
    --include-path "PECB/" \
    --include-path "Medical Reports/" \
    --exclude-path "Scoliosis Images/"
```

`--include-path`/`--exclude-path` are repeatable and matched by path
*component* prefix against `rel_path` (e.g. `"PECB/"` matches
`PECB/cert.pdf` but not `PECB Extras/cert.pdf`); a pattern containing `*`
or `?` is matched as an fnmatch glob instead (e.g. `--exclude-path
"*.mp4"`). With no `--include-path`, every folder passes; `--exclude-path`
is applied after include and always wins, so excludes can carve a
sub-folder out of an included one (e.g. exclude `Medical
Reports/Scoliosis Images/` while including all of `Medical Reports/`).
Excluded-by-filter files are counted in the manifest's
`excluded_by_path_filter_count` but not listed, to keep the manifest
scoped to exactly what will be reviewed for transfer.

### Extension filtering and hard stops (USS-TJR-MSN-0208)

```bash
# Bounded overnight batch — folder scope + file-count/size caps
python cli.py export-manifest --source onedrive-starship-intake \
    --include-path "Operational Resilience/" \
    --include-path "PECB/" \
    --include-path "Medical Reports/" \
    --exclude-path "Scoliosis Images/" \
    --exclude-path "Transfer 1/" \
    --exclude-path "A_Cleanup/" \
    --max-files 250 \
    --max-total-bytes 2147483648
```

By default `export-manifest` only includes files whose extension is in
`manifest_guards.DEFAULT_INCLUDE_EXTENSIONS` (`.pdf .docx .txt .md .csv
.xlsx .xls`) — everything else, including the specific extensions this
mission exists to keep out of a bulk transfer
(`DEFAULT_EXCLUDE_EXTENSIONS`: `.jpg .jpeg .png .heic .mp4 .mov .epub
.mobi`) and anything not in either list, is excluded (counted in
`excluded_by_extension_filter_count`). `--allow-ext EXT` (repeatable)
explicitly permits an extra extension for one run if genuinely needed.

`--max-files` and `--max-total-bytes` don't truncate the manifest —
exceeding either is a **hard stop**: nothing is written to disk, the
violation is printed to stderr, and the command exits 1. The same hard-
stop treatment applies, regardless of `--include-path`/`--exclude-path`/
extension filtering, if the *final* candidate list still contains a
`Scoliosis Images` path component (pass `--allow-scoliosis-images` if
that's genuinely intended) or any of the default-blocked extensions —
this is a defense-in-depth check on the actual result, not just the
flags given, so a missing `--include-path` (which otherwise lets every
folder pass) or a stray `--allow-ext` still gets caught before anything
is written.

All commands default to JSON output (`--format json`); pass `--format text`
for a plain Python repr.

## How it works

1. `scan` walks each enabled source folder (skipping symlinks), applies
   `ignore.patterns` / `max_file_size_mb` / `ignore_hidden` from
   `config.yaml`, and SHA256-hashes every eligible file.
2. Each file is upserted into the `files` table keyed on
   `(source_name, rel_path)`; a hash mismatch marks it `changed`, a first
   sighting marks it `new`. Files previously tracked as `active` that
   weren't seen this walk are marked `deleted` — but only for a source
   whose root path actually existed and was walked, so an unmounted
   drive never mass-deletes tracked history.
3. Every new/changed/deleted event is also appended to the `changes` log,
   scoped to the `scan_id` that produced it, so `list-new`/`list-changed`
   can report on a specific run without recomputing anything.
4. `--dry-run` runs the exact same walk/diff logic, then rolls back the
   SQLite transaction instead of committing — nothing is written to
   `collector.db`.
5. `export-manifest` reads the current `active` file set (not tied to one
   scan) and writes a JSON manifest with path, hash, and size for
   whatever downstream process handles the actual secure transfer to the
   VM.

## Cloud-aware collection

OneDrive "Files On-Demand" and modern iCloud Drive can leave a file's
directory entry present on disk without its content ever being downloaded.
Before this was handled explicitly, the collector had no way to tell a
cloud-only placeholder apart from a real file — it just hashed whatever
bytes `open()` returned, which either reads garbage/zero-byte data or
silently triggers an OS-level download the moment the file is touched.
During a real OneDrive intake run (USS-TJR-MSN-0205E), 7 such placeholders
had to be identified and excluded by hand via ad-hoc symlink staging.
`cloud_detection.py` fixes this at the source, before a file is ever
manifested for transfer.

**Detection technique.** On macOS, a cloud-only placeholder has the
`SF_DATALESS` bit set in `os.stat(path, follow_symlinks=False).st_flags`
(`0x40000000`) — the same signal Finder and `mdls` use to show the
cloud-download badge. This holds even though the placeholder shares the real
file's exact name, unlike the older iCloud Drive convention of renaming a
not-yet-downloaded file to `.{filename}.icloud` in the same directory, which
is checked as a secondary/fallback signal. `st_flags` doesn't exist on
Linux, so the check degrades gracefully (`getattr(..., 'st_flags', 0)`)
rather than crashing on non-macOS platforms.

**Scan behaviour.** For every file that passes the existing ignore-pattern
check, `Collector.scan()` calls the availability check *before* hashing.
A `cloud_only` result is excluded from hashing/tracking by default and
reported in `cloud_only_files` (with a `cloud_only_count`) in the scan
payload. An `unavailable` result (`os.stat()` raised — broken symlink,
permission denied, vanished mid-scan — and no `.icloud` stub was found
either) is reported separately in `unavailable_files`
(`unavailable_count`) rather than folded into the generic `errors` list,
since "cloud-only, correctly skipped" and "unavailable, something's wrong"
are different signals worth distinguishing at a glance. The CLI prints a
stderr note when either count is nonzero.

**Operator override.** Setting `ignore.include_cloud_only: true` in
`config.yaml` hashes and tracks cloud-only files normally instead of
skipping them. This is a deliberate escape hatch, not a recommended
default — hashing a placeholder will likely trigger an OS-level download of
its real content the moment it's touched, which is a real tradeoff (time,
bandwidth, local disk usage) worth understanding before flipping it on.

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```
