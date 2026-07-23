#!/bin/bash
# integration_tests/test_us026_s1_invite_agent_unification.sh
# Feature 026 (corrigido, 2026-07-23) — User Story 1: convite unificado
# vincula user_id ao real.estate.agent que POST /api/v1/profiles já criou.
#
# CORREÇÃO DE ARQUITETURA (2026-07-23): campos exclusivos de agente
# (creci/bank_name/bank_account/pix_key) foram MOVIDOS de POST /api/v1/
# users/invite para POST /api/v1/profiles -- eles não dependem do login
# existir, então não faz sentido esperar o convite para o agente nascer
# completo. O nó `agent` foi REMOVIDO inteiramente do corpo do convite;
# POST /api/v1/users/invite agora só aceita profile_id, igual para
# qualquer profile_type. Este script foi reescrito para refletir isso --
# os cenários de CRECI (formato inválido, duplicado) agora são testados
# no CADASTRO do perfil, não no convite.
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
  # real_estate_agent.profile_id/.user_id are both ondelete='restrict' FKs --
  # delete agent rows first (scoped to both profile_id and user_id) to clear
  # the FK block before deleting res_users/profiles from a prior run.
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_agent WHERE profile_id IN (SELECT id FROM thedevkitchen_estate_profile WHERE email LIKE 'us026_%@example.com') OR user_id IN (SELECT u.id FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email LIKE 'us026_%@example.com');" >/dev/null 2>&1
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM res_users WHERE login LIKE 'us026_%@example.com';" >/dev/null 2>&1
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM thedevkitchen_estate_profile WHERE email LIKE 'us026_%@example.com';" >/dev/null 2>&1
  # Legacy agent row seeded (no profile_id/user_id) by the CPF-collision
  # scenario further down -- not covered by the email-based WHERE clauses
  # above.
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
    "DELETE FROM real_estate_agent WHERE cpf = '03120823040' AND profile_id IS NULL;" >/dev/null 2>&1
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
SESSION_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.session_id')
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.user.default_company_id')

AUTH_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${SESSION_ID}" -H "X-Company-ID: ${COMPANY_ID}")

# --- Resolve o FK inteiro de profile_type_id (profile_api.py exige um
# inteiro de thedevkitchen_profile_type.id, NÃO a string "agent") ---
AGENT_PROFILE_TYPE_ID=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT id FROM thedevkitchen_profile_type WHERE code = 'agent' LIMIT 1;" | tr -d '[:space:]')

# ============================================================
# Cenário 1: caminho feliz -- creci/bank fields no CADASTRO do
# perfil, convite só com profile_id, real_estate_agent nasce
# completo (profile_id + creci + bank) e ganha user_id no convite.
# ============================================================
PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{
    "name": "US026 Agent Pending",
    "company_id": '"${COMPANY_ID}"',
    "document": "39053344705",
    "email": "us026_agent_pending@example.com",
    "birthdate": "1990-01-01",
    "profile_type_id": '"${AGENT_PROFILE_TYPE_ID}"',
    "creci": "CRECI-SP 999999",
    "hire_date": "2026-01-15",
    "bank_name": "Banco Teste",
    "bank_account": "12345-6",
    "pix_key": "us026_agent_pending@example.com"
  }')
PROFILE_BODY=$(echo "$PROFILE_RESPONSE" | sed '$d')
PROFILE_STATUS=$(echo "$PROFILE_RESPONSE" | tail -n 1)
assert_status "201" "$PROFILE_STATUS" "profile creation with creci/bank fields"
PROFILE_ID=$(echo "$PROFILE_BODY" | jq -r '.id')

# --- Confirma: o real_estate_agent já nasce com creci preenchido, ANTES do convite ---
PRE_INVITE_DB_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT profile_id, user_id, creci FROM real_estate_agent WHERE profile_id = ${PROFILE_ID};")
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$PRE_INVITE_DB_CHECK" | grep -q "${PROFILE_ID}||CRECI-SP 999999"; then
  echo "PASS: real_estate_agent already has profile_id + creci at profile-creation time, user_id still null"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: real_estate_agent missing profile_id/creci right after profile creation (got: $PRE_INVITE_DB_CHECK)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Convite: só profile_id, sem nó agent nenhum ---
INVITE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id": '"${PROFILE_ID}"'}')
INVITE_BODY=$(echo "$INVITE_RESPONSE" | sed '$d')
INVITE_STATUS=$(echo "$INVITE_RESPONSE" | tail -n 1)
assert_status "201" "$INVITE_STATUS" "invite with only profile_id"
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

# --- Verifica no banco: profile_id, user_id E creci todos preenchidos no mesmo registro ---
USER_ID=$(echo "$INVITE_BODY" | jq -r '.data.id')
DB_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT profile_id, user_id, creci FROM real_estate_agent WHERE id = ${AGENT_ID};")
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$DB_CHECK" | grep -q "${PROFILE_ID}|${USER_ID}|CRECI-SP 999999"; then
  echo "PASS: real_estate_agent row has profile_id, user_id AND creci (set at profile creation, untouched by invite)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: real_estate_agent row missing profile_id/user_id/creci (got: $DB_CHECK)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# --- Confirma semântica de upsert: ainda existe SÓ 1 linha para este profile_id ---
POST_INVITE_COUNT=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM real_estate_agent WHERE profile_id = ${PROFILE_ID};" | tr -d '[:space:]')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$POST_INVITE_COUNT" = "1" ]; then
  echo "PASS: exactly 1 real_estate_agent row for this profile_id after invite (upsert, not duplicate create)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: expected exactly 1 real_estate_agent row after invite, got $POST_INVITE_COUNT"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# ============================================================
# Cenário 2: creci mal formado -> 400 NO CADASTRO DO PERFIL
# (não mais no convite -- o nó agent do convite não existe mais).
# ============================================================
BAD_CRECI_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Bad Creci","company_id":'"${COMPANY_ID}"',"document":"52998224725","email":"us026_bad_creci@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"',"creci":"ab"}')
BAD_CRECI_STATUS=$(echo "$BAD_CRECI_RESPONSE" | tail -n 1)
assert_status "400" "$BAD_CRECI_STATUS" "creci too short returns 400 at profile creation"

# Atomicidade: nem o profile nem o agent devem ter sido criados
BAD_CRECI_PROFILE_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM thedevkitchen_estate_profile WHERE email = 'us026_bad_creci@example.com';")
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$BAD_CRECI_PROFILE_CHECK" | tr -d '[:space:]')" = "0" ]; then
  echo "PASS: atomic rollback — no profile created after creci validation failure"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: atomic rollback — a profile row exists despite the 400 (got count: $BAD_CRECI_PROFILE_CHECK)"
  echo "  ACTION IF THIS FAILS: confirm request.env.cr.rollback() is still called in"
  echo "  profile_api.py's except ValidationError block."
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# ============================================================
# Cenário 3: CRECI duplicado na mesma empresa -> 409 NO CADASTRO
# DO SEGUNDO PERFIL (não mais no convite).
# ============================================================
DUP_PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Dup Creci","company_id":'"${COMPANY_ID}"',"document":"15350946056","email":"us026_dup_creci@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"',"creci":"CRECI-SP 555555"}')
DUP_PROFILE_STATUS=$(echo "$DUP_PROFILE_RESPONSE" | tail -n 1)
assert_status "201" "$DUP_PROFILE_STATUS" "profile 1 creation establishes creci CRECI-SP 555555"

DUP_PROFILE2_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Dup Creci 2","company_id":'"${COMPANY_ID}"',"document":"10433218100","email":"us026_dup_creci_2@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"',"creci":"CRECI-SP 555555"}')
DUP_PROFILE2_STATUS=$(echo "$DUP_PROFILE2_RESPONSE" | tail -n 1)
assert_status "409" "$DUP_PROFILE2_STATUS" "profile 2 creation with duplicate creci returns 409"

# Atomicidade: profile 2 must not have been left behind despite the agent-level 409
DUP_PROFILE2_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM thedevkitchen_estate_profile WHERE email = 'us026_dup_creci_2@example.com';")
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$DUP_PROFILE2_CHECK" | tr -d '[:space:]')" = "0" ]; then
  echo "PASS: atomic rollback — profile 2 not left behind despite the duplicate-creci 409"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: atomic rollback — profile 2 row exists despite the 409 (got count: $DUP_PROFILE2_CHECK)"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# ============================================================
# Cenário 4: cliente envia profile_id inexistente/extra keys no
# corpo do convite -- ignorados silenciosamente (o endpoint só
# lê profile_id; qualquer outra chave é um no-op, igual antes).
# ============================================================
SPOOF_PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Spoof Test","company_id":'"${COMPANY_ID}"',"document":"96001338914","email":"us026_spoof@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"',"creci":"CRECI-SP 777777"}')
SPOOF_PROFILE_BODY=$(echo "$SPOOF_PROFILE_RESPONSE" | sed '$d')
SPOOF_PROFILE_STATUS=$(echo "$SPOOF_PROFILE_RESPONSE" | tail -n 1)
assert_status "201" "$SPOOF_PROFILE_STATUS" "profile creation for spoofing scenario"
SPOOF_PROFILE_ID=$(echo "$SPOOF_PROFILE_BODY" | jq -r '.id')

SPOOF_INVITE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${SPOOF_PROFILE_ID}"',"company_id":999999,"user_id":999999}')
SPOOF_STATUS=$(echo "$SPOOF_INVITE" | tail -n 1)
assert_status "201" "$SPOOF_STATUS" "top-level company_id/user_id in invite body do not cause a 400 (silently ignored)"

SPOOF_AGENT_ID=$(echo "$SPOOF_INVITE" | sed '$d' | jq -r '.data.agent_id')
SPOOF_USER_ID=$(echo "$SPOOF_INVITE" | sed '$d' | jq -r '.data.id')
SPOOF_DB_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT company_id, user_id FROM real_estate_agent WHERE id = ${SPOOF_AGENT_ID};")
TESTS_RUN=$((TESTS_RUN + 1))
if echo "$SPOOF_DB_CHECK" | grep -q "${COMPANY_ID}|${SPOOF_USER_ID}"; then
  echo "PASS: spoofed company_id/user_id (999999) ignored -- real company_id (${COMPANY_ID}) and invited user_id (${SPOOF_USER_ID}) persisted"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: company_id/user_id spoofing NOT blocked (got: $SPOOF_DB_CHECK, expected ${COMPANY_ID}|${SPOOF_USER_ID})"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# ============================================================
# Cenário 5: colisão de CPF contra um agente legado (sem
# profile_id/user_id) -- exercita o ramo defensivo de create()
# em _link_agent_to_invited_user, não a validação de creci.
# ============================================================
CPF_COLLISION_PROFILE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Cpf Collision","company_id":'"${COMPANY_ID}"',"document":"03120823040","email":"us026_cpf_collision@example.com","birthdate":"1990-01-01","profile_type_id":'"${AGENT_PROFILE_TYPE_ID}"'}')
CPF_COLLISION_PROFILE_BODY=$(echo "$CPF_COLLISION_PROFILE_RESPONSE" | sed '$d')
CPF_COLLISION_PROFILE_STATUS=$(echo "$CPF_COLLISION_PROFILE_RESPONSE" | tail -n 1)
assert_status "201" "$CPF_COLLISION_PROFILE_STATUS" "profile creation for CPF collision scenario"
CPF_COLLISION_PROFILE_ID=$(echo "$CPF_COLLISION_PROFILE_BODY" | jq -r '.id')

# profile_api.py's own auto-create already created a bare real_estate_agent
# for this profile with cpf=03120823040 -- delete it so we can seed a
# DIFFERENT, unrelated legacy agent with the SAME cpf in the same company
# without hitting the collision at seed time itself.
docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
  "DELETE FROM real_estate_agent WHERE profile_id = ${CPF_COLLISION_PROFILE_ID};" >/dev/null 2>&1

# Seed a legacy real_estate_agent row (no profile_id/user_id -- simulating
# data that predates this feature) with the SAME cpf, same company.
docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -c \
  "INSERT INTO real_estate_agent (company_id, name, cpf, hire_date, active) VALUES (${COMPANY_ID}, 'US026 Legacy Agent Cpf Collision', '03120823040', '2020-01-01', true);" >/dev/null 2>&1

# Invite the profile -- the defensive create() branch of
# _link_agent_to_invited_user fires (no bare agent left for this profile_id
# after the delete above), and real.estate.agent.create()'s setdefault()
# fills cpf from profile.document (03120823040), colliding with the legacy
# row above -> 409, not 500.
CPF_COLLISION_INVITE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"profile_id":'"${CPF_COLLISION_PROFILE_ID}"'}')
CPF_COLLISION_INVITE_STATUS=$(echo "$CPF_COLLISION_INVITE" | tail -n 1)
assert_status "409" "$CPF_COLLISION_INVITE_STATUS" "cpf collision against a legacy agent row returns 409 (not 500)"

# Atomicidade (FR2.2): create_user_from_profile succeeded (creating a
# res.users row) BEFORE _link_agent_to_invited_user's create() tripped the
# DB-level UNIQUE(cpf, company_id) constraint; no res.users row should
# remain for the failed invite.
CPF_COLLISION_ATOMIC_CHECK=$(docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc \
  "SELECT COUNT(*) FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email = 'us026_cpf_collision@example.com';")
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$(echo "$CPF_COLLISION_ATOMIC_CHECK" | tr -d '[:space:]')" = "0" ]; then
  echo "PASS: atomic rollback — no orphaned res.users left despite create_user_from_profile succeeding before the CPF constraint fired"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: atomic rollback — a res.users row exists despite the 409 (got count: $CPF_COLLISION_ATOMIC_CHECK)"
  echo "  ACTION IF THIS FAILS: confirm request.env.cr.rollback() is still called in"
  echo "  invite_controller.py's except psycopg2.IntegrityError block around _link_agent_to_invited_user."
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

cleanup_test_data

echo ""
echo "=== US026-S1: $TESTS_PASSED/$TESTS_RUN passed ==="
if [ "$TESTS_FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
