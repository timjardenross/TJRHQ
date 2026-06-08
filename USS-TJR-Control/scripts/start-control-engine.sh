#!/bin/bash

# USS TJR Control Engine Startup Script
# Starts the Control Engine Flask API on localhost:8888
#
# Purpose:
#   Launch the Control Engine HTTP API for service orchestration and health monitoring
#
# Returns:
#   0 = successful startup
#   1 = startup failed

set -e

# ============================================================================
# CONFIGURATION
# ============================================================================

# Determine script location and repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROL_DECK_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$(dirname "$CONTROL_DECK_DIR")")"

# Service configuration
CONTROL_ENGINE_DIR="$REPO_ROOT/core/command-centre"
CONTROL_ENGINE_FILE="$CONTROL_ENGINE_DIR/control_engine.py"
LOG_DIR="$CONTROL_DECK_DIR/logs"
LOG_FILE="$LOG_DIR/control-engine.log"

# Python environment
PYTHON_CMD="python3"
VENV_ACTIVATE="$REPO_ROOT/slack-bot/.venv/bin/activate"

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

echo "Starting Control Engine..."
echo "  Script: $SCRIPT_DIR/$(basename "$0")"
echo "  Repo root: $REPO_ROOT"
echo "  Control Engine: $CONTROL_ENGINE_FILE"
echo "  Log file: $LOG_FILE"

# Check if control_engine.py exists
if [ ! -f "$CONTROL_ENGINE_FILE" ]; then
    echo "❌ Error: control_engine.py not found at $CONTROL_ENGINE_FILE"
    exit 1
fi

# Check if we have Python 3
if ! command -v $PYTHON_CMD &> /dev/null; then
    echo "❌ Error: $PYTHON_CMD not found"
    exit 1
fi

# Create log directory if needed
mkdir -p "$LOG_DIR"

# ============================================================================
# STARTUP
# ============================================================================

echo "Activating virtual environment..."

# Activate venv and launch Control Engine
(
    if [ -f "$VENV_ACTIVATE" ]; then
        source "$VENV_ACTIVATE"
        echo "✅ Virtual environment activated"
    else
        echo "⚠️  Virtual environment not found at $VENV_ACTIVATE"
        echo "   Proceeding without venv (may fail if dependencies missing)"
    fi

    echo "Launching Control Engine on localhost:8888..."
    cd "$CONTROL_ENGINE_DIR"
    $PYTHON_CMD control_engine.py
) 2>&1 | tee -a "$LOG_FILE"

echo "✅ Control Engine started (see logs at $LOG_FILE)"
exit 0
