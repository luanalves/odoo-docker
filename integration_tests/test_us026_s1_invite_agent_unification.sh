#!/bin/bash
# integration_tests/test_us026_s1_invite_agent_unification.sh
# Feature 026 — User Story 1: convite unificado cria real.estate.agent
# vinculado a profile_id E user_id, com paridade total de campos.
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

assert_field_value() {
  local body="$1" jq_path="$2" expected="$3" label="$4"
  local actual
  actual=$(echo "$body" | jq -r "$jq_path")
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ "$actual" = "$expected" ]; then
    echo "PASS: $label ($jq_path = $actual)"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "FAIL: $label (expected $jq_path = $expected, got $actual)"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

cleanup_test_data() {
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM res_users WHERE login LIKE 'us026_%@example.com';" >/dev/null 2>&1
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM thedevkitchen_estate_profile WHERE email LIKE 'us026_%@example.com';" >/dev/null 2>&1
}

cleanup_test_data

# --- Auth (mesmo padrão de test_us9_s6_resend_invite.sh) ---
BEARER_TOKEN=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"${OAUTH_CLIENT_ID}\",\"client_secret\":\"${OAUTH_CLIENT_SECRET}\"}" \
  | jq -r '.access_token')

LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_MANAGER}\",\"password\":\"${TEST_PASSWORD_MANAGER}\"}")
# CORRIGIDO (achado 2026-07-19): a resposta de /api/v1/users/login NÃO tem wrapper .data —
# os campos vêm direto na raiz, confirmado contra o container ao vivo e contra
# test_us9_s6_resend_invite.sh (que já lê .session_id/.user.default_company_id sem .data).
SESSION_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.session_id')
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.user.default_company_id')

AUTH_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

# --- Resolve o FK inteiro de profile_type_id (achado 2026-07-19: profile_api.py exige um
# inteiro de thedevkitchen_profile_type.id, NÃO a string "agent" — profile_api.py:174-182) ---
AGENT_PROFILE_TYPE_ID=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM thedevkitchen_profile_type WHERE code = 'agent' LIMIT 1;" | tr -d '[:space:]')

# --- Cria o profile (pré-requisito — profile_id continua obrigatório, decisão confirmada).
# NOTA: isso já dispara profile_api.py:236-255, que auto-cria um real_estate_agent para este
# profile_id (sem user_id) — é exatamente esse registro que o convite abaixo deve vincular
# (write), não duplicar (create). Ver o "Achado Crítico" no topo desta task. ---
PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{
    "name": "US026 Agent Pending",
    "company_id": '"${COMPANY_ID}"',
    "document": "39053344705",
    "email": "us026_agent_pending@example.com",
    "birthdate": "1990-01-01",
    "profile_type_id": '"${AGENT_PROFILE_TYPE_ID}"'
  }')
PROFILE_BODY=$(echo "$PROFILE_RESPONSE" | sed '$d')
PROFILE_STATUS=$(echo "$PROFILE_RESPONSE" | tail -n 1)
assert_status "201" "$PROFILE_STATUS" "profile creation"
# NOTE: unlike the invite endpoint (which wraps in {"data": ...}), POST /api/v1/profiles
# returns response.py's success_response(), which puts fields flat at the root (confirmed
# live: GET /api/v1/profiles/<id> and POST both return {"id": ..., "name": ..., ...} with
# no .data wrapper) — same class of discrepancy as the already-fixed login .data issue.
PROFILE_ID=$(echo "$PROFILE_BODY" | jq -r '.id')

# --- Confirma a premissa do achado: profile_api.py já criou um real_estate_agent órfão ---
PRE_EXISTING_COUNT=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM real_estate_agent WHERE profile_id = ${PROFILE_ID};" | tr -d '[:space:]')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$PRE_EXISTING_COUNT" = "1" ]; then
  echo "PASS: profile_api.py auto-created exactly 1 real_estate_agent row for this profile (as expected)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: expected exactly 1 pre-existing real_estate_agent row, got $PRE_EXISTING_COUNT — the achado's premise may no longer hold, investigate before trusting the rest of this script"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Convite com paridade total de campos no nó agent ---
INVITE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{
    "profile_id": '"${PROFILE_ID}"',
    "agent": {
      "creci": "CRECI-SP 999999",
      "hire_date": "2026-01-15",
      "bank_name": "Banco Teste",
      "bank_account": "12345-6",
      "pix_key": "us026_agent_pending@example.com"
    }
  }')
INVITE_BODY=$(echo "$INVITE_RESPONSE" | sed '$d')
INVITE_STATUS=$(echo "$INVITE_RESPONSE" | tail -n 1)
assert_status "201" "$INVITE_STATUS" "invite with agent object"
assert_field_value "$INVITE_BODY" '.data.profile_id' "$PROFILE_ID" "response has profile_id"

AGENT_ID=$(echo "$INVITE_BODY" | jq -r '.data.agent_id')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$AGENT_ID" != "null" ] && [ -n "$AGENT_ID" ]; then
  echo "PASS: response includes agent_id ($AGENT_ID)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: response missing agent_id"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

AGENT_LINK=$(echo "$INVITE_BODY" | jq -r '.links.agent')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$AGENT_LINK" = "/api/v1/agents/${AGENT_ID}" ]; then
  echo "PASS: links.agent present and correct"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: links.agent missing or wrong (got $AGENT_LINK)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Verifica no banco: profile_id E user_id ambos preenchidos no mesmo registro ---
USER_ID=$(echo "$INVITE_BODY" | jq -r '.data.id')
DB_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT profile_id, user_id, creci FROM real_estate_agent WHERE id = ${AGENT_ID};")
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$DB_CHECK" | grep -q "${PROFILE_ID}|${USER_ID}|CRECI-SP 999999"; then
  echo "PASS: real_estate_agent row has BOTH profile_id and user_id set, plus creci"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: real_estate_agent row missing profile_id/user_id/creci (got: $DB_CHECK)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Confirma semântica de upsert: ainda existe SÓ 1 linha para este profile_id (write, não
# um segundo create() duplicado) — e é a MESMA linha que profile_api.py já tinha criado ---
POST_INVITE_COUNT=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM real_estate_agent WHERE profile_id = ${PROFILE_ID};" | tr -d '[:space:]')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$POST_INVITE_COUNT" = "1" ]; then
  echo "PASS: exactly 1 real_estate_agent row for this profile_id after invite (upsert, not duplicate create)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: expected exactly 1 real_estate_agent row after invite, got $POST_INVITE_COUNT (duplicate create() instead of upsert write()?)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

cleanup_test_data

echo ""
echo "=== US026-S1: $TESTS_PASSED/$TESTS_RUN passed ==="
if [ "$TESTS_FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
