#!/usr/bin/env bash
# Feature 027 - US2: POST /api/v1/profiles/<id>/reactivate
#
# Same deviations from the task-10 brief as test_us27_s1 (see that file's
# header for the full rationale): X-Openerp-Session-Id (not X-Session-Id),
# company_id derived from login response (not hardcoded 1), and a
# checksum-valid CPF generator for the document field.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/get_oauth2_token.sh"

if [ -f "$SCRIPT_DIR/../18.0/.env" ]; then
    source "$SCRIPT_DIR/../18.0/.env"
fi

BASE_URL="${BASE_URL:-http://localhost:8069}"
API_BASE="$BASE_URL/api/v1"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
FAILURES=0

gen_valid_cpf() {
    local base="$1"
    local d
    local sum1=0 sum2=0
    local weights1=(10 9 8 7 6 5 4 3 2)
    for i in 0 1 2 3 4 5 6 7 8; do
        d=${base:$i:1}
        sum1=$((sum1 + d * ${weights1[$i]}))
    done
    local dv1=$(( (sum1 * 10) % 11 ))
    [ "$dv1" -eq 10 ] && dv1=0
    local base10="${base}${dv1}"
    local weights2=(11 10 9 8 7 6 5 4 3 2)
    for i in 0 1 2 3 4 5 6 7 8 9; do
        d=${base10:$i:1}
        sum2=$((sum2 + d * ${weights2[$i]}))
    done
    local dv2=$(( (sum2 * 10) % 11 ))
    [ "$dv2" -eq 10 ] && dv2=0
    echo "${base10}${dv2}"
}

echo "========================================"
echo "US27-S2: POST /profiles/<id>/reactivate"
echo "========================================"

BEARER_TOKEN=$(get_oauth2_token)
[ -z "$BEARER_TOKEN" ] && { echo -e "${RED}✗ Failed to get OAuth2 token${NC}"; exit 1; }

login_user() {
    local response=$(curl -s -X POST "$API_BASE/users/login" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $BEARER_TOKEN" \
        -d "{\"login\": \"$1\", \"password\": \"$2\"}")
    local session_id=$(echo "$response" | jq -r '.session_id // empty')
    local company_id=$(echo "$response" | jq -r '.user.default_company_id // empty')
    echo "${session_id}|${company_id}"
}

assert_status() {
    if [ "$3" = "$2" ]; then echo -e "${GREEN}✓ $1 -> $3${NC}";
    else echo -e "${RED}✗ $1 -> expected $2, got $3${NC}"; FAILURES=$((FAILURES + 1)); fi
}

OWNER_LOGIN=$(login_user "${TEST_USER_OWNER:-owner@example.com}" "${TEST_PASSWORD_OWNER:-SecurePass123!}")
MANAGER_LOGIN=$(login_user "${TEST_USER_MANAGER:-manager@example.com}" "${TEST_PASSWORD_MANAGER:-SecurePass123!}")
OWNER_SESSION="${OWNER_LOGIN%%|*}"; OWNER_COMPANY="${OWNER_LOGIN##*|}"
MANAGER_SESSION="${MANAGER_LOGIN%%|*}"
[ -z "$OWNER_SESSION" ] && { echo -e "${RED}✗ Owner login failed${NC}"; exit 1; }

echo ""
echo "Step 1: Create + deactivate a test profile as Owner (setup)"
TIMESTAMP=$(date +%s)
DOC=$(gen_valid_cpf "$(printf '%09d' $((TIMESTAMP % 1000000000)))")
TENANT_TYPE_ID=$(curl -s "$API_BASE/profile-types" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" | jq -r '.data[] | select(.code=="tenant") | .id')
CREATE_RESPONSE=$(curl -s -X POST "$API_BASE/profiles" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{\"name\": \"US27S2 Tenant $TIMESTAMP\", \"company_id\": $OWNER_COMPANY, \"document\": \"$DOC\", \"email\": \"us27s2_$TIMESTAMP@example.com\", \"birthdate\": \"1990-01-01\", \"profile_type_id\": $TENANT_TYPE_ID}")
PROFILE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.id // empty')
[ -z "$PROFILE_ID" ] && { echo -e "${RED}✗ Failed to create profile: $CREATE_RESPONSE${NC}"; exit 1; }
curl -s -X DELETE "$API_BASE/profiles/$PROFILE_ID" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" > /dev/null
echo -e "${GREEN}✓ Profile $PROFILE_ID created and deactivated${NC}"

echo ""
echo "Step 2: Manager attempts reactivate -> expect 403"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/profiles/$PROFILE_ID/reactivate" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $MANAGER_SESSION")
assert_status "Manager reactivate" "403" "$STATUS"

echo ""
echo "Step 3: Owner reactivates -> expect 200, data.active=true"
RESPONSE=$(curl -s -X POST "$API_BASE/profiles/$PROFILE_ID/reactivate" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
ACTIVE=$(echo "$RESPONSE" | jq -r '.data.active')
if [ "$ACTIVE" = "true" ]; then echo -e "${GREEN}✓ Reactivated: active=true${NC}";
else echo -e "${RED}✗ Reactivate failed: $RESPONSE${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "Step 4: Reactivating an already-active profile -> expect 400"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/profiles/$PROFILE_ID/reactivate" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
assert_status "Re-reactivate already-active" "400" "$STATUS"

echo ""
echo "Step 5: Non-existent profile id -> expect 404"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/profiles/99999999/reactivate" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
assert_status "Nonexistent profile reactivate" "404" "$STATUS"

echo ""
echo "========================================"
if [ "$FAILURES" -eq 0 ]; then echo -e "${GREEN}US27-S2: ALL CHECKS PASSED${NC}"; exit 0;
else echo -e "${RED}US27-S2: $FAILURES CHECK(S) FAILED${NC}"; exit 1; fi
