#!/bin/bash
# integration_tests/test_us026_s2_resend_invite_regression.sh
# Feature 026 — User Story 2: reenvio de convite não recria/duplica o agente.
#
# Pure regression coverage — no production code touched. POST
# /api/v1/users/resend-invite only regenerates the invite token/email; it never
# calls create_user_from_profile or _upsert_agent_for_invite (Tasks 4-6's new
# agent-unification logic lives entirely in invite_user, not resend_invite —
# see 18.0/extra-addons/thedevkitchen_user_onboarding/controllers/invite_controller.py).
# This script proves that calling resend-invite after those changes does NOT
# create a duplicate real_estate_agent row and does NOT disturb the row already
# linked by the original invite.
#
# NOTE (confirmed against current code before writing this script, per Task 7
# instructions — the brief's assumed request shape was stale):
#   - Route is POST /api/v1/users/resend-invite (NOT /api/v1/users/{id}/resend-invite).
#   - user_id is a JSON body field, not a URL path segment (invite_controller.py:304-330).
#   - Auth is the same triple decorator chain as every other endpoint in this
#     session (@require_jwt/@require_session/@require_company) — Bearer token +
#     X-Openerp-Session-Id + X-Company-ID, matching test_us9_s6_resend_invite.sh's
#     already-passing usage of this same endpoint.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../18.0/.env" 2>/dev/null || true
BASE_URL="${BASE_URL:-http://localhost:8069}"
TESTS_RUN=0; TESTS_PASSED=0; TESTS_FAILED=0

# Test data namespaced distinctly from test_us026_s1_invite_agent_unification.sh
# (us026_agent_pending@..., us026_bad_creci@..., us026_dup_creci*@..., us026_spoof@...)
# and test_us026_s1_rbac_visibility.sh (us026_rbac_agent@...) — this script only
# ever touches us026_resend_agent@example.com, so cleanup uses an exact match,
# not a LIKE 'us026_%' wildcard that could reach into the other scripts' data.
TEST_EMAIL="us026_resend_agent@example.com"
TEST_CPF="73928461591"  # fresh, checksum-valid, not reused by the other US026 scripts

cleanup() {
  # real_estate_agent has ondelete=restrict FKs on both profile_id and user_id
  # (confirmed via pg_constraint in Task 5/6 work) — must delete it before the
  # res_users/profile rows it points to, or the DELETEs below fail silently.
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_agent WHERE profile_id IN (SELECT id FROM thedevkitchen_estate_profile WHERE email = '${TEST_EMAIL}') OR user_id IN (SELECT u.id FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email = '${TEST_EMAIL}');" >/dev/null 2>&1
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM res_users WHERE login = '${TEST_EMAIL}';" >/dev/null 2>&1
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM thedevkitchen_estate_profile WHERE email = '${TEST_EMAIL}';" >/dev/null 2>&1
}
cleanup

# --- Auth ---
BEARER_TOKEN=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token" -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"${OAUTH_CLIENT_ID}\",\"client_secret\":\"${OAUTH_CLIENT_SECRET}\"}" \
  | jq -r '.access_token')
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_MANAGER}\",\"password\":\"${TEST_PASSWORD_MANAGER}\"}")
SESSION_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.session_id')  # sem wrapper .data
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.user.default_company_id')
AUTH_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

if [ -z "$SESSION_ID" ] || [ "$SESSION_ID" = "null" ]; then
  echo "FAIL: could not authenticate (no session_id) — aborting"
  echo "LOGIN_RESPONSE: $LOGIN_RESPONSE"
  exit 1
fi

# Resolve o FK inteiro de profile_type_id (nunca hardcodear a string "agent")
AGENT_PROFILE_TYPE_ID=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM thedevkitchen_profile_type WHERE code = 'agent' LIMIT 1;" | tr -d '[:space:]')

# --- Setup: create profile (auto-creates a real_estate_agent without user_id,
# per profile_api.py — expected background behavior) then invite it as an agent
# (invite_controller.py's _upsert_agent_for_invite links that same row + sets
# user_id, per Tasks 4-6). ---
PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Resend Agent","company_id":'"${COMPANY_ID}"',"document":"'"${TEST_CPF}"'","email":"'"${TEST_EMAIL}"'","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
PROFILE_BODY=$(echo "$PROFILE_RESPONSE" | sed '$d')
PROFILE_STATUS=$(echo "$PROFILE_RESPONSE" | tail -n 1)
PROFILE_ID=$(echo "$PROFILE_BODY" | jq -r '.id')  # resposta flat, sem wrapper .data

TESTS_RUN=$((TESTS_RUN + 1))
if [ "$PROFILE_STATUS" = "201" ] && [ -n "$PROFILE_ID" ] && [ "$PROFILE_ID" != "null" ]; then
  echo "PASS: setup — profile created (id=$PROFILE_ID)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: setup — profile creation failed (status $PROFILE_STATUS): $PROFILE_BODY"
  TESTS_FAILED=$((TESTS_FAILED + 1))
  cleanup
  echo ""
  echo "=== US026-S2: $TESTS_PASSED/$TESTS_RUN passed ==="
  exit 1
fi

INVITE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${PROFILE_ID}"',"agent":{"creci":"CRECI-SP 444444"}}')
INVITE_BODY=$(echo "$INVITE_RESPONSE" | sed '$d')
INVITE_STATUS=$(echo "$INVITE_RESPONSE" | tail -n 1)
USER_ID=$(echo "$INVITE_BODY" | jq -r '.data.id')
AGENT_ID_FROM_INVITE=$(echo "$INVITE_BODY" | jq -r '.data.agent_id')

TESTS_RUN=$((TESTS_RUN + 1))
if [ "$INVITE_STATUS" = "201" ] && [ -n "$USER_ID" ] && [ "$USER_ID" != "null" ]; then
  echo "PASS: setup — invite created user (id=$USER_ID, agent_id=$AGENT_ID_FROM_INVITE)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: setup — invite failed (status $INVITE_STATUS): $INVITE_BODY"
  TESTS_FAILED=$((TESTS_FAILED + 1))
  cleanup
  echo ""
  echo "=== US026-S2: $TESTS_PASSED/$TESTS_RUN passed ==="
  exit 1
fi

# --- Baseline: exactly one agent row linked to this user, capture its id ---
AGENT_COUNT_BEFORE=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM real_estate_agent WHERE user_id = ${USER_ID};" | tr -d '[:space:]')
AGENT_ID_BEFORE=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM real_estate_agent WHERE user_id = ${USER_ID} LIMIT 1;" | tr -d '[:space:]')

TESTS_RUN=$((TESTS_RUN + 1))
if [ "$AGENT_COUNT_BEFORE" = "1" ]; then
  echo "PASS: baseline — exactly one agent row linked to user $USER_ID before resend (agent_id=$AGENT_ID_BEFORE)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: baseline — expected exactly 1 agent row for user $USER_ID, found $AGENT_COUNT_BEFORE"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Act: call resend-invite. Route takes user_id in the JSON body, not the URL
# (confirmed against invite_controller.py:292-330 — the brief's assumed
# /api/v1/users/{id}/resend-invite path shape is stale). ---
RESEND_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/resend-invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"user_id":'"${USER_ID}"'}')
RESEND_BODY=$(echo "$RESEND_RESPONSE" | sed '$d')
RESEND_STATUS=$(echo "$RESEND_RESPONSE" | tail -n 1)
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$RESEND_STATUS" = "200" ] || [ "$RESEND_STATUS" = "201" ]; then
  echo "PASS: resend-invite succeeds (status $RESEND_STATUS): $RESEND_BODY"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: resend-invite returned $RESEND_STATUS: $RESEND_BODY"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Assert: agent row count for this user is unchanged, and it's the SAME row
# (not one deleted + a different one created, which a naive count comparison
# alone would miss). ---
AGENT_COUNT_AFTER=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM real_estate_agent WHERE user_id = ${USER_ID};" | tr -d '[:space:]')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$AGENT_COUNT_BEFORE" = "$AGENT_COUNT_AFTER" ]; then
  echo "PASS: agent count unchanged after resend-invite ($AGENT_COUNT_BEFORE == $AGENT_COUNT_AFTER)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: agent count changed after resend-invite (before: $AGENT_COUNT_BEFORE, after: $AGENT_COUNT_AFTER)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

AGENT_ID_AFTER=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM real_estate_agent WHERE user_id = ${USER_ID} LIMIT 1;" | tr -d '[:space:]')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$AGENT_ID_BEFORE" = "$AGENT_ID_AFTER" ] && [ -n "$AGENT_ID_BEFORE" ]; then
  echo "PASS: same agent row id preserved across resend-invite (id=$AGENT_ID_BEFORE)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: agent row id changed or missing (before: $AGENT_ID_BEFORE, after: $AGENT_ID_AFTER)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Assert: overall real_estate_agent table count for this profile is also
# still exactly 1 (guards against a duplicate row created without a user_id,
# which the user_id-scoped queries above would not catch). ---
AGENT_COUNT_BY_PROFILE=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM real_estate_agent WHERE profile_id = ${PROFILE_ID};" | tr -d '[:space:]')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$AGENT_COUNT_BY_PROFILE" = "1" ]; then
  echo "PASS: exactly one agent row for profile $PROFILE_ID after resend-invite (no orphan duplicate)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: expected exactly 1 agent row for profile $PROFILE_ID, found $AGENT_COUNT_BY_PROFILE"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

cleanup
echo ""
echo "=== US026-S2: $TESTS_PASSED/$TESTS_RUN passed ==="
[ "$TESTS_FAILED" -gt 0 ] && exit 1
exit 0
