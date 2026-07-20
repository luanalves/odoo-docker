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
  # NOTE (found while adding Task 5 scenarios): real_estate_agent.profile_id and
  # .user_id are both ondelete='restrict' FKs (confirmed via pg_constraint:
  # confdeltype='r' on real_estate_agent_profile_id_fkey/real_estate_agent_user_id_fkey).
  # Every scenario in this script creates an agent-type profile, which always ends up
  # with a linked real_estate_agent row (auto-created by profile_api.py and/or
  # upserted by the invite controller) -- so the two DELETEs below used to fail
  # silently (stderr redirected to /dev/null) whenever a prior run's agent row was
  # still around, leaving orphaned res_users/profile rows that then made the NEXT
  # run's profile creation return 409 instead of 201. Deleting real_estate_agent
  # first (scoped to both profile_id and user_id, since the two aren't always the
  # same set after a failed/partial run) clears the FK block before the rest.
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_agent WHERE profile_id IN (SELECT id FROM thedevkitchen_estate_profile WHERE email LIKE 'us026_%@example.com') OR user_id IN (SELECT u.id FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email LIKE 'us026_%@example.com');" >/dev/null 2>&1
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

# --- Cenário: agent.creci mal formado -> 400, nenhum registro criado ---
BAD_CRECI_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Bad Creci","company_id":'"${COMPANY_ID}"',"document":"52998224725","email":"us026_bad_creci@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
BAD_CRECI_PROFILE_BODY=$(echo "$BAD_CRECI_RESPONSE" | sed '$d')
BAD_CRECI_PROFILE_STATUS=$(echo "$BAD_CRECI_RESPONSE" | tail -n 1)
assert_status "201" "$BAD_CRECI_PROFILE_STATUS" "profile creation for bad creci scenario"
BAD_CRECI_PROFILE_ID=$(echo "$BAD_CRECI_PROFILE_BODY" | jq -r '.id')

INVALID_INVITE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${BAD_CRECI_PROFILE_ID}"',"agent":{"creci":"ab"}}')
INVALID_INVITE_STATUS=$(echo "$INVALID_INVITE" | tail -n 1)
assert_status "400" "$INVALID_INVITE_STATUS" "creci too short returns 400"

# Atomicidade (FR2.2): nenhum res.users deve ter sido criado para este profile
ATOMIC_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email = 'us026_bad_creci@example.com';")
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$ATOMIC_CHECK" | tr -d '[:space:]')" = "0" ]; then
  echo "PASS: atomic rollback — no res.users created after creci validation failure"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: atomic rollback — a res.users row exists despite the 400 (got count: $ATOMIC_CHECK)"
  echo "  ACTION IF THIS FAILS: add request.env.cr.rollback() before the 409/400 return"
  echo "  inside invite_controller.py's new agent-creation except block, then re-run."
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Cenário: CRECI duplicado na mesma empresa -> 409 ---
# NOTE: brief's original CPFs for this pair (91129418804 / 74954510736) fail CPF
# checksum validation (validators.validate_document via validate_docbr, confirmed
# live: cpf.validate() returns False for both) -- profile creation would 400/409
# on document validation before ever reaching the invite step. Replaced with
# freshly generated, checksum-valid CPFs (confirmed cpf.validate()==True and no
# collision with any existing profile under this test's company_id).
DUP_PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Dup Creci","company_id":'"${COMPANY_ID}"',"document":"15350946056","email":"us026_dup_creci@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
DUP_PROFILE_BODY=$(echo "$DUP_PROFILE_RESPONSE" | sed '$d')
DUP_PROFILE_STATUS=$(echo "$DUP_PROFILE_RESPONSE" | tail -n 1)
assert_status "201" "$DUP_PROFILE_STATUS" "profile creation for duplicate creci scenario (profile 1)"
DUP_PROFILE_ID=$(echo "$DUP_PROFILE_BODY" | jq -r '.id')

FIRST_INVITE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${DUP_PROFILE_ID}"',"agent":{"creci":"CRECI-SP 555555"}}')
FIRST_INVITE_STATUS=$(echo "$FIRST_INVITE" | tail -n 1)
assert_status "201" "$FIRST_INVITE_STATUS" "first invite establishes creci"

DUP_PROFILE2_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Dup Creci 2","company_id":'"${COMPANY_ID}"',"document":"10433218100","email":"us026_dup_creci_2@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
DUP_PROFILE2_BODY=$(echo "$DUP_PROFILE2_RESPONSE" | sed '$d')
DUP_PROFILE2_STATUS=$(echo "$DUP_PROFILE2_RESPONSE" | tail -n 1)
assert_status "201" "$DUP_PROFILE2_STATUS" "profile creation for duplicate creci scenario (profile 2)"
DUP_PROFILE2_ID=$(echo "$DUP_PROFILE2_BODY" | jq -r '.id')

DUP_INVITE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${DUP_PROFILE2_ID}"',"agent":{"creci":"CRECI-SP 555555"}}')
DUP_INVITE_STATUS=$(echo "$DUP_INVITE" | tail -n 1)
assert_status "409" "$DUP_INVITE_STATUS" "duplicate creci in same company returns 409"

# Atomicidade (FR2.2): profile 2's invite created a res.users row (create_user_from_profile
# succeeded) BEFORE _upsert_agent_for_invite's write() tripped the company-scoped CRECI
# uniqueness constraint in agent.py's _check_creci_format -- this is the scenario that
# actually exercises invite_controller.py's request.env.cr.rollback() (unlike the "bad
# creci" scenario above, which fails schema validation before any res.users row is ever
# created, so its atomicity check passes trivially and would not catch a deleted rollback).
DUP_ATOMIC_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email = 'us026_dup_creci_2@example.com';")
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$DUP_ATOMIC_CHECK" | tr -d '[:space:]')" = "0" ]; then
  echo "PASS: atomic rollback — no orphaned res.users left for profile 2 despite create_user_from_profile succeeding before the CRECI constraint fired"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: atomic rollback — a res.users row exists for profile 2 despite the 409 (got count: $DUP_ATOMIC_CHECK)"
  echo "  ACTION IF THIS FAILS: confirm request.env.cr.rollback() is still called in"
  echo "  invite_controller.py's except ValidationError block around _upsert_agent_for_invite."
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Cenário: cliente envia company_id/user_id no nó agent -> ignorados silenciosamente ---
# NOTE: brief's original CPF (74954510736) is also checksum-invalid, replaced for the
# same reason as above (96001338914, confirmed valid and non-colliding).
SPOOF_PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Spoof Test","company_id":'"${COMPANY_ID}"',"document":"96001338914","email":"us026_spoof@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
SPOOF_PROFILE_BODY=$(echo "$SPOOF_PROFILE_RESPONSE" | sed '$d')
SPOOF_PROFILE_STATUS=$(echo "$SPOOF_PROFILE_RESPONSE" | tail -n 1)
assert_status "201" "$SPOOF_PROFILE_STATUS" "profile creation for spoofing scenario"
SPOOF_PROFILE_ID=$(echo "$SPOOF_PROFILE_BODY" | jq -r '.id')

SPOOF_INVITE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${SPOOF_PROFILE_ID}"',"agent":{"company_id":999999,"user_id":999999,"creci":"CRECI-SP 777777"}}')
SPOOF_STATUS=$(echo "$SPOOF_INVITE" | tail -n 1)
assert_status "201" "$SPOOF_STATUS" "company_id/user_id in agent node do not cause a 400"

SPOOF_AGENT_ID=$(echo "$SPOOF_INVITE" | sed '$d' | jq -r '.data.agent_id')
SPOOF_USER_ID=$(echo "$SPOOF_INVITE" | sed '$d' | jq -r '.data.id')
SPOOF_DB_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT company_id FROM real_estate_agent WHERE id = ${SPOOF_AGENT_ID};")
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$SPOOF_DB_CHECK" | tr -d '[:space:]')" = "${COMPANY_ID}" ]; then
  echo "PASS: spoofed company_id (999999) ignored, real company_id (${COMPANY_ID}) persisted"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: company_id spoofing NOT blocked (got: $SPOOF_DB_CHECK, expected ${COMPANY_ID})"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Parallel check (Minor finding #2): user_id in the agent node must also be ignored,
# not just company_id -- persisted user_id must match the real invited user (SPOOF_USER_ID,
# from the invite response's .data.id), not the spoofed 999999 ---
SPOOF_USER_ID_DB_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT user_id FROM real_estate_agent WHERE id = ${SPOOF_AGENT_ID};")
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$SPOOF_USER_ID_DB_CHECK" | tr -d '[:space:]')" = "${SPOOF_USER_ID}" ]; then
  echo "PASS: spoofed user_id (999999) ignored, real invited user_id (${SPOOF_USER_ID}) persisted"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: user_id spoofing NOT blocked (got: $SPOOF_USER_ID_DB_CHECK, expected ${SPOOF_USER_ID})"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

cleanup_test_data

echo ""
echo "=== US026-S1: $TESTS_PASSED/$TESTS_RUN passed ==="
if [ "$TESTS_FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
