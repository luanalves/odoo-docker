#!/usr/bin/env bash
# Feature 027 - US1: DELETE /api/v1/profiles/<id> authorization matrix
# owner/admin authorized for ANY profile_type; manager/director/others 403.
#
# Deviations from the task-10 brief's literal transcription (all required to
# make the script actually pass against the live stack -- see task-10-report.md):
#   - Session header is X-Openerp-Session-Id, not X-Session-Id (confirmed
#     against thedevkitchen_apigateway/middleware.py; the brief's header name
#     is silently ignored by require_session and yields 401 for every call).
#   - company_id is derived per-user from the login response
#     (user.default_company_id) instead of hardcoded to 1 -- company_id=1
#     ("My Company") is not in any seed test user's company_ids (they all
#     belong to company 5, "Imobiliária Seed"), so hardcoding 1 would 403 on
#     profile creation before the authz matrix under test ever runs.
#   - document uses a real CPF-checksum generator (gen_valid_cpf) instead of
#     a raw modulo of the timestamp -- profile creation validates the CPF
#     checksum server-side, and a random 11-digit number passes only ~1% of
#     the time.
#   - Step 7 was originally written to verify deactivation via
#     GET /profiles?...&document=<doc> (list endpoint) instead of
#     GET /profiles/<id>, because the single-record GET did not pass
#     active_test=False (unlike list_profiles), so it 404'd on a just-
#     deactivated profile. That bug is now fixed (get_profile.with_context
#     (active_test=False), see profile_api.py) as a follow-up bugfix task
#     inserted between Task 10 and Task 11 -- Step 7 now asserts directly
#     against GET /profiles/<id>, which is the more direct check.
#   - Step 2 creates a 'prospector' profile, not 'tenant' as the brief says
#     -- PROFILE_CREATION_MATRIX in profile_api.py (pre-existing, Feature
#     009/026) restricts Manager to
#     agent/prospector/receptionist/financial/legal; Manager cannot create
#     'tenant' (owner-only). 'prospector' is still a non-agent type, so the
#     step's intent (proving the deactivate/reactivate matrix isn't
#     agent-specific) is preserved.

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

# Generates a checksum-valid Brazilian CPF from a 9-digit base (see header
# note above -- the API validates the two CPF check digits server-side).
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
echo "US27-S1: DELETE /profiles/<id> authorization"
echo "========================================"

BEARER_TOKEN=$(get_oauth2_token)
if [ -z "$BEARER_TOKEN" ]; then
    echo -e "${RED}✗ Failed to get OAuth2 token${NC}"
    exit 1
fi

login_user() {
    local email="$1"
    local password="$2"
    local response=$(curl -s -X POST "$API_BASE/users/login" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $BEARER_TOKEN" \
        -d "{\"login\": \"$email\", \"password\": \"$password\"}")
    local session_id=$(echo "$response" | jq -r '.session_id // empty')
    local company_id=$(echo "$response" | jq -r '.user.default_company_id // empty')
    if [ -z "$session_id" ]; then echo ""; return 1; fi
    echo "${session_id}|${company_id}"
}

assert_status() {
    local label="$1" expected="$2" actual="$3"
    if [ "$actual" = "$expected" ]; then
        echo -e "${GREEN}✓ ${label} -> ${actual}${NC}"
    else
        echo -e "${RED}✗ ${label} -> expected ${expected}, got ${actual}${NC}"
        FAILURES=$((FAILURES + 1))
    fi
}

echo ""
echo "Step 1: Logging in as owner, manager, director, agent..."
OWNER_LOGIN=$(login_user "${TEST_USER_OWNER:-owner@example.com}" "${TEST_PASSWORD_OWNER:-SecurePass123!}")
MANAGER_LOGIN=$(login_user "${TEST_USER_MANAGER:-manager@example.com}" "${TEST_PASSWORD_MANAGER:-SecurePass123!}")
DIRECTOR_LOGIN=$(login_user "${TEST_USER_DIRECTOR:-director@example.com}" "${TEST_PASSWORD_DIRECTOR:-SecurePass123!}")
AGENT_LOGIN=$(login_user "${TEST_USER_AGENT:-agent@example.com}" "${TEST_PASSWORD_AGENT:-SecurePass123!}")

OWNER_SESSION="${OWNER_LOGIN%%|*}"; OWNER_COMPANY="${OWNER_LOGIN##*|}"
MANAGER_SESSION="${MANAGER_LOGIN%%|*}"; MANAGER_COMPANY="${MANAGER_LOGIN##*|}"
DIRECTOR_SESSION="${DIRECTOR_LOGIN%%|*}"; DIRECTOR_COMPANY="${DIRECTOR_LOGIN##*|}"
AGENT_SESSION="${AGENT_LOGIN%%|*}"; AGENT_COMPANY="${AGENT_LOGIN##*|}"

for name in OWNER MANAGER DIRECTOR AGENT; do
    varname="${name}_SESSION"
    if [ -z "${!varname}" ]; then
        echo -e "${RED}✗ ${name} login failed -- check TEST_USER_${name}/TEST_PASSWORD_${name} in 18.0/.env${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ All 4 sessions obtained${NC}"

echo ""
echo "Step 2: Manager creates a throwaway 'prospector' profile to deactivate (non-agent type, proves the matrix isn't agent-specific)..."
TIMESTAMP=$(date +%s)
DOC=$(gen_valid_cpf "$(printf '%09d' $((TIMESTAMP % 1000000000)))")
CREATE_RESPONSE=$(curl -s -X POST "$API_BASE/profiles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -H "X-Openerp-Session-Id: $MANAGER_SESSION" \
    -d "{\"name\": \"US27S1 Prospector $TIMESTAMP\", \"company_id\": $MANAGER_COMPANY, \"document\": \"$DOC\", \"email\": \"us27s1_$TIMESTAMP@example.com\", \"birthdate\": \"1990-01-01\", \"profile_type_id\": $(curl -s "$API_BASE/profile-types" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $MANAGER_SESSION" | jq -r '.data[] | select(.code=="prospector") | .id')}")
PROFILE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.id // empty')
if [ -z "$PROFILE_ID" ]; then
    echo -e "${RED}✗ Failed to create test profile: $CREATE_RESPONSE${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Test profile created: id=$PROFILE_ID${NC}"

echo ""
echo "Step 3: Manager attempts DELETE -> expect 403 (regression: manager was authorized pre-027)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_ID" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $MANAGER_SESSION")
assert_status "Manager DELETE" "403" "$STATUS"

echo ""
echo "Step 4: Director attempts DELETE -> expect 403"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_ID" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $DIRECTOR_SESSION")
assert_status "Director DELETE" "403" "$STATUS"

echo ""
echo "Step 5: Agent attempts DELETE (own or others' profile) -> expect 403"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_ID" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $AGENT_SESSION")
assert_status "Agent DELETE" "403" "$STATUS"

echo ""
echo "Step 6: Owner performs DELETE -> expect 200"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_ID" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
assert_status "Owner DELETE" "200" "$STATUS"

echo ""
echo "Step 7: GET /profiles/<id> directly to confirm active=false"
GET_RESPONSE=$(curl -s "$API_BASE/profiles/$PROFILE_ID" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
ACTIVE=$(echo "$GET_RESPONSE" | jq -r '.active')
if [ "$ACTIVE" = "false" ]; then
    echo -e "${GREEN}✓ Profile is inactive${NC}"
else
    echo -e "${RED}✗ Profile still active: $GET_RESPONSE${NC}"
    FAILURES=$((FAILURES + 1))
fi

echo ""
echo "Step 8: test_delete_already_inactive_profile_returns_400 -- Owner DELETEs the same profile again"
# Final-review I-6: delete_profile now looks the profile up with
# active_test=False, so its "Profile is already inactive" guard is
# reachable. Before that fix Odoo's implicit active=True filter hid the
# row and this second DELETE answered 404, making the 400 branch dead code.
DELETE2_BODY=$(curl -s -o /tmp/us27s1_delete2.json -w "%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_ID" \
    -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
assert_status "Owner second DELETE (already inactive)" "400" "$DELETE2_BODY"
MSG=$(jq -r '.message // .error // empty' /tmp/us27s1_delete2.json 2>/dev/null)
if echo "$MSG" | grep -qi "already inactive"; then
    echo -e "${GREEN}✓ Message is the 'already inactive' guard, not a generic 404: $MSG${NC}"
else
    echo -e "${RED}✗ Expected 'Profile is already inactive', got: $MSG${NC}"
    FAILURES=$((FAILURES + 1))
fi
rm -f /tmp/us27s1_delete2.json

echo ""
echo "Step 9: test_multitenancy_isolation_delete_profile -- Owner A DELETEs a Company B profile"
# ADR-008 anti-enumeration: cross-company access is 404, never 403 --
# a 403 would confirm the id exists in another tenant.
OWNER_B_LOGIN=$(login_user "${TEST_USER_OWNER_B:-cap.owner.b@example.com}" "${TEST_PASSWORD_OWNER_B:-seed123}")
OWNER_B_SESSION="${OWNER_B_LOGIN%%|*}"; OWNER_B_COMPANY="${OWNER_B_LOGIN##*|}"
if [ -z "$OWNER_B_SESSION" ]; then
    echo -e "${RED}✗ Owner B login failed -- check TEST_USER_OWNER_B/TEST_PASSWORD_OWNER_B in 18.0/.env${NC}"
    FAILURES=$((FAILURES + 1))
elif [ "$OWNER_B_COMPANY" = "$OWNER_COMPANY" ]; then
    echo -e "${RED}✗ Owner B is in the same company ($OWNER_B_COMPANY) as Owner A -- cannot test isolation${NC}"
    FAILURES=$((FAILURES + 1))
else
    DOC_B=$(gen_valid_cpf "$(printf '%09d' $(( (TIMESTAMP + 7) % 1000000000 )))")
    TENANT_TYPE_ID_B=$(curl -s "$API_BASE/profile-types" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_B_SESSION" | jq -r '.data[] | select(.code=="tenant") | .id')
    CREATE_B=$(curl -s -X POST "$API_BASE/profiles" \
        -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_B_SESSION" \
        -d "{\"name\": \"US27S1 CompanyB $TIMESTAMP\", \"company_id\": $OWNER_B_COMPANY, \"document\": \"$DOC_B\", \"email\": \"us27s1b_$TIMESTAMP@example.com\", \"birthdate\": \"1990-01-01\", \"profile_type_id\": $TENANT_TYPE_ID_B}")
    PROFILE_B_ID=$(echo "$CREATE_B" | jq -r '.id // empty')
    if [ -z "$PROFILE_B_ID" ]; then
        echo -e "${RED}✗ Failed to create Company B profile: $CREATE_B${NC}"
        FAILURES=$((FAILURES + 1))
    else
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_B_ID" \
            -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
        assert_status "Owner A DELETE Company B profile $PROFILE_B_ID (anti-enumeration)" "404" "$STATUS"
        # Cleanup: Owner B deactivates its own profile (proves the 404 above
        # was isolation, not a nonexistent id).
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_B_ID" \
            -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_B_SESSION")
        assert_status "Owner B DELETE own Company B profile (control)" "200" "$STATUS"
    fi
fi

echo ""
echo "Step 10: Legacy route POST /api/v1/agents/<id>/deactivate no longer usable for this purpose"
echo "(covered separately by test_us27_s5_legacy_agent_routes_removed.sh once Task 9 lands)"

echo ""
echo "========================================"
if [ "$FAILURES" -eq 0 ]; then
    echo -e "${GREEN}US27-S1: ALL CHECKS PASSED${NC}"
    exit 0
else
    echo -e "${RED}US27-S1: $FAILURES CHECK(S) FAILED${NC}"
    exit 1
fi
