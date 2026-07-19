#!/usr/bin/env bash
#
# run_knowledge_collection.sh — USS-TJR-MSN-0207A Mac Automation
#
# Chains the two already-built document-pipeline stages that previously
# required a human (or Claude) to invoke manually:
#
#   1. mac-collector  scan             (core/infrastructure/mac-collector)
#   2. mac-collector  export-manifest  (same tool, same DB)
#   3. vm-transfer    transfer         (core/infrastructure/vm-transfer)
#
# Intended to be run on a schedule by the LaunchAgent in this same directory
# (com.usstjr.knowledge-collection.plist), but is a normal shell script and
# can be run by hand for testing.
#
# WHAT THIS SCRIPT DELIBERATELY DOES NOT DO
# -------------------------------------------------------------------------
# - It does not decide which files are cloud-only placeholders. That is
#   handled inside mac-collector's Collector.scan() (see cloud_detection.py)
#   and is ON by default — this script never passes a flag that would
#   change that behaviour (e.g. it never sets ignore.include_cloud_only).
# - It does not decide which files are "eligible" content (ebooks, temp
#   files, etc). That is enforced server-side, on the VM, by
#   vm-processing's eligibility.py, after this script's job is done.
# - It does not invent a new Python environment strategy. It activates each
#   tool's own per-tool .venv, exactly as documented in that tool's README.
#
# Both properties above are *inherited* from the underlying tools by
# calling them with their default configuration. Nothing here re-implements
# or second-guesses either safeguard.
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — EDIT THESE for the deployment machine.
# ---------------------------------------------------------------------------

# Absolute path to the root of the USSTJROS repo checkout on this machine.
REPO_ROOT="${USSTJR_REPO_ROOT:-/Users/timjarden-ross/Documents/GitHub/USSTJROS}"

# Absolute paths to each tool's own virtualenv (per each tool's README:
# `cd core/infrastructure/<tool> && python3 -m venv .venv`). These are
# intentionally two separate venvs, matching each tool's documented setup —
# this script does not introduce a shared/combined venv.
MAC_COLLECTOR_VENV="${USSTJR_MAC_COLLECTOR_VENV:-$REPO_ROOT/core/infrastructure/mac-collector/.venv}"
VM_TRANSFER_VENV="${USSTJR_VM_TRANSFER_VENV:-$REPO_ROOT/core/infrastructure/vm-transfer/.venv}"

# Log file for this script's own chained run (timestamps, stage results,
# manifest path, skip/failure reasons). The LaunchAgent additionally
# captures raw stdout/stderr to its own StandardOutPath/StandardErrorPath —
# see the plist and README for how the two logs relate.
LOG_FILE="${USSTJR_KNOWLEDGE_COLLECTION_LOG:-$HOME/Library/Logs/starship-knowledge-collection.log}"

# Lock directory used to prevent overlapping runs (see "Locking" below).
LOCK_DIR="${USSTJR_KNOWLEDGE_COLLECTION_LOCK:-$HOME/Library/Application Support/starship-knowledge-collection/run.lock}"

# ---------------------------------------------------------------------------
# Derived paths (do not edit below this line for normal deployment).
# ---------------------------------------------------------------------------

MAC_COLLECTOR_DIR="$REPO_ROOT/core/infrastructure/mac-collector"
VM_TRANSFER_DIR="$REPO_ROOT/core/infrastructure/vm-transfer"

mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$(dirname "$LOCK_DIR")"

log() {
    printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" | tee -a "$LOG_FILE" >&2
}

# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------
# macOS ships BSD flock semantics differently across tool availability —
# there is no guarantee a GNU-compatible `flock(1)` binary exists on a given
# Mac (it is not part of the base OS; Homebrew's util-linux does not install
# a `flock` shim by default either). Rather than depend on an optional
# package, this uses the classic `mkdir`-as-lock pattern: `mkdir` is
# atomic at the filesystem level on every platform bash runs on, so exactly
# one concurrent invocation can win the race to create LOCK_DIR.
#
# A stale lock (owning process died without cleanup — e.g. `kill -9`, power
# loss) is detected by checking whether the PID recorded inside the lock
# directory is still alive; if not, the stale lock is reclaimed.

LOCK_PID_FILE="$LOCK_DIR/pid"

release_lock() {
    if [ "${LOCK_ACQUIRED:-0}" = "1" ]; then
        rm -rf "$LOCK_DIR"
    fi
}
trap release_lock EXIT

acquire_lock() {
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo "$$" > "$LOCK_PID_FILE"
        LOCK_ACQUIRED=1
        return 0
    fi

    # Lock dir already exists — check whether its owner is still alive.
    if [ -f "$LOCK_PID_FILE" ]; then
        local existing_pid
        existing_pid="$(cat "$LOCK_PID_FILE" 2>/dev/null || echo "")"
        if [ -n "$existing_pid" ] && kill -0 "$existing_pid" 2>/dev/null; then
            log "Another run (pid $existing_pid) holds the lock at $LOCK_DIR — exiting without starting."
            exit 0
        fi
    fi

    log "Found stale lock at $LOCK_DIR (owner not running) — reclaiming."
    rm -rf "$LOCK_DIR"
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo "$$" > "$LOCK_PID_FILE"
        LOCK_ACQUIRED=1
        return 0
    fi

    log "Failed to acquire lock at $LOCK_DIR after reclaim attempt — exiting."
    exit 1
}

LOCK_ACQUIRED=0
acquire_lock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

run_mac_collector() {
    # Args passed straight through to `python cli.py`. Runs inside a
    # subshell so `source .venv/bin/activate` and `cd` don't leak into the
    # parent shell / the vm-transfer stage below.
    (
        cd "$MAC_COLLECTOR_DIR"
        # shellcheck disable=SC1091
        source "$MAC_COLLECTOR_VENV/bin/activate"
        python cli.py "$@"
    )
}

run_vm_transfer() {
    (
        cd "$VM_TRANSFER_DIR"
        # shellcheck disable=SC1091
        source "$VM_TRANSFER_VENV/bin/activate"
        python cli.py "$@"
    )
}

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

log "=== Starting knowledge collection run (pid $$) ==="

if [ ! -x "$MAC_COLLECTOR_VENV/bin/python" ]; then
    log "ERROR: mac-collector venv not found at $MAC_COLLECTOR_VENV — follow core/infrastructure/mac-collector/README.md setup first."
    exit 1
fi
if [ ! -x "$VM_TRANSFER_VENV/bin/python" ]; then
    log "ERROR: vm-transfer venv not found at $VM_TRANSFER_VENV — follow core/infrastructure/vm-transfer/README.md setup first."
    exit 1
fi
if [ ! -f "$MAC_COLLECTOR_DIR/config.yaml" ]; then
    log "ERROR: $MAC_COLLECTOR_DIR/config.yaml not found — copy config.example.yaml and edit source paths first (see that tool's README)."
    exit 1
fi
if [ ! -f "$VM_TRANSFER_DIR/config.yaml" ]; then
    log "ERROR: $VM_TRANSFER_DIR/config.yaml not found — copy config.example.yaml and edit remote connection details first (see that tool's README)."
    exit 1
fi

# --- Stage 1: scan --------------------------------------------------------
# Deliberately no --source / --dry-run / config overrides: default config
# is what carries the cloud-aware collection default (include_cloud_only:
# false) and the ignore-pattern rules. Do not add flags here without
# re-reading mac-collector/README.md's "Cloud-aware collection" section.
log "Stage 1/3: mac-collector scan"
SCAN_OUTPUT_FILE="$(mktemp)"
trap 'rm -f "$SCAN_OUTPUT_FILE"; release_lock' EXIT
if ! run_mac_collector scan >"$SCAN_OUTPUT_FILE" 2>>"$LOG_FILE"; then
    log "Stage 1/3 FAILED: mac-collector scan exited non-zero (errors present — see log above and $SCAN_OUTPUT_FILE)."
    cat "$SCAN_OUTPUT_FILE" >> "$LOG_FILE"
    exit 1
fi
cat "$SCAN_OUTPUT_FILE" >> "$LOG_FILE"
log "Stage 1/3 OK: scan completed."

# --- Stage 2: export-manifest ---------------------------------------------
log "Stage 2/3: mac-collector export-manifest"
MANIFEST_OUTPUT_FILE="$(mktemp)"
trap 'rm -f "$SCAN_OUTPUT_FILE" "$MANIFEST_OUTPUT_FILE"; release_lock' EXIT
if ! run_mac_collector export-manifest >"$MANIFEST_OUTPUT_FILE" 2>>"$LOG_FILE"; then
    log "Stage 2/3 FAILED: mac-collector export-manifest exited non-zero."
    cat "$MANIFEST_OUTPUT_FILE" >> "$LOG_FILE"
    exit 1
fi
cat "$MANIFEST_OUTPUT_FILE" >> "$LOG_FILE"

# export-manifest prints a small JSON object to stdout:
#   {"output": "<path>", "file_count": N, "total_size_bytes": N}
# Parsed with python3 (already a hard dependency of both tools) rather than
# introducing a jq dependency this script would otherwise not need.
MANIFEST_PATH="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['output'])" "$MANIFEST_OUTPUT_FILE")"
FILE_COUNT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['file_count'])" "$MANIFEST_OUTPUT_FILE")"
log "Stage 2/3 OK: manifest written to $MANIFEST_PATH ($FILE_COUNT eligible files)."

if [ "$FILE_COUNT" -eq 0 ]; then
    log "Nothing to transfer (0 eligible files in manifest) — skipping vm-transfer stage."
    log "=== Run complete: nothing to transfer ==="
    exit 0
fi

# --- Stage 3: vm-transfer transfer -----------------------------------------
log "Stage 3/3: vm-transfer transfer --manifest $MANIFEST_PATH"
TRANSFER_OUTPUT_FILE="$(mktemp)"
trap 'rm -f "$SCAN_OUTPUT_FILE" "$MANIFEST_OUTPUT_FILE" "$TRANSFER_OUTPUT_FILE"; release_lock' EXIT
if ! run_vm_transfer transfer --manifest "$MANIFEST_PATH" >"$TRANSFER_OUTPUT_FILE" 2>>"$LOG_FILE"; then
    log "Stage 3/3 FAILED: vm-transfer transfer exited non-zero (one or more files failed — see log above)."
    cat "$TRANSFER_OUTPUT_FILE" >> "$LOG_FILE"
    exit 1
fi
cat "$TRANSFER_OUTPUT_FILE" >> "$LOG_FILE"
log "Stage 3/3 OK: transfer completed."

log "=== Run complete: $FILE_COUNT files transferred ==="

rm -f "$SCAN_OUTPUT_FILE" "$MANIFEST_OUTPUT_FILE" "$TRANSFER_OUTPUT_FILE"
exit 0
