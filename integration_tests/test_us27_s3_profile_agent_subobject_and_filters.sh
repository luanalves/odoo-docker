#!/usr/bin/env bash
# Feature 027 - US3: GET /profiles + GET /profiles/<id> agent sub-object
# parity, creci_number/creci_state filters, and legacy GET /agents removed.
#
# Same deviations from the task-10 brief as test_us27_s1 (see that file's
# header for the full rationale): X-Openerp-Session-Id (not X-Session-Id),
# company_id derived from login response (not hardcoded 1), and a
# checksum-valid CPF generator for the document field.
#
# Additional deviation: creci uses the last 6 digits of TIMESTAMP, not the
# full 10-digit epoch timestamp -- CreciValidator.normalize() (services/
# creci_validator.py) requires the numeric part to be 4-8 digits; a raw
# epoch timestamp (10 digits) fails that check regardless of separator
# style.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/get_oauth2_token.sh"
if [ -f "$SCRIPT_DIR/../18.0/.env" ]; then source "$SCRIPT_DIR/../18.0/.env"; fi

BASE_URL="${BASE_URL:-http://localhost:8069}"
API_BASE="$BASE_URL/api/v1"
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'; FAILURES=0

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
echo "US27-S3: GET /profiles agent sub-object + creci filters"
echo "========================================"

BEARER_TOKEN=$(get_oauth2_token)
[ -z "$BEARER_TOKEN" ] && { echo -e "${RED}✗ Failed to get OAuth2 token${NC}"; exit 1; }

OWNER_LOGIN_RESP=$(curl -s -X POST "$API_BASE/users/login" -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" \
    -d "{\"login\": \"${TEST_USER_OWNER:-owner@example.com}\", \"password\": \"${TEST_PASSWORD_OWNER:-SecurePass123!}\"}")
OWNER_SESSION=$(echo "$OWNER_LOGIN_RESP" | jq -r '.session_id // empty')
OWNER_COMPANY=$(echo "$OWNER_LOGIN_RESP" | jq -r '.user.default_company_id // empty')
[ -z "$OWNER_SESSION" ] && { echo -e "${RED}✗ Owner login failed${NC}"; exit 1; }

echo ""
echo "Step 1: Create an agent profile with creci"
TIMESTAMP=$(date +%s)
DOC=$(gen_valid_cpf "$(printf '%09d' $((TIMESTAMP % 1000000000)))")
AGENT_TYPE_ID=$(curl -s "$API_BASE/profile-types" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" | jq -r '.data[] | select(.code=="agent") | .id')
CREATE_RESPONSE=$(curl -s -X POST "$API_BASE/profiles" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{\"name\": \"US27S3 Agent $TIMESTAMP\", \"company_id\": $OWNER_COMPANY, \"document\": \"$DOC\", \"email\": \"us27s3_$TIMESTAMP@example.com\", \"birthdate\": \"1990-01-01\", \"profile_type_id\": $AGENT_TYPE_ID, \"creci\": \"CRECI-SP ${TIMESTAMP: -6}\"}")
PROFILE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.id // empty')
[ -z "$PROFILE_ID" ] && { echo -e "${RED}✗ Failed to create profile: $CREATE_RESPONSE${NC}"; exit 1; }
echo -e "${GREEN}✓ Profile $PROFILE_ID created${NC}"

echo ""
echo "Step 2: GET /profiles/<id> -> agent sub-object present with creci"
GET_RESPONSE=$(curl -s "$API_BASE/profiles/$PROFILE_ID" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
AGENT_CRECI=$(echo "$GET_RESPONSE" | jq -r '.agent.creci // empty')
if [ -n "$AGENT_CRECI" ]; then echo -e "${GREEN}✓ agent.creci present: $AGENT_CRECI${NC}";
else echo -e "${RED}✗ agent sub-object missing: $GET_RESPONSE${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "Step 3: GET /profiles?company_ids=<owner company>&creci_number=<n> -> matches"
CRECI_NUMBER=$(echo "$AGENT_CRECI" | grep -oE '[0-9]+$')
LIST_RESPONSE=$(curl -s "$API_BASE/profiles?company_ids=$OWNER_COMPANY&creci_number=$CRECI_NUMBER" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
FOUND=$(echo "$LIST_RESPONSE" | jq --arg pid "$PROFILE_ID" '[.data[] | select((.id|tostring)==$pid)] | length')
if [ "$FOUND" = "1" ]; then echo -e "${GREEN}✓ creci_number filter matched${NC}";
else echo -e "${RED}✗ creci_number filter did not match: $LIST_RESPONSE${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "Step 4: GET /profiles?company_ids=<owner company>&creci_state=ZZ -> empty (no error)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE/profiles?company_ids=$OWNER_COMPANY&creci_state=ZZ" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
if [ "$STATUS" = "200" ]; then echo -e "${GREEN}✓ Unmatched creci_state returns 200 (empty list, not an error)${NC}";
else echo -e "${RED}✗ Expected 200, got $STATUS${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "========================================"
if [ "$FAILURES" -eq 0 ]; then echo -e "${GREEN}US27-S3: ALL CHECKS PASSED${NC}"; exit 0;
else echo -e "${RED}US27-S3: $FAILURES CHECK(S) FAILED${NC}"; exit 1; fi
