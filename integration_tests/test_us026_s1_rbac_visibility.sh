#!/bin/bash
# integration_tests/test_us026_s1_rbac_visibility.sh
# Feature 026 — prova que o agente convidado vê seus próprios imóveis
# (o bug que a Feature 025 deixaria aberto: profile_id setado, user_id não).
#
# Este é o teste mais importante da feature: prova que o user_id corrigido
# (Tasks 4/5, upsert em real.estate.agent no fluxo de convite) realmente
# resolve o problema original -- não apenas que o registro foi criado, mas
# que property_api.py:157-167 (RBAC de agente) o reconhece via
# real.estate.agent.search([('user_id', '=', user.id)]).
#
# Sem Task 4: o agente convidado teria profile_id setado mas user_id NULL
# no registro real.estate.agent (ou um segundo registro duplicado sem
# user_id) -- a busca acima não encontraria nada, domain viraria
# ('id', '=', False), e GET /properties retornaria lista vazia mesmo
# com um imóvel de fato atribuído a esse agente.
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

# Distinct, greppable namespace for this script's test data (us026_rbac_*), so its
# cleanup never collides with test_us026_s1_invite_agent_unification.sh's data
# (which uses the us026_* / us026_agent_pending@ etc. namespace).
cleanup() {
  # FK ordering: real_estate_agent.profile_id / .user_id are ondelete='restrict',
  # so it must be deleted before thedevkitchen_estate_profile / res_users.
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_property WHERE name = 'US026 RBAC Test Property';" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_agent WHERE profile_id IN (SELECT id FROM thedevkitchen_estate_profile WHERE email = 'us026_rbac_agent@example.com') OR user_id IN (SELECT u.id FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email = 'us026_rbac_agent@example.com');" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM res_users WHERE login = 'us026_rbac_agent@example.com';" >/dev/null 2>&1
  docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM thedevkitchen_estate_profile WHERE email = 'us026_rbac_agent@example.com';" >/dev/null 2>&1
}
cleanup

# --- Auth (mesmo padrão de test_us026_s1_invite_agent_unification.sh) ---
BEARER_TOKEN=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token" -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"${OAUTH_CLIENT_ID}\",\"client_secret\":\"${OAUTH_CLIENT_SECRET}\"}" \
  | jq -r '.access_token')

LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_MANAGER}\",\"password\":\"${TEST_PASSWORD_MANAGER}\"}")
# Achado 2026-07-19: /api/v1/users/login não tem wrapper .data -- campos direto na raiz.
SESSION_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.session_id')
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.user.default_company_id')

if [ -z "$SESSION_ID" ] || [ "$SESSION_ID" = "null" ]; then
  echo "FATAL: manager login failed, cannot proceed. Response: $LOGIN_RESPONSE"
  exit 1
fi

AUTH_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

# Resolve o FK inteiro de profile_type_id (achado 2026-07-19, ver Task 4) -- nunca
# hardcoded a string "agent".
AGENT_PROFILE_TYPE_ID=$(docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM thedevkitchen_profile_type WHERE code = 'agent' LIMIT 1;" | tr -d '[:space:]')

# 1. Cria profile + convite.
# CPF: 08386379499 -- gerado e verificado com validate_docbr.CPF().validate() == True
# no próprio container (script-time check), distinto de todos os CPFs já usados em
# test_us026_s1_invite_agent_unification.sh (39053344705, 10433218100, 96001338914,
# 52998224725, 15350946056).
PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 RBAC Agent","company_id":'"${COMPANY_ID}"',"document":"08386379499","email":"us026_rbac_agent@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
PROFILE_BODY=$(echo "$PROFILE_RESPONSE" | sed '$d')
PROFILE_STATUS=$(echo "$PROFILE_RESPONSE" | tail -n 1)
assert_status "201" "$PROFILE_STATUS" "profile created for RBAC test agent"
# /api/v1/profiles também não tem wrapper .data.
PROFILE_ID=$(echo "$PROFILE_BODY" | jq -r '.id')

INVITE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${PROFILE_ID}"',"agent":{"creci":"CRECI-SP 888888"}}')
INVITE_BODY=$(echo "$INVITE_RESPONSE" | sed '$d')
INVITE_STATUS=$(echo "$INVITE_RESPONSE" | tail -n 1)
assert_status "201" "$INVITE_STATUS" "invite created (agent user_id upsert path)"
# /api/v1/users/invite DOES wrap in .data (see Task 4/5).
NEW_USER_ID=$(echo "$INVITE_BODY" | jq -r '.data.id')
NEW_AGENT_ID=$(echo "$INVITE_BODY" | jq -r '.data.agent_id')

if [ -z "$NEW_USER_ID" ] || [ "$NEW_USER_ID" = "null" ] || [ -z "$NEW_AGENT_ID" ] || [ "$NEW_AGENT_ID" = "null" ]; then
  echo "FATAL: invite did not return usable id/agent_id. Response: $INVITE_BODY"
  cleanup
  exit 1
fi
echo "INFO: new_user_id=$NEW_USER_ID new_agent_id=$NEW_AGENT_ID company_id=$COMPANY_ID"

# 2. Força a senha diretamente no banco (o crypt context do Odoo aceita 'plaintext'
#    como scheme legado -- res_users.py:_crypt_context(), ['pbkdf2_sha512','plaintext'] --
#    então não é preciso um hash bcrypt/pbkdf2 real aqui; mesmo padrão de contorno de
#    fluxo de e-mail usado em test_us9_s6_resend_invite.sh, que também zera
#    signup_pending diretamente via SQL).
docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
  "UPDATE res_users SET password='rbac_test_pass_026', signup_pending=FALSE WHERE id = ${NEW_USER_ID};" >/dev/null

# 3. Cria um imóvel atribuído ao NOVO agente.
# NOTA: real_estate_property tem várias colunas NOT NULL sem default (property_type_id,
# country_id, state_id, location_type_id, origin_media, property_purpose, zip_code,
# city, street, street_number, property_status, condition, area) -- o INSERT mínimo do brief
# original (name/company_id/agent_id/active) falharia com not-null violation. Valores
# abaixo replicam um registro real existente (id=43-45, "Property P1-* US5S3"), com
# state_id trocado de 248 (Aveiro/Portugal, country_id=183 -- inconsistente com
# country_id=31/BR daquele registro) para 95 (São Paulo, country_id=31) para manter
# país/estado coerentes.
docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -c \
  "INSERT INTO real_estate_property (
      name, company_id, agent_id, active,
      property_type_id, country_id, state_id, location_type_id,
      origin_media, property_purpose, zip_code, city, street, street_number,
      property_status, condition, area
   ) VALUES (
      'US026 RBAC Test Property', ${COMPANY_ID}, ${NEW_AGENT_ID}, TRUE,
      1, 31, 95, 1,
      'website', 'residential', '01310-100', 'São Paulo', 'Rua US026 RBAC', '1',
      'available', 'good', 100
   );" >/dev/null

PROPERTY_ID=$(docker compose -f "${COMPOSE_FILE}" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM real_estate_property WHERE name = 'US026 RBAC Test Property';" | tr -d '[:space:]')
echo "INFO: created property_id=$PROPERTY_ID assigned to agent_id=$NEW_AGENT_ID"

# 4. Login como o agente recém-convidado.
AGENT_LOGIN=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d '{"login":"us026_rbac_agent@example.com","password":"rbac_test_pass_026"}')
AGENT_SESSION_ID=$(echo "$AGENT_LOGIN" | jq -r '.session_id')  # sem wrapper .data
if [ -z "$AGENT_SESSION_ID" ] || [ "$AGENT_SESSION_ID" = "null" ]; then
  echo "FATAL: invited agent login failed. Response: $AGENT_LOGIN"
  cleanup
  exit 1
fi
AGENT_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${AGENT_SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

# 5. O PRÓPRIO teste da lacuna que a Feature 025 deixaria aberta.
# NOTA: company_ids é um parâmetro OBRIGATÓRIO em GET /properties
# (property_api.py:48-50) -- omiti-lo retornaria 400, não a resposta RBAC que
# queremos exercitar aqui.
PROPERTIES_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "${BASE_URL}/api/v1/properties?company_ids=${COMPANY_ID}" "${AGENT_HEADERS[@]}")
PROPERTIES_STATUS=$(echo "$PROPERTIES_RESPONSE" | tail -n 1)
PROPERTIES_BODY=$(echo "$PROPERTIES_RESPONSE" | sed '$d')
assert_status "200" "$PROPERTIES_STATUS" "invited agent can call GET /properties"

PROPERTY_COUNT=$(echo "$PROPERTIES_BODY" | jq '.data | length')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$PROPERTY_COUNT" -gt 0 ] 2>/dev/null; then
  echo "PASS: invited agent sees $PROPERTY_COUNT own propert(y/ies) -- NOT an empty list"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: invited agent sees ZERO properties -- the exact bug this feature exists to fix (user_id not linked)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# 6. Confirma que a propriedade retornada é de fato a que criamos (não apenas uma
# contagem > 0 coincidente vinda de outro dado residual).
RETURNED_IDS=$(echo "$PROPERTIES_BODY" | jq -r '[.data[].id] | join(",")')
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$PROPERTIES_BODY" | jq -e --argjson pid "$PROPERTY_ID" '.data | any(.id == $pid)' >/dev/null 2>&1; then
  echo "PASS: returned property list includes our assigned property_id=$PROPERTY_ID (returned ids: $RETURNED_IDS)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: returned property list does NOT include our assigned property_id=$PROPERTY_ID (returned ids: $RETURNED_IDS)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

cleanup
echo ""
echo "=== US026-S1 RBAC visibility: $TESTS_PASSED/$TESTS_RUN passed ==="
[ "$TESTS_FAILED" -gt 0 ] && exit 1
exit 0
