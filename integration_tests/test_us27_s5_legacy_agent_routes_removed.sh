#!/usr/bin/env bash
# Feature 027 - Task 9: confirm the 5 legacy /api/v1/agents routes are gone.
# Run this ONLY after Task 9 has been implemented and the module upgraded.

set -e

BASE_URL="${BASE_URL:-http://localhost:8069}"
API_BASE="$BASE_URL/api/v1"
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'; FAILURES=0

echo "========================================"
echo "US27-S5: Legacy /api/v1/agents routes removed"
echo "========================================"

check_404() {
    local label="$1" method="$2" path="$3"
    local status=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$API_BASE$path")
    if [ "$status" = "404" ]; then echo -e "${GREEN}✓ $label -> 404${NC}";
    else echo -e "${RED}✗ $label -> expected 404, got $status${NC}"; FAILURES=$((FAILURES + 1)); fi
}

check_404 "GET /agents" GET "/agents"
check_404 "GET /agents/1" GET "/agents/1"
check_404 "PUT /agents/1" PUT "/agents/1"
check_404 "POST /agents/1/deactivate" POST "/agents/1/deactivate"
check_404 "POST /agents/1/reactivate" POST "/agents/1/reactivate"

echo ""
echo "========================================"
if [ "$FAILURES" -eq 0 ]; then echo -e "${GREEN}US27-S5: ALL CHECKS PASSED${NC}"; exit 0;
else echo -e "${RED}US27-S5: $FAILURES CHECK(S) FAILED${NC}"; exit 1; fi
