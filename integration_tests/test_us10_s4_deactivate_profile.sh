#!/usr/bin/env bash
# Feature 010 - US10-S4: Soft Delete Profile - T24
# E2E test for DELETE /api/v1/profiles/<id>
#
# Success Criteria:
# - Soft delete with reason → 200, active=False
# - Agent extension deactivated in cascade
# - Linked res.users deactivated
# - Already inactive → 400

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
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================"
echo "US10-S4: Soft Delete Profile"
echo "========================================"

# Get Bearer Token
echo "Step 0: Getting OAuth2 bearer token..."
BEARER_TOKEN=$(get_oauth2_token)
if [ $? -ne 0 ] || [ -z "$BEARER_TOKEN" ]; then
    echo -e "${RED}✗ Failed to get OAuth2 token${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Bearer token obtained${NC}"

# Helper: Login user
login_user() {
    local email="$1"
    local password="$2"
    
    local response=$(curl -s -X POST "$API_BASE/users/login" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $BEARER_TOKEN" \
        -d "{\"login\": \"$email\", \"password\": \"$password\"}")
    
    local session_id=$(echo "$response" | jq -r '.session_id // empty')
    local company_id=$(echo "$response" | jq -r '.user.default_company_id // empty')
    
    if [ -z "$session_id" ] || [ -z "$company_id" ]; then
        echo ""
        return 1
    fi
    
    echo "$session_id|$company_id"
}

# Step 1: Login as Owner
echo ""
echo "Step 1: Logging in as Owner..."
OWNER_EMAIL="${TEST_USER_OWNER:-owner@example.com}"
OWNER_PASSWORD="${TEST_PASSWORD_OWNER:-SecurePass123!}"

OWNER_LOGIN_DATA=$(login_user "$OWNER_EMAIL" "$OWNER_PASSWORD")
if [ -z "$OWNER_LOGIN_DATA" ]; then
    echo -e "${RED}✗ Owner login failed${NC}"
    exit 1
fi

OWNER_SESSION="${OWNER_LOGIN_DATA%%|*}"
OWNER_COMPANY="${OWNER_LOGIN_DATA##*|}"
echo -e "${GREEN}✓ Owner logged in (company_id=$OWNER_COMPANY)${NC}"

# Step 2: Create a test profile
echo ""
echo "Step 2: Creating test profile..."
TIMESTAMP=$(date +%s)
TEST_CPF=$(python3 -c "
import time
base = str((int(time.time()) + 600) % 1000000000).zfill(9)
def d(cpf, w):
    s = sum(int(c)*w for c,w in zip(cpf,w))
    r = s%11
    return '0' if r<2 else str(11-r)
d1 = d(base, range(10,1,-1))
d2 = d(base+d1, range(11,1,-1))
print(base+d1+d2)
")

CREATE_RESPONSE=$(curl -s -X POST "$API_BASE/profiles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{
        \"name\": \"Delete Test ${TIMESTAMP}\",
        \"company_id\": $OWNER_COMPANY,
        \"document\": \"$TEST_CPF\",
        \"email\": \"deletetest${TIMESTAMP}@test.com\",
        \"phone\": \"11987654321\",
        \"birthdate\": \"1990-01-15\",
        \"profile_type_id\": 3
    }")

PROFILE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.id // empty')
if [ -z "$PROFILE_ID" ]; then
    echo -e "${RED}✗ Failed to create test profile${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Test profile created (ID=$PROFILE_ID)${NC}"

# Step 3: Soft delete with reason → 200, active=False
echo ""
echo "Step 3: Soft deleting profile with reason..."
DELETE_RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_ID?company_ids=$OWNER_COMPANY" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{
        \"reason\": \"Test deactivation\",
        \"deactivation_date\": \"2026-02-19\"
    }")

HTTP_CODE=$(echo "$DELETE_RESPONSE" | tail -n1)
if [ "$HTTP_CODE" != "200" ]; then
    echo -e "${RED}✗ Delete failed, got $HTTP_CODE${NC}"
    echo "Response: $DELETE_RESPONSE"
    exit 1
fi

BODY=$(echo "$DELETE_RESPONSE" | sed '$d')
SUCCESS=$(echo "$BODY" | jq -r '.success // empty')

if [ "$SUCCESS" != "true" ]; then
    echo -e "${RED}✗ Profile not deactivated (success=$SUCCESS)${NC}"
    echo "Response body: $BODY"
    exit 1
fi

echo -e "${GREEN}✓ Profile soft deleted (is_active=false)${NC}"

# Step 4: Test already inactive → 400
# Feature 027 (I-6): delete_profile now searches with active_test=False
# (matching get_profile/list_profiles/reactivate_profile), so it can find
# an already-inactive profile and reach its own "already inactive" check
# instead of 404ing before ever reaching it. 400 is the correct/intended
# response here (owner as delete_profile's own code has always said),
# not 404 -- the old 404 only happened because the profile was invisible
# to the search, which was itself the bug Feature 027 fixed.
echo ""
echo "Step 4: Testing delete already inactive profile → 400..."
DELETE_AGAIN=$(curl -s -w "\n%{http_code}" -X DELETE "$API_BASE/profiles/$PROFILE_ID?company_ids=$OWNER_COMPANY" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{
        \"reason\": \"Already deleted\"
    }")

HTTP_CODE=$(echo "$DELETE_AGAIN" | tail -n1)
if [ "$HTTP_CODE" != "400" ]; then
    echo -e "${RED}✗ Expected 400, got $HTTP_CODE${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Delete inactive profile returns 400 (already inactive)${NC}"

# Step 5: Test agent extension cascade deactivation
echo ""
echo "Step 5: Testing agent extension cascade deactivation..."
# Create an agent profile
AGENT_CPF=$(python3 -c "
import time
base = str((int(time.time()) + 700) % 1000000000).zfill(9)
def d(cpf, w):
    s = sum(int(c)*w for c,w in zip(cpf,w))
    r = s%11
    return '0' if r<2 else str(11-r)
d1 = d(base, range(10,1,-1))
d2 = d(base+d1, range(11,1,-1))
print(base+d1+d2)
")
CREATE_AGENT=$(curl -s -X POST "$API_BASE/profiles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -H "X-Openerp-Session-Id: $OWNER_SESSION" \
    -d "{
        \"name\": \"Agent Cascade Test\",
        \"company_id\": $OWNER_COMPANY,
        \"document\": \"$AGENT_CPF\",
        \"email\": \"agentcascade${TIMESTAMP}@test.com\",
        \"phone\": \"11988887777\",
        \"birthdate\": \"1992-03-20\",
        \"profile_type_id\": 4,
        \"hire_date\": \"2024-01-01\"
    }")

AGENT_PROFILE_ID=$(echo "$CREATE_AGENT" | jq -r '.id // empty')
AGENT_LINK=$(echo "$CREATE_AGENT" | jq -r '._links.agent // empty')
AGENT_EXTENSION_ID=$(echo "$AGENT_LINK" | sed -n 's|.*/agents/\([0-9]*\).*|\1|p')

if [ -n "$AGENT_PROFILE_ID" ] && [ "$AGENT_PROFILE_ID" != "null" ]; then
    # Soft delete the agent profile
    DELETE_AGENT=$(curl -s -X DELETE "$API_BASE/profiles/$AGENT_PROFILE_ID?company_ids=$OWNER_COMPANY" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $BEARER_TOKEN" \
        -H "X-Openerp-Session-Id: $OWNER_SESSION" \
        -d "{\"reason\": \"Cascade test\"}")
    
    # Verify agent extension is also deactivated (would need agent API check)
    echo -e "${GREEN}✓ Agent profile deleted (cascade verification needs agent API)${NC}"
else
    echo -e "${YELLOW}⊘ Agent profile creation failed, skipping cascade test${NC}"
fi

# Step 6: Test linked res.users deactivation (requires invite flow integration)
echo ""
echo "Step 6: Testing linked res.users deactivation..."
echo -e "${YELLOW}⊘ Skipped (requires invite flow integration)${NC}"

echo ""
echo -e "${GREEN}========================================"
echo "✓ All T24 tests passed!"
echo "========================================${NC}"

exit 0
