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
echo "Step 6: test_multitenancy_isolation_reactivate_profile -- Owner A reactivates a Company B profile"
# ADR-008 anti-enumeration: cross-company access is 404, never 403.
OWNER_B_LOGIN=$(login_user "${TEST_USER_OWNER_B:-cap.owner.b@example.com}" "${TEST_PASSWORD_OWNER_B:-seed123}")
OWNER_B_SESSION="${OWNER_B_LOGIN%%|*}"; OWNER_B_COMPANY="${OWNER_B_LOGIN##*|}"
if [ -z "$OWNER_B_SESSION" ] || [ "$OWNER_B_COMPANY" = "$OWNER_COMPANY" ]; then
    echo -e "${RED}✗ Owner B unavailable or in the same company as Owner A -- cannot test isolation${NC}"
    FAILURES=$((FAILURES + 1))
else
    DOC_B=$(gen_valid_cpf "$(printf '%09d' $(( (TIMESTAMP + 11) % 1000000000 )))")
    TENANT_TYPE_ID_B=$(curl -s "$API_BASE/profile-types" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_B_SESSION" | jq -r '.data[] | select(.code=="tenant") | .id')
    CREATE_B=$(curl -s -X POST "$API_BASE/profiles" \
        -H "Content-Type: application/json" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_B_SESSION" \
        -d "{\"name\": \"US27S2 CompanyB $TIMESTAMP\", \"company_id\": $OWNER_B_COMPANY, \"document\": \"$DOC_B\", \"email\": \"us27s2b_$TIMESTAMP@example.com\", \"birthdate\": \"1990-01-01\", \"profile_type_id\": $TENANT_TYPE_ID_B}")
    PROFILE_B_ID=$(echo "$CREATE_B" | jq -r '.id // empty')
    if [ -z "$PROFILE_B_ID" ]; then
        echo -e "${RED}✗ Failed to create Company B profile: $CREATE_B${NC}"; FAILURES=$((FAILURES + 1))
    else
        curl -s -X DELETE "$API_BASE/profiles/$PROFILE_B_ID" -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_B_SESSION" > /dev/null
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/profiles/$PROFILE_B_ID/reactivate" \
            -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
        assert_status "Owner A reactivate Company B profile $PROFILE_B_ID (anti-enumeration)" "404" "$STATUS"
        # Control: Owner B *can* reactivate it, proving the 404 above was
        # tenant isolation and not simply a nonexistent/undeletable id.
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/profiles/$PROFILE_B_ID/reactivate" \
            -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_B_SESSION")
        assert_status "Owner B reactivate own Company B profile (control)" "200" "$STATUS"
    fi
fi

echo ""
echo "Step 7: test_reactivate_atomic_rollback_on_agent_constraint_failure (FR2.7)"
# _reactivate_profile_cascade writes profile -> agent -> res.users IN THAT
# ORDER. We arrange a genuine constraint failure on the LAST step so the
# first two have already been written when it blows up:
#
#   odoo/addons/base/models/res_users.py::_check_company is
#   @api.constrains('company_id', 'company_ids', 'active') and only
#   validates users where u.active is True. So an INACTIVE user is allowed
#   to sit in the inconsistent state "company_id not in company_ids" -- and
#   the moment the cascade writes active=True, that real core constraint
#   fires with a real ValidationError.
#
# Without the explicit request.env.cr.rollback() in reactivate_profile's
# outer exception handler, Odoo commits the request anyway and the profile
# (and agent) stay active=True while the login stays disabled -- exactly
# the partial state FR2.7 forbids. This step asserts all three are still
# inactive after the 500.
COMPOSE="docker compose -f ${SCRIPT_DIR}/../18.0/docker-compose.yml"
odoo_shell() {
    $COMPOSE exec -T odoo odoo shell -d "${DB_NAME:-realestate}" --no-http --log-level=error 2>/dev/null
}

ROLLBACK_TAG="us27s2rb_${TIMESTAMP}"
ROLLBACK_DOC=$(gen_valid_cpf "$(printf '%09d' $(( (TIMESTAMP + 23) % 1000000000 )))")
SETUP_OUT=$(odoo_shell <<PYEOF
company = env['res.company'].browse(${OWNER_COMPANY})
other = env['res.company'].search([('id', '!=', ${OWNER_COMPANY})], limit=1)
ptype = env['thedevkitchen.profile.type'].search([('code', '=', 'agent')], limit=1)
partner = env['res.partner'].create({'name': 'RB ${ROLLBACK_TAG}', 'company_id': company.id})
profile = env['thedevkitchen.estate.profile'].create({
    'name': 'RB ${ROLLBACK_TAG}', 'company_id': company.id,
    'profile_type_id': ptype.id, 'document': '${ROLLBACK_DOC}',
    'email': '${ROLLBACK_TAG}@example.com', 'birthdate': '1990-01-01',
    'partner_id': partner.id,
})
agent = env['real.estate.agent'].create({'profile_id': profile.id})
user = env['res.users'].create({
    'login': '${ROLLBACK_TAG}@example.com', 'name': 'RB ${ROLLBACK_TAG}',
    'partner_id': partner.id, 'company_id': company.id,
    'company_ids': [(6, 0, [company.id])],
})
# Deactivate everything (the normal soft-delete end state)...
user.write({'active': False})
agent.write({'active': False})
profile.write({'active': False})
# ...then plant the pre-existing inconsistency the constraint will catch
# on reactivation. Legal only while the user is inactive.
user.write({'company_ids': [(6, 0, [other.id])]})
env.cr.commit()
print('SETUP|%s|%s|%s' % (profile.id, agent.id, user.id))
PYEOF
)
RB_LINE=$(echo "$SETUP_OUT" | grep '^SETUP|' | head -1)
RB_PROFILE=$(echo "$RB_LINE" | cut -d'|' -f2)
RB_AGENT=$(echo "$RB_LINE" | cut -d'|' -f3)
RB_USER=$(echo "$RB_LINE" | cut -d'|' -f4)

if [ -z "$RB_PROFILE" ]; then
    echo -e "${RED}✗ Rollback fixture setup failed:${NC}"; echo "$SETUP_OUT" | tail -20
    FAILURES=$((FAILURES + 1))
else
    echo "  Fixture: profile=$RB_PROFILE agent=$RB_AGENT user=$RB_USER (all inactive, user company_ids poisoned)"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/profiles/$RB_PROFILE/reactivate" \
        -H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $OWNER_SESSION")
    assert_status "Reactivate with poisoned res.users state" "500" "$STATUS"

    STATE=$(odoo_shell <<PYEOF
p = env['thedevkitchen.estate.profile'].with_context(active_test=False).browse(${RB_PROFILE})
a = env['real.estate.agent'].with_context(active_test=False).browse(${RB_AGENT})
u = env['res.users'].with_context(active_test=False).browse(${RB_USER})
print('STATE|%s|%s|%s' % (p.active, a.active, u.active))
PYEOF
)
    STATE_LINE=$(echo "$STATE" | grep '^STATE|' | head -1)
    if [ "$STATE_LINE" = "STATE|False|False|False" ]; then
        echo -e "${GREEN}✓ Whole transaction rolled back: profile/agent/user all still inactive${NC}"
    else
        echo -e "${RED}✗ Partial state committed -- expected STATE|False|False|False, got: $STATE_LINE${NC}"
        FAILURES=$((FAILURES + 1))
    fi

    # Cleanup: unpoison and archive the fixture (soft-delete only, ADR-015).
    odoo_shell > /dev/null <<PYEOF
u = env['res.users'].with_context(active_test=False).browse(${RB_USER})
u.write({'company_ids': [(6, 0, [${OWNER_COMPANY}])]})
u.write({'login': 'archived_${ROLLBACK_TAG}@example.com'})
env.cr.commit()
PYEOF
fi

echo ""
echo "========================================"
if [ "$FAILURES" -eq 0 ]; then echo -e "${GREEN}US27-S2: ALL CHECKS PASSED${NC}"; exit 0;
else echo -e "${RED}US27-S2: $FAILURES CHECK(S) FAILED${NC}"; exit 1; fi
