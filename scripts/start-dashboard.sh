#!/bin/bash
# Start the Self-Improvement Dashboard

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

echo "🚀 Starting Self-Improvement Dashboard..."
echo "📍 URL: http://localhost:8892"
echo "📊 Access the dashboard in your browser"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python3 scripts/self_improvement/dashboard.py
