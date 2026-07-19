#!/bin/bash
#
# START_BOT_WITH_RESEARCH.sh — Launch Slack bot with research delegator support
#
# This script:
# 1. Sets PYTHONPATH to include repo root and slack-bot directory
# 2. Validates research delegator imports (pre-flight check)
# 3. Starts the bot
#
# Usage:
#   chmod +x START_BOT_WITH_RESEARCH.sh
#   ./START_BOT_WITH_RESEARCH.sh
#
# Or from any directory:
#   /path/to/repo/START_BOT_WITH_RESEARCH.sh
#

set -e  # Exit on error

PROFILE="${1:-commander}"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Determine repo root (this script lives in slack-bot/, so go up one level)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}Starting Slack Bot with Research Delegator${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Repo root: $REPO_ROOT"
echo "Script: ${BASH_SOURCE[0]}"
echo "Profile: $PROFILE"
echo ""

# Set PYTHONPATH
# This allows imports from both repo root (core/) and slack-bot directory
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/slack-bot"
echo -e "${GREEN}✅ PYTHONPATH set:${NC}"
echo "   $PYTHONPATH"
echo ""

# Load environment variables from profile-specific .env if it exists
ENV_FILE="$REPO_ROOT/slack-bot/.env.${PROFILE}"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE="$REPO_ROOT/slack-bot/.env"
fi

if [ -f "$ENV_FILE" ]; then
    echo -e "${GREEN}Loading environment from ${ENV_FILE#$REPO_ROOT/}...${NC}"
    set -a
    source "$ENV_FILE"
    set +a
    echo -e "${GREEN}✅ environment loaded${NC}"
else
    echo -e "${YELLOW}⚠️  No profile .env found, using existing environment variables${NC}"
fi
echo ""

# Verify required environment variables
echo -e "${GREEN}Checking environment variables...${NC}"
REQUIRED_VARS=("SLACK_BOT_TOKEN" "SLACK_APP_TOKEN")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
        echo -e "${RED}❌ $var missing${NC}"
    else
        echo -e "${GREEN}✅ $var present${NC}"
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo ""
    echo -e "${RED}ERROR: Missing required environment variables:${NC}"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
echo "Set them in .env or export them:"
  echo "  export SLACK_BOT_TOKEN='xoxb-...'"
  echo "  export SLACK_APP_TOKEN='xapp-...'"
  exit 1
fi
echo ""

# Optional: Run pre-flight validation
if [ -f "$REPO_ROOT/verify_research_delegator.py" ]; then
    echo -e "${GREEN}Running research delegator pre-flight validation...${NC}"
    python3 "$REPO_ROOT/verify_research_delegator.py"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Validation passed${NC}"
    else
        echo -e "${RED}❌ Validation failed${NC}"
        echo "   Starting anyway (research commands may fail)"
    fi
    echo ""
else
    echo -e "${YELLOW}⚠️  verify_research_delegator.py not found, skipping pre-flight check${NC}"
    echo ""
fi

# Start the bot
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}Starting Slack bot from: $REPO_ROOT${NC}"
echo -e "${GREEN}Command: python3 slack-bot/app.py${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

cd "$REPO_ROOT"
python3 slack-bot/app.py

# If we get here, bot exited (normally or with error)
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Bot exited cleanly${NC}"
else
    echo -e "${RED}Bot exited with error code: $EXIT_CODE${NC}"
fi

exit $EXIT_CODE
