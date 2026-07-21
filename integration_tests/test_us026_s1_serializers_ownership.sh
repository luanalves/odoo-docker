#!/bin/bash
# integration_tests/test_us026_s1_serializers_ownership.sh
# Feature 026 — FR6.1, last remaining consumer of agent_id.user_id:
# controllers/utils/serializers.py:validate_property_access() (line ~617-643).
#
# validate_property_access() is called from TWO routes in property_api.py:
#   - GET /api/v1/properties/<id>  (operation="read",  line ~695)
#   - PUT /api/v1/properties/<id>  (operation="write", line ~747)
# Both share the same agent branch (line 637-643):
#   if property_record.agent_id and property_record.agent_id.user_id == user:
#       return True, None
#   return False, "You can only access your own properties"
#
# This script exercises the WRITE path (PUT), since it is the one explicitly
# named in the review finding, using an agent created through the Feature 026
# unified invite flow (Tasks 4/5 upsert) -- proving property_record.agent_id.user_id
# resolves correctly end-to-end for this THIRD consumer, completing FR6.1
# alongside property_api.py's list_properties() (test_us026_s1_rbac_visibility.sh)
# and lead_api.py's list_leads() (same script, steps 7-9).
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

# Distinct namespace (us026_ownership_*) so cleanup never collides with
# test_us026_s1_invite_agent_unification.sh (us026_*) or
# test_us026_s1_rbac_visibility.sh (us026_rbac_*).
cleanup() {
  # FK ordering: real_estate_property.agent_id is ON DELETE SET NULL (safe to
  # leave), but real_estate_agent.profile_id/.user_id are ondelete='restrict' --
  # must delete the agent row before thedevkitchen_estate_profile/res_users.
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_property WHERE name IN ('US026 Ownership Test Property A', 'US026 Ownership Test Property B');" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_agent WHERE profile_id IN (SELECT id FROM thedevkitchen_estate_profile WHERE email = 'us026_ownership_agent@example.com') OR user_id IN (SELECT u.id FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email = 'us026_ownership_agent@example.com');" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM res_users WHERE login = 'us026_ownership_agent@example.com';" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM thedevkitchen_estate_profile WHERE email = 'us026_ownership_agent@example.com';" >/dev/null 2>&1
}
cleanup

# --- Auth (mesmo padrão dos demais scripts test_us026_*.sh) ---
BEARER_TOKEN=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token" -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"${OAUTH_CLIENT_ID}\",\"client_secret\":\"${OAUTH_CLIENT_SECRET}\"}" \
  | jq -r '.access_token')

LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_MANAGER}\",\"password\":\"${TEST_PASSWORD_MANAGER}\"}")
# /api/v1/users/login has no .data wrapper.
SESSION_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.session_id')
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.user.default_company_id')

if [ -z "$SESSION_ID" ] || [ "$SESSION_ID" = "null" ]; then
  echo "FATAL: manager login failed, cannot proceed. Response: $LOGIN_RESPONSE"
  exit 1
fi

AUTH_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

# Resolve profile_type_id FK (never hardcode the "agent" string).
AGENT_PROFILE_TYPE_ID=$(docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM thedevkitchen_profile_type WHERE code = 'agent' LIMIT 1;" | tr -d '[:space:]')

# 1. Cria profile + convite via o fluxo unificado.
# CPF: 14546511051 -- gerado e validado com validate_docbr.CPF().validate() == True
# dentro do próprio container (script-time check), distinto de todos os CPFs já
# usados neste branch (39053344705, 10433218100, 96001338914, 52998224725,
# 15350946056, 08386379499).
PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Ownership Agent","company_id":'"${COMPANY_ID}"',"document":"14546511051","email":"us026_ownership_agent@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
PROFILE_BODY=$(echo "$PROFILE_RESPONSE" | sed '$d')
PROFILE_STATUS=$(echo "$PROFILE_RESPONSE" | tail -n 1)
assert_status "201" "$PROFILE_STATUS" "profile created for ownership test agent"
# /api/v1/profiles has no .data wrapper.
PROFILE_ID=$(echo "$PROFILE_BODY" | jq -r '.id')

INVITE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${PROFILE_ID}"',"agent":{"creci":"CRECI-SP 222222"}}')
INVITE_BODY=$(echo "$INVITE_RESPONSE" | sed '$d')
INVITE_STATUS=$(echo "$INVITE_RESPONSE" | tail -n 1)
assert_status "201" "$INVITE_STATUS" "invite created (agent user_id upsert path)"
# /api/v1/users/invite DOES wrap in .data.
NEW_USER_ID=$(echo "$INVITE_BODY" | jq -r '.data.id')
NEW_AGENT_ID=$(echo "$INVITE_BODY" | jq -r '.data.agent_id')

if [ -z "$NEW_USER_ID" ] || [ "$NEW_USER_ID" = "null" ] || [ -z "$NEW_AGENT_ID" ] || [ "$NEW_AGENT_ID" = "null" ]; then
  echo "FATAL: invite did not return usable id/agent_id. Response: $INVITE_BODY"
  cleanup
  exit 1
fi
echo "INFO: new_user_id=$NEW_USER_ID new_agent_id=$NEW_AGENT_ID company_id=$COMPANY_ID"

# 2. Força a senha diretamente no banco (mesma técnica de test_us026_s1_rbac_visibility.sh
#    -- o crypt context do Odoo aceita 'plaintext' como scheme legado) e zera signup_pending.
docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
  "UPDATE res_users SET password='ownership_test_pass_026', signup_pending=FALSE WHERE id = ${NEW_USER_ID};" >/dev/null

# 3. Cria Propriedade A, atribuída ao NOVO agente (o caso de sucesso).
docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
  "INSERT INTO real_estate_property (
      name, company_id, agent_id, active,
      property_type_id, country_id, state_id, location_type_id,
      origin_media, property_purpose, zip_code, city, street, street_number,
      property_status, condition, area
   ) VALUES (
      'US026 Ownership Test Property A', ${COMPANY_ID}, ${NEW_AGENT_ID}, TRUE,
      1, 31, 95, 1,
      'website', 'residential', '01310-100', 'São Paulo', 'Rua US026 Ownership A', '1',
      'available', 'good', 100
   );" >/dev/null

PROPERTY_A_ID=$(docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM real_estate_property WHERE name = 'US026 Ownership Test Property A';" | tr -d '[:space:]')
echo "INFO: created property_A_id=$PROPERTY_A_ID assigned to agent_id=$NEW_AGENT_ID"

# 4. Cria Propriedade B, SEM agente atribuído (agent_id nullable, ON DELETE SET NULL
# per real_estate_property_agent_id_fkey) -- o caso negativo. property_record.agent_id
# sendo vazio já basta para cair no ramo "you can only access your own properties" de
# validate_property_access(), sem precisar de um segundo agente real.
docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
  "INSERT INTO real_estate_property (
      name, company_id, agent_id, active,
      property_type_id, country_id, state_id, location_type_id,
      origin_media, property_purpose, zip_code, city, street, street_number,
      property_status, condition, area
   ) VALUES (
      'US026 Ownership Test Property B', ${COMPANY_ID}, NULL, TRUE,
      1, 31, 95, 1,
      'website', 'residential', '01310-100', 'São Paulo', 'Rua US026 Ownership B', '2',
      'available', 'good', 80
   );" >/dev/null

PROPERTY_B_ID=$(docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM real_estate_property WHERE name = 'US026 Ownership Test Property B';" | tr -d '[:space:]')
echo "INFO: created property_B_id=$PROPERTY_B_ID with NO agent assigned"

# 5. Login como o agente recém-convidado.
AGENT_LOGIN=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d '{"login":"us026_ownership_agent@example.com","password":"ownership_test_pass_026"}')
AGENT_SESSION_ID=$(echo "$AGENT_LOGIN" | jq -r '.session_id')  # sem wrapper .data
if [ -z "$AGENT_SESSION_ID" ] || [ "$AGENT_SESSION_ID" = "null" ]; then
  echo "FATAL: invited agent login failed. Response: $AGENT_LOGIN"
  cleanup
  exit 1
fi
AGENT_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${AGENT_SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

# 6. PUT na Propriedade A (a própria do agente) -> deve retornar 200. Isto exercita
# serializers.py:641 (property_record.agent_id.user_id == user) via property_api.py's
# update_property() (operation="write", property_api.py:747).
PUT_A_RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT "${BASE_URL}/api/v1/properties/${PROPERTY_A_ID}" "${AGENT_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Ownership Test Property A - Updated"}')
PUT_A_STATUS=$(echo "$PUT_A_RESPONSE" | tail -n 1)
PUT_A_BODY=$(echo "$PUT_A_RESPONSE" | sed '$d')
assert_status "200" "$PUT_A_STATUS" "invited agent can PUT their own property (ownership check passes)"

TESTS_RUN=$((TESTS_RUN + 1))
if echo "$PUT_A_BODY" | jq -e '.name == "US026 Ownership Test Property A - Updated"' >/dev/null 2>&1; then
  echo "PASS: property A was actually updated (name reflects the PUT)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: property A response does not show the updated name (got: $PUT_A_BODY)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# 7. PUT na Propriedade B (NÃO é do agente) -> deve retornar 403 com error_type
# "access_denied" e a mensagem exata "You can only access your own properties"
# (serializers.py:643), provando que o ramo negativo do ownership check também
# resolve corretamente para este agente criado via o fluxo unificado.
PUT_B_RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT "${BASE_URL}/api/v1/properties/${PROPERTY_B_ID}" "${AGENT_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Ownership Test Property B - Should Not Update"}')
PUT_B_STATUS=$(echo "$PUT_B_RESPONSE" | tail -n 1)
PUT_B_BODY=$(echo "$PUT_B_RESPONSE" | sed '$d')
assert_status "403" "$PUT_B_STATUS" "invited agent is BLOCKED from PUT on a property not assigned to them"

TESTS_RUN=$((TESTS_RUN + 1))
if echo "$PUT_B_BODY" | jq -e '.error == "access_denied" and .message == "You can only access your own properties"' >/dev/null 2>&1; then
  echo "PASS: 403 body carries the exact ownership-check error type + message"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: 403 body does not carry the expected error message (got: $PUT_B_BODY)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# 8. Confirma no banco que a Propriedade B de fato NÃO foi alterada (o 403 realmente
# bloqueou a escrita, não apenas retornou o código errado com side effect).
NAME_B_AFTER=$(docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT name FROM real_estate_property WHERE id = ${PROPERTY_B_ID};")
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$NAME_B_AFTER" | tr -d '[:space:]')" = "US026OwnershipTestPropertyB" ]; then
  echo "PASS: property B name unchanged in DB after the blocked PUT"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: property B name changed despite the 403 (got: $NAME_B_AFTER)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

cleanup
echo ""
echo "=== US026-S1 serializers.py ownership check (FR6.1): $TESTS_PASSED/$TESTS_RUN passed ==="
[ "$TESTS_FAILED" -gt 0 ] && exit 1
exit 0
