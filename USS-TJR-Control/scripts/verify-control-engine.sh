#!/bin/bash

################################################################################
# Control Engine Startup Health Check
#
# Verifies all Control Engine API endpoints are responding after startup
#
# Usage:
#   ./verify-control-engine.sh [options]
#
# Options:
#   --url URL          Control Engine URL (default: http://localhost:8888)
#   --timeout N        HTTP timeout in seconds (default: 5)
#   --wait N           Wait N seconds before checking (default: 3)
#   --retries N        Retry failed checks N times (default: 3)
#
# Exit Codes:
#   0 = All checks passed
#   1 = One or more checks failed
#   2 = Unable to connect to Control Engine
#
# Author: STARFLEET COMMAND ENGINEERING
# Mission: M-20260609-000000
# Date: June 8, 2026
################################################################################

set -o pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

CONTROL_ENGINE_URL="${CONTROL_ENGINE_URL:-http://localhost:8888}"
TIMEOUT=5
WAIT_TIME=3
MAX_RETRIES=3
VERBOSE=false

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_TOTAL=0

# ============================================================================
# ARGUMENT PARSING
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --url)
            CONTROL_ENGINE_URL="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --wait)
            WAIT_TIME="$2"
            shift 2
            ;;
        --retries)
            MAX_RETRIES="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
    ((CHECKS_PASSED++))
}

log_failure() {
    echo -e "${RED}✗${NC} $1"
    ((CHECKS_FAILED++))
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

check_endpoint() {
    local endpoint=$1
    local description=$2
    local retry_count=0

    ((CHECKS_TOTAL++))

    while [ $retry_count -lt $MAX_RETRIES ]; do
        if [ $retry_count -gt 0 ]; then
            log_warning "Retrying $endpoint (attempt $((retry_count + 1))/$MAX_RETRIES)"
        fi

        local response=$(curl -s -w "\n%{http_code}" \
            --max-time "$TIMEOUT" \
            "$CONTROL_ENGINE_URL$endpoint" 2>/dev/null)

        local http_code=$(echo "$response" | tail -n1)
        local body=$(echo "$response" | head -n-1)

        if [ -z "$http_code" ]; then
            ((retry_count++))
            sleep 1
            continue
        fi

        if [ "$http_code" = "200" ]; then
            if [ "$VERBOSE" = true ]; then
                log_success "$description (HTTP $http_code)"
                # echo "  Response: $(echo "$body" | head -c 100)..."
            else
                log_success "$description"
            fi
            return 0
        else
            ((retry_count++))
            sleep 1
        fi
    done

    log_failure "$description (HTTP $http_code after $MAX_RETRIES attempts)"
    return 1
}

# ============================================================================
# STARTUP VERIFICATION
# ============================================================================

main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║         Control Engine Startup Health Check                    ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    log_info "Target: $CONTROL_ENGINE_URL"
    log_info "Waiting ${WAIT_TIME}s for startup..."
    sleep "$WAIT_TIME"
    echo ""

    # Basic connectivity check
    log_info "Checking connectivity..."
    if ! timeout "$TIMEOUT" bash -c "echo >/dev/tcp/${CONTROL_ENGINE_URL#http*://}/8888" 2>/dev/null; then
        log_failure "Cannot connect to Control Engine at $CONTROL_ENGINE_URL"
        echo ""
        echo "Make sure Control Engine is running:"
        echo "  cd ~/Documents/GitHub/USSTJROS/core/command-centre"
        echo "  python3 control_engine.py"
        echo ""
        return 2
    fi
    log_success "Connected to Control Engine"
    echo ""

    # Check API endpoints
    log_info "Checking API endpoints..."
    check_endpoint "/api/health" "GET /api/health"
    check_endpoint "/api/services/status" "GET /api/services/status"
    check_endpoint "/api/missions/active" "GET /api/missions/active"
    check_endpoint "/api/missions/recent" "GET /api/missions/recent"
    check_endpoint "/api/missions/this-week" "GET /api/missions/this-week"
    check_endpoint "/api/dashboard/summary" "GET /api/dashboard/summary"
    check_endpoint "/api" "GET /api (Info endpoint)"
    check_endpoint "/healthz" "GET /healthz (Health check)"
    echo ""

    # Summary
    echo "╔════════════════════════════════════════════════════════════════╗"
    printf "║ Results: "
    printf "${GREEN}%d passed${NC}" "$CHECKS_PASSED"
    printf ", "
    if [ $CHECKS_FAILED -eq 0 ]; then
        printf "${GREEN}0 failed${NC}"
    else
        printf "${RED}%d failed${NC}" "$CHECKS_FAILED"
    fi
    printf " (of %d checks)%*s║\n" "$CHECKS_TOTAL" $((60 - ${#CHECKS_PASSED} - ${#CHECKS_FAILED} - 28)) ""
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    if [ $CHECKS_FAILED -eq 0 ]; then
        echo -e "${GREEN}✓ All checks passed!${NC}"
        echo ""
        echo "Control Engine is ready for use."
        echo ""
        echo "Access the following:"
        echo "  • API Health: $CONTROL_ENGINE_URL/api/health"
        echo "  • Status Page: http://localhost:8081/status.html"
        echo "  • Service Widget: http://localhost:8081/service-health-widget.html"
        echo ""
        return 0
    else
        echo -e "${RED}✗ $CHECKS_FAILED check(s) failed${NC}"
        echo ""
        echo "Troubleshooting steps:"
        echo "  1. Check Control Engine is running: ps aux | grep control_engine"
        echo "  2. Check logs: tail -f USS-TJR-Control/logs/control-engine.log"
        echo "  3. Verify USS-TJR-Control services are available"
        echo "  4. Check network connectivity: netstat -an | grep 8888"
        echo ""
        return 1
    fi
}

# ============================================================================
# MAIN
# ============================================================================

main
exit $?
