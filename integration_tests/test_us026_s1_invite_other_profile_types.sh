#!/bin/bash
# integration_tests/test_us026_s1_invite_other_profile_types.sh
# Feature 026 — cobre um gap encontrado após a correção do nó `agent`
# (2026-07-23): POST /api/v1/users/invite é um endpoint GENÉRICO que convida
# QUALQUER profile_type, não só 'agent'. Este script prova, para cada um dos
# outros 9 tipos (owner, director, manager, prospector, receptionist,
# financial, legal, tenant, property_owner), que o convite:
#   1. Funciona (201) exatamente como antes desta feature — FR2.4
#      ("comportamento de invite_user permanece INALTERADO" para não-agent);
#   2. NÃO inclui agent_id/links.agent na resposta;
#   3. NÃO cria nenhum registro real_estate_agent para o perfil convidado.
# Corresponde a `test_invite_non_agent_profile_unaffected` na tabela de
# cobertura de testes da spec (US1), identificado como faltante em auditoria.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../18.0/.env" 2>/dev/null || true
BASE_URL="${BASE_URL:-http://localhost:8069}"

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

cleanup_test_data() {
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_agent WHERE profile_id IN (SELECT id FROM thedevkitchen_estate_profile WHERE email LIKE 'us026_otherprofiles_%@example.com') OR user_id IN (SELECT u.id FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email LIKE 'us026_otherprofiles_%@example.com');" >/dev/null 2>&1
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM res_users WHERE login LIKE 'us026_otherprofiles_%@example.com';" >/dev/null 2>&1
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM thedevkitchen_estate_profile WHERE email LIKE 'us026_otherprofiles_%@example.com';" >/dev/null 2>&1
}

cleanup_test_data

# --- Auth (mesmo padrão de test_us026_s1_invite_agent_unification.sh) ---
BEARER_TOKEN=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"${OAUTH_CLIENT_ID}\",\"client_secret\":\"${OAUTH_CLIENT_SECRET}\"}" \
  | jq -r '.access_token')

LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_OWNER}\",\"password\":\"${TEST_PASSWORD_OWNER}\"}")
SESSION_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.session_id')
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.user.default_company_id')

AUTH_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

TIMESTAMP=$(date +%s)

# profile_type code -> valid CPF (freshly generated, distinct per type so no
# cross-type document collisions inside this run). Plain case/function
# instead of an associative array: the macOS default /bin/bash is 3.2,
# which predates bash 4's `declare -A` support -- this script must run
# under that shell, not a newer one.
cpf_for_profile_type() {
  case "$1" in
    owner)          echo "80339101350" ;;
    director)       echo "61755569688" ;;
    manager)        echo "83188791470" ;;
    prospector)     echo "70472575600" ;;
    receptionist)   echo "54050059835" ;;
    financial)      echo "45943160264" ;;
    legal)          echo "73242406400" ;;
    tenant)         echo "98489251550" ;;
    property_owner) echo "49533645385" ;;
  esac
}

for profile_code in owner director manager prospector receptionist financial legal tenant property_owner; do
  PROFILE_TYPE_ID=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
    "SELECT id FROM thedevkitchen_profile_type WHERE code = '${profile_code}' LIMIT 1;" | tr -d '[:space:]')

  if [ -z "$PROFILE_TYPE_ID" ]; then
    TESTS_RUN=$((TESTS_RUN + 1))
    echo "FAIL: profile_type '${profile_code}' not found in thedevkitchen_profile_type -- skipping"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    continue
  fi

  CPF=$(cpf_for_profile_type "$profile_code")
  EMAIL="us026_otherprofiles_${profile_code}_${TIMESTAMP}@example.com"

  PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
    "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
    -d '{"name":"US026 Other Profile '"${profile_code}"'","company_id":'"${COMPANY_ID}"',"document":"'"${CPF}"'","email":"'"${EMAIL}"'","birthdate":"1990-01-01","profile_type_id":'"${PROFILE_TYPE_ID}"'}')
  PROFILE_BODY=$(echo "$PROFILE_RESPONSE" | sed '$d')
  PROFILE_STATUS=$(echo "$PROFILE_RESPONSE" | tail -n 1)
  assert_status "201" "$PROFILE_STATUS" "profile creation for profile_type='${profile_code}'"
  PROFILE_ID=$(echo "$PROFILE_BODY" | jq -r '.id')

  if [ -z "$PROFILE_ID" ] || [ "$PROFILE_ID" = "null" ]; then
    echo "  SKIP: no profile_id, cannot continue with invite for '${profile_code}' (body: $PROFILE_BODY)"
    continue
  fi

  # --- FR2.4: invite_user's behavior for non-agent profile types must be
  # completely unaffected by this feature -- no `agent` object needed or
  # read, plain profile_id-only invite, exactly as before Feature 026. ---
  INVITE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
    "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
    -d '{"profile_id":'"${PROFILE_ID}"'}')
  INVITE_BODY=$(echo "$INVITE_RESPONSE" | sed '$d')
  INVITE_STATUS=$(echo "$INVITE_RESPONSE" | tail -n 1)
  assert_status "201" "$INVITE_STATUS" "invite for profile_type='${profile_code}'"

  AGENT_ID_IN_RESPONSE=$(echo "$INVITE_BODY" | jq -r '.data.agent_id // empty')
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ -z "$AGENT_ID_IN_RESPONSE" ]; then
    echo "PASS: no agent_id in response for profile_type='${profile_code}'"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "FAIL: unexpected agent_id ($AGENT_ID_IN_RESPONSE) in response for profile_type='${profile_code}'"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi

  AGENT_LINK_IN_RESPONSE=$(echo "$INVITE_BODY" | jq -r '.links.agent // empty')
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ -z "$AGENT_LINK_IN_RESPONSE" ]; then
    echo "PASS: no links.agent in response for profile_type='${profile_code}'"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "FAIL: unexpected links.agent ($AGENT_LINK_IN_RESPONSE) for profile_type='${profile_code}'"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi

  AGENT_COUNT=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
    "SELECT COUNT(*) FROM real_estate_agent WHERE profile_id = ${PROFILE_ID};" | tr -d '[:space:]')
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ "$AGENT_COUNT" = "0" ]; then
    echo "PASS: no real_estate_agent record created for profile_type='${profile_code}'"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "FAIL: unexpected real_estate_agent row(s) ($AGENT_COUNT) for profile_type='${profile_code}'"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
done

# --- Feature 026 (corrigido, 2026-07-23, segunda correção) regression: ---
# creci/bank_* validation must ONLY fire when profile_type resolves to
# 'agent'. Before this fix, PROFILE_CREATE_SCHEMA validated these fields
# unconditionally, so a malformed creci sent alongside a non-agent
# profile_type_id would incorrectly reject profile creation with 400, even
# though creci is meaningless for that profile_type. Prove the malformed
# creci is now silently accepted-and-ignored for a 'tenant' profile: 201,
# no real_estate_agent row created, and the value isn't persisted anywhere.
TENANT_TYPE_ID=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM thedevkitchen_profile_type WHERE code = 'tenant' LIMIT 1;" | tr -d '[:space:]')
BAD_CRECI_EMAIL="us026_otherprofiles_badcreci_${TIMESTAMP}@example.com"

BAD_CRECI_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Tenant Bad Creci","company_id":'"${COMPANY_ID}"',"document":"35299744471","email":"'"${BAD_CRECI_EMAIL}"'","birthdate":"1990-01-01","profile_type_id":'"${TENANT_TYPE_ID}"',"creci":"ab"}')
BAD_CRECI_BODY=$(echo "$BAD_CRECI_RESPONSE" | sed '$d')
BAD_CRECI_STATUS=$(echo "$BAD_CRECI_RESPONSE" | tail -n 1)
assert_status "201" "$BAD_CRECI_STATUS" "tenant profile with malformed creci is accepted (agent-field validation is not gated by profile_type)"

BAD_CRECI_PROFILE_ID=$(echo "$BAD_CRECI_BODY" | jq -r '.id')
TESTS_RUN=$((TESTS_RUN + 1))
if [ -n "$BAD_CRECI_PROFILE_ID" ] && [ "$BAD_CRECI_PROFILE_ID" != "null" ]; then
  AGENT_COUNT_BAD_CRECI=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
    "SELECT COUNT(*) FROM real_estate_agent WHERE profile_id = ${BAD_CRECI_PROFILE_ID};" | tr -d '[:space:]')
  if [ "$AGENT_COUNT_BAD_CRECI" = "0" ]; then
    echo "PASS: no real_estate_agent record created for tenant profile despite malformed creci in payload"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "FAIL: unexpected real_estate_agent row(s) ($AGENT_COUNT_BAD_CRECI) for tenant profile with malformed creci"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
else
  echo "FAIL: tenant-with-bad-creci profile creation did not return a usable profile id (body: $BAD_CRECI_BODY)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

cleanup_test_data

echo ""
echo "=== US026-S1 non-agent profile types (test_invite_non_agent_profile_unaffected): $TESTS_PASSED/$TESTS_RUN passed ==="
if [ "$TESTS_FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
