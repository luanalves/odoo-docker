#!/bin/bash
# integration_tests/test_us026_s1_proposal_notification_recipient.sh
# Feature 026 — FR6.1, proposal.py notification-recipient path (adjusted scope,
# confirmed with the human before writing this script).
#
# ACHADO CRÍTICO (documentado aqui e no relatório final, não é limitação deste
# teste): proposal.py's _emit_event(self, event_type, payload) (~line 853-867)
# receives a `payload` dict that includes "recipient_partner_ids" (e.g.
# [self.agent_id.user_id.partner_id.id] at line 676, or
# [comp.agent_id.user_id.partner_id.id] at line 665) built by every FSM action
# (action_send/action_accept/action_reject/etc.) -- but `payload` is NEVER READ
# inside _emit_event's body. Only proposal_id and event_type actually cross to
# Celery:
#     send_task("proposal.send_email",
#                kwargs={"proposal_id": self.id, "event_name": event_type},
#                queue="notification_events")
# So recipient_partner_ids is discarded before it ever reaches the async worker.
# There is no event/outbox table and no code path that makes this value
# observable from outside the Odoo process -- confirmed by reading event_bus.py/
# tasks.py and grepping for any persistence of the payload dict (none found).
# Deeper instrumentation (patching _emit_event, reading Celery task args from
# RabbitMQ) would be required to observe it directly, which is out of scope
# for a curl-based E2E script.
#
# Additionally: email_template_proposal_accepted's partner_to is hardcoded to
# object.partner_id.id (the CLIENT only) -- it does NOT use agent_id.user_id.partner_id
# at all, despite action_accept() computing it into the (discarded) payload.
# Only email_template_proposal_superseded's partner_to happens to reference
# object.agent_id.user_id.partner_id.id.
#
# GIVEN THIS, the achievable and honest scope of this script is:
#   1. Prove the FULL chain (invite -> real.estate.agent with user_id set ->
#      assignment -> proposal FSM: draft -> queued -> sent -> accept ->
#      accepted + superseded) works end-to-end for an agent created through
#      the Feature 026 unified invite flow, with NO 500s/unexpected errors
#      anywhere the discarded recipient_partner_ids computation lives.
#   2. Directly verify via SQL that the exact expression chain
#      agent_id -> user_id -> partner_id (which _emit_event's callers depend on
#      to build recipient_partner_ids, even though it's discarded downstream)
#      is structurally sound for THIS specific invited agent: both user_id and
#      partner_id resolve to non-null values.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../18.0/.env" 2>/dev/null || true
BASE_URL="${BASE_URL:-http://localhost:8069}"
COMPOSE_FILE="${SCRIPT_DIR}/../18.0/docker-compose.yml"

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

assert_status() {
  local expected="$1" actual="$2" label="$3"
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ "$actual" = "$expected" ]; then
    echo "PASS: $label (status $actual)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "FAIL: $label (expected $expected, got $actual)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

# Distinct namespace (us026_notif_*) so cleanup never collides with any other
# test_us026_*.sh script's data.
cleanup() {
  # FK ordering: proposals reference property_id/agent_id -- delete them first.
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_proposal WHERE property_id IN (SELECT id FROM real_estate_property WHERE name = 'US026 Notification Test Property');" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_agent_property_assignment WHERE property_id IN (SELECT id FROM real_estate_property WHERE name = 'US026 Notification Test Property');" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_lead WHERE name LIKE '%US026 Notification Test Property%';" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_property WHERE name = 'US026 Notification Test Property';" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_agent WHERE profile_id IN (SELECT id FROM thedevkitchen_estate_profile WHERE email = 'us026_notif_agent@example.com') OR user_id IN (SELECT u.id FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email = 'us026_notif_agent@example.com');" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM res_users WHERE login = 'us026_notif_agent@example.com';" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM thedevkitchen_estate_profile WHERE email = 'us026_notif_agent@example.com';" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM res_partner WHERE vat = '40196154383';" >/dev/null 2>&1
}
cleanup

# --- Auth as manager (mesmo padrão dos demais scripts test_us026_*.sh; usado
# para TODAS as chamadas, incluindo /accept, que exige group_real_estate_manager
# ou group_real_estate_owner -- action_accept(), proposal.py:628-633). ---
BEARER_TOKEN=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token" -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"${OAUTH_CLIENT_ID}\",\"client_secret\":\"${OAUTH_CLIENT_SECRET}\"}" \
  | jq -r '.access_token')

LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_MANAGER}\",\"password\":\"${TEST_PASSWORD_MANAGER}\"}")
SESSION_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.session_id')
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.user.default_company_id')

if [ -z "$SESSION_ID" ] || [ "$SESSION_ID" = "null" ]; then
  echo "FATAL: manager login failed, cannot proceed. Response: $LOGIN_RESPONSE"
  exit 1
fi

AUTH_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

AGENT_PROFILE_TYPE_ID=$(docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM thedevkitchen_profile_type WHERE code = 'agent' LIMIT 1;" | tr -d '[:space:]')

# 1. Invite a new agent via the full unified invite flow.
# CPF: 40196154383 -- gerado e validado com validate_docbr.CPF().validate() == True
# no próprio container, distinto de todos os CPFs já usados neste branch.
PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Notification Agent","company_id":'"${COMPANY_ID}"',"document":"40196154383","email":"us026_notif_agent@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
PROFILE_BODY=$(echo "$PROFILE_RESPONSE" | sed '$d')
PROFILE_STATUS=$(echo "$PROFILE_RESPONSE" | tail -n 1)
assert_status "201" "$PROFILE_STATUS" "profile created for notification test agent"
PROFILE_ID=$(echo "$PROFILE_BODY" | jq -r '.id')

INVITE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${PROFILE_ID}"',"agent":{"creci":"CRECI-SP 333333"}}')
INVITE_BODY=$(echo "$INVITE_RESPONSE" | sed '$d')
INVITE_STATUS=$(echo "$INVITE_RESPONSE" | tail -n 1)
assert_status "201" "$INVITE_STATUS" "invite created (agent user_id upsert path)"
NEW_USER_ID=$(echo "$INVITE_BODY" | jq -r '.data.id')
NEW_AGENT_ID=$(echo "$INVITE_BODY" | jq -r '.data.agent_id')

if [ -z "$NEW_USER_ID" ] || [ "$NEW_USER_ID" = "null" ] || [ -z "$NEW_AGENT_ID" ] || [ "$NEW_AGENT_ID" = "null" ]; then
  echo "FATAL: invite did not return usable id/agent_id. Response: $INVITE_BODY"
  cleanup
  exit 1
fi
echo "INFO: new_user_id=$NEW_USER_ID new_agent_id=$NEW_AGENT_ID company_id=$COMPANY_ID"

# 2. Create a property (raw INSERT, same minimal-fields pattern as
# test_us026_s1_rbac_visibility.sh -- ORM-level constraints like _check_intentions
# and _check_prices only fire via the ORM, not on a raw SQL INSERT, consistent
# with the other scripts in this branch).
docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
  "INSERT INTO real_estate_property (
      name, company_id, agent_id, active,
      property_type_id, country_id, state_id, location_type_id,
      origin_media, property_purpose, zip_code, city, street, street_number,
      property_status, condition, area
   ) VALUES (
      'US026 Notification Test Property', ${COMPANY_ID}, NULL, TRUE,
      1, 31, 95, 1,
      'website', 'residential', '01310-100', 'São Paulo', 'Rua US026 Notif', '1',
      'available', 'good', 100
   );" >/dev/null

PROPERTY_ID=$(docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM real_estate_property WHERE name = 'US026 Notification Test Property';" | tr -d '[:space:]')
echo "INFO: created property_id=$PROPERTY_ID"

# 3. Assign the invited agent to the property via POST /api/v1/assignments.
# REQUIRED: real.estate.proposal's _check_agent_assigned_to_property constraint
# (proposal.py:346-358) checks property.assigned_agent_ids, which is COMPUTED
# from real.estate.agent.property.assignment records (property.py:592-597),
# NOT from the property's plain agent_id column -- these are different things.
# Without this step, proposal creation below would fail with a ValidationError
# ("Agent is not assigned to property").
ASSIGNMENT_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/assignments" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"agent_id":'"${NEW_AGENT_ID}"',"property_id":'"${PROPERTY_ID}"'}')
ASSIGNMENT_STATUS=$(echo "$ASSIGNMENT_RESPONSE" | tail -n 1)
assert_status "201" "$ASSIGNMENT_STATUS" "agent assigned to property via POST /api/v1/assignments"

# 4. Create TWO proposals on the SAME property, both with this agent.
# agent_id is required per proposal_create.json's schema (required: property_id,
# client_name, client_document, agent_id, proposal_type, proposal_value).
# First becomes draft (no active proposal exists yet); second auto-parks as
# queued (proposal.py create()'s pessimistic-lock logic, active_exists check,
# lines 485-500).
PROPOSAL_BODY_TEMPLATE='{"property_id":'"${PROPERTY_ID}"',"client_name":"US026 Notif Client","client_document":"52998224725","agent_id":'"${NEW_AGENT_ID}"',"proposal_type":"sale","proposal_value":250000}'

P1_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/proposals" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d "$PROPOSAL_BODY_TEMPLATE")
P1_STATUS=$(echo "$P1_RESPONSE" | tail -n 1)
P1_BODY=$(echo "$P1_RESPONSE" | sed '$d')
assert_status "201" "$P1_STATUS" "first proposal created"
P1_ID=$(echo "$P1_BODY" | jq -r '.id')
P1_STATE=$(echo "$P1_BODY" | jq -r '.state')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$P1_STATE" = "draft" ]; then
  echo "PASS: first proposal state=draft"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: first proposal state=$P1_STATE (expected draft)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

P2_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/proposals" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d "$PROPOSAL_BODY_TEMPLATE")
P2_STATUS=$(echo "$P2_RESPONSE" | tail -n 1)
P2_BODY=$(echo "$P2_RESPONSE" | sed '$d')
assert_status "201" "$P2_STATUS" "second proposal created"
P2_ID=$(echo "$P2_BODY" | jq -r '.id')
P2_STATE=$(echo "$P2_BODY" | jq -r '.state')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$P2_STATE" = "queued" ]; then
  echo "PASS: second proposal state=queued (auto-parked, active slot taken by first)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: second proposal state=$P2_STATE (expected queued)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi
echo "INFO: P1_ID=$P1_ID (draft) P2_ID=$P2_ID (queued)"

# 5. POST /proposals/<first>/send -> sent.
SEND_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/proposals/${P1_ID}/send" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" -d '{}')
SEND_STATUS=$(echo "$SEND_RESPONSE" | tail -n 1)
SEND_BODY=$(echo "$SEND_RESPONSE" | sed '$d')
assert_status "200" "$SEND_STATUS" "first proposal sent"
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$SEND_BODY" | jq -r '.state')" = "sent" ]; then
  echo "PASS: first proposal state=sent"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: first proposal state after send=$(echo "$SEND_BODY" | jq -r '.state') (expected sent)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# 6. POST /proposals/<first>/accept as the MANAGER (group_real_estate_manager) --
# NOT as the agent -- action_accept() enforces this RBAC (proposal.py:628-633).
# This triggers BOTH proposal.accepted (first) AND proposal.superseded (second,
# since it's still queued/non-terminal when the first is accepted -- the accept
# logic auto-cancels all non-terminal competitors on the same property,
# proposal.py:642-668).
ACCEPT_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/proposals/${P1_ID}/accept" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" -d '{}')
ACCEPT_STATUS=$(echo "$ACCEPT_RESPONSE" | tail -n 1)
ACCEPT_BODY=$(echo "$ACCEPT_RESPONSE" | sed '$d')
assert_status "200" "$ACCEPT_STATUS" "first proposal accepted by manager (no 500 anywhere in the recipient-computation path)"

# 7. Verify final states via REST + psql: first accepted; second cancelled with
# superseded_by_id pointing at the first.
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$ACCEPT_BODY" | jq -r '.state')" = "accepted" ]; then
  echo "PASS: first proposal state=accepted (REST)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: first proposal state after accept=$(echo "$ACCEPT_BODY" | jq -r '.state') (expected accepted)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

P2_AFTER=$(curl -s -X GET "${BASE_URL}/api/v1/proposals/${P2_ID}" "${AUTH_HEADERS[@]}")
P2_AFTER_STATE=$(echo "$P2_AFTER" | jq -r '.state')
P2_AFTER_SUPERSEDED_BY=$(echo "$P2_AFTER" | jq -r '.superseded_by_id // .superseded_by_id.id // empty')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$P2_AFTER_STATE" = "cancelled" ]; then
  echo "PASS: second proposal state=cancelled (REST, after first was accepted)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: second proposal state=$P2_AFTER_STATE (expected cancelled)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# superseded_by_id via psql (avoids depending on the exact JSON shape the
# serializer uses for a many2one field).
DB_P2_SUPERSEDED_BY=$(docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT state, superseded_by_id FROM real_estate_proposal WHERE id = ${P2_ID};")
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$DB_P2_SUPERSEDED_BY" | grep -q "cancelled|${P1_ID}"; then
  echo "PASS: DB confirms second proposal state=cancelled, superseded_by_id=${P1_ID}"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: DB does not show expected state/superseded_by_id (got: $DB_P2_SUPERSEDED_BY, expected cancelled|${P1_ID})"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# 8. Direct SQL join proving the exact expression chain agent_id -> user_id ->
# partner_id (which _emit_event's CALLERS depend on to build
# recipient_partner_ids, even though _emit_event itself discards the payload
# before Celery) is structurally sound for THIS invited agent.
CHAIN_CHECK=$(docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT a.id, a.user_id, u.partner_id FROM real_estate_agent a JOIN res_users u ON u.id = a.user_id WHERE a.id = ${NEW_AGENT_ID};")
echo "INFO: agent_id -> user_id -> partner_id chain: $CHAIN_CHECK"
TESTS_RUN=$((TESTS_RUN + 1))
CHAIN_USER_ID=$(echo "$CHAIN_CHECK" | awk -F'|' '{print $2}' | tr -d '[:space:]')
CHAIN_PARTNER_ID=$(echo "$CHAIN_CHECK" | awk -F'|' '{print $3}' | tr -d '[:space:]')
if [ -n "$CHAIN_USER_ID" ] && [ "$CHAIN_USER_ID" != "" ] && [ -n "$CHAIN_PARTNER_ID" ] && [ "$CHAIN_PARTNER_ID" != "" ]; then
  echo "PASS: agent_id.user_id (${CHAIN_USER_ID}) and agent_id.user_id.partner_id (${CHAIN_PARTNER_ID}) both non-null for this invited agent"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: chain broken -- user_id or partner_id is null/empty (got: $CHAIN_CHECK)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

cleanup
echo ""
echo "=== US026-S1 proposal.py notification-recipient path (FR6.1, adjusted scope): $TESTS_PASSED/$TESTS_RUN passed ==="
echo ""
echo "REMINDER (see full comment block at top of this file): recipient_partner_ids"
echo "is computed by every FSM action but discarded before _emit_event sends the"
echo "Celery task -- only proposal_id and event_name cross the boundary. Also,"
echo "email_template_proposal_accepted's partner_to is hardcoded to the client"
echo "partner_id only; it does not use agent_id.user_id.partner_id at all (only"
echo "email_template_proposal_superseded's partner_to does). This is a genuine"
echo "finding about the codebase, not a limitation of this test."
[ "$TESTS_FAILED" -gt 0 ] && exit 1
exit 0
