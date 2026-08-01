#!/usr/bin/env bash
# Feature 027 - US4: PUT /api/v1/profiles/<id> agent-exclusive fields.
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
echo "US27-S4: PUT /profiles/<id> agent fields"
echo "========================================"

BEARER_TOKEN=$(get_oauth2_token)
[ -z "$BEARER_TOKEN" ] && { echo -e "${RED}✗ Failed to get OAuth2 token${NC}"; exit 1; }

OWNER_LOGIN_RESP=$(curl -s -X POST "$API_BASE/users/login" -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" \
    -d "{\"login\": \"${TEST_USER_OWNER:-owner@example.com}\", \"password\": \"${TEST_PASSWORD_OWNER:-SecurePass123!}\"}")
OWNER_SESSION=$(echo "$OWNER_LOGIN_RESP" | jq -r '.session_id // empty')
OWNER_COMPANY=$(echo "$OWNER_LOGIN_RESP" | jq -r '.user.default_company_id // empty')
[ -z "$OWNER_SESSION" ] && { echo -e "${RED}✗ Owner login failed${NC}"; exit 1; }

echo ""
echo "Step 1: Create an agent profile without creci"
TIMESTAMP=$(date +%s)
DOC=$(gen_valid_cpf "$(printf '%09d' $((TIMESTAMP % 1000000000)))")
AGENT_TYPE_ID=$(curl -s "$API_BASE/profile-types" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" | jq -r '.data[] | select(.code=="agent") | .id')
CREATE_RESPONSE=$(curl -s -X POST "$API_BASE/profiles" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{\"name\": \"US27S4 Agent $TIMESTAMP\", \"company_id\": $OWNER_COMPANY, \"document\": \"$DOC\", \"email\": \"us27s4_$TIMESTAMP@example.com\", \"birthdate\": \"1990-01-01\", \"profile_type_id\": $AGENT_TYPE_ID}")
PROFILE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.id // empty')
[ -z "$PROFILE_ID" ] && { echo -e "${RED}✗ Failed to create profile: $CREATE_RESPONSE${NC}"; exit 1; }

echo ""
echo "Step 2: PUT creci/bank fields -> 200, values applied"
UPDATE_RESPONSE=$(curl -s -X PUT "$API_BASE/profiles/$PROFILE_ID" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{\"creci\": \"CRECI-SP ${TIMESTAMP: -6}\", \"bank_name\": \"Itau\", \"bank_account\": \"1234-5\", \"pix_key\": \"us27s4_$TIMESTAMP@example.com\"}")
CRECI=$(echo "$UPDATE_RESPONSE" | jq -r '.agent.creci // empty')
if [ -n "$CRECI" ]; then echo -e "${GREEN}✓ creci updated: $CRECI${NC}";
else echo -e "${RED}✗ Update failed: $UPDATE_RESPONSE${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "Step 3: PUT malformed creci (< 4 chars) -> 400"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$API_BASE/profiles/$PROFILE_ID" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{\"creci\": \"ab\"}")
if [ "$STATUS" = "400" ]; then echo -e "${GREEN}✓ Malformed creci -> 400${NC}";
else echo -e "${RED}✗ Expected 400, got $STATUS${NC}"; FAILURES=$((FAILURES + 1)); fi

echo ""
echo "Step 4: test_update_profile_creci_conflict_returns_409_with_rollback (FR5.4)"
# Second agent profile owning a *different* CRECI...
DOC2=$(gen_valid_cpf "$(printf '%09d' $(( (TIMESTAMP + 31) % 1000000000 )))")
CREATE2=$(curl -s -X POST "$API_BASE/profiles" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{\"name\": \"US27S4 Agent B $TIMESTAMP\", \"company_id\": $OWNER_COMPANY, \"document\": \"$DOC2\", \"email\": \"us27s4b_$TIMESTAMP@example.com\", \"birthdate\": \"1990-01-01\", \"profile_type_id\": $AGENT_TYPE_ID}")
PROFILE2_ID=$(echo "$CREATE2" | jq -r '.id // empty')
[ -z "$PROFILE2_ID" ] && { echo -e "${RED}✗ Failed to create second profile: $CREATE2${NC}"; FAILURES=$((FAILURES + 1)); }

CONFLICT_CRECI="CRECI-RJ ${TIMESTAMP: -6}"
UPD2=$(curl -s -X PUT "$API_BASE/profiles/$PROFILE2_ID" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{\"creci\": \"$CONFLICT_CRECI\"}")
if [ "$(echo "$UPD2" | jq -r '.agent.creci // empty')" = "" ]; then
    echo -e "${RED}✗ Could not seed the conflicting CRECI on profile B: $UPD2${NC}"; FAILURES=$((FAILURES + 1))
fi

# Baseline of profile A's own mutable fields, so we can prove the rollback
# covers the WHOLE request (profile.write happens BEFORE the agent.write
# that raises), not just the failed agent write.
BEFORE=$(curl -s "$API_BASE/profiles/$PROFILE_ID" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
NAME_BEFORE=$(echo "$BEFORE" | jq -r '.name')
BANK_BEFORE=$(echo "$BEFORE" | jq -r '.agent.bank_name')
CRECI_BEFORE=$(echo "$BEFORE" | jq -r '.agent.creci')

STATUS=$(curl -s -o /tmp/us27s4_conflict.json -w "%{http_code}" -X PUT "$API_BASE/profiles/$PROFILE_ID" \
    -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{\"name\": \"SHOULD NOT PERSIST $TIMESTAMP\", \"bank_name\": \"SHOULD NOT PERSIST\", \"creci\": \"$CONFLICT_CRECI\"}")
if [ "$STATUS" = "409" ]; then
    echo -e "${GREEN}✓ Duplicate CRECI -> 409 ($(jq -r '.message // .error' /tmp/us27s4_conflict.json))${NC}"
else
    echo -e "${RED}✗ Expected 409, got $STATUS: $(cat /tmp/us27s4_conflict.json)${NC}"; FAILURES=$((FAILURES + 1))
fi
rm -f /tmp/us27s4_conflict.json

AFTER=$(curl -s "$API_BASE/profiles/$PROFILE_ID" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
NAME_AFTER=$(echo "$AFTER" | jq -r '.name')
BANK_AFTER=$(echo "$AFTER" | jq -r '.agent.bank_name')
CRECI_AFTER=$(echo "$AFTER" | jq -r '.agent.creci')
if [ "$NAME_AFTER" = "$NAME_BEFORE" ] && [ "$BANK_AFTER" = "$BANK_BEFORE" ] && [ "$CRECI_AFTER" = "$CRECI_BEFORE" ]; then
    echo -e "${GREEN}✓ Rollback covered the whole request: name/bank_name/creci all unchanged${NC}"
else
    echo -e "${RED}✗ Partial write committed -- name '$NAME_BEFORE'->'$NAME_AFTER', bank '$BANK_BEFORE'->'$BANK_AFTER', creci '$CRECI_BEFORE'->'$CRECI_AFTER'${NC}"
    FAILURES=$((FAILURES + 1))
fi

echo ""
echo "Step 5: Legacy PUT /api/v1/agents/<id> -- covered by test_us27_s5 once Task 9 removes it"

echo ""
echo "========================================"
if [ "$FAILURES" -eq 0 ]; then echo -e "${GREEN}US27-S4: ALL CHECKS PASSED${NC}"; exit 0;
else echo -e "${RED}US27-S4: $FAILURES CHECK(S) FAILED${NC}"; exit 1; fi
