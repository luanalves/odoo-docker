#!/bin/bash
# integration_tests/test_us026_s1_profile_invite_matrix.sh
# Feature 026 -- happy/unhappy path matrix requested by the solicitante on
# top of the already-shipped fix (agent-field validation scoped to
# profile_type='agent'). Covers the three endpoints this feature touches:
#   A. GET  /api/v1/profile-types
#   B. POST /api/v1/profiles      (create, all 10 profile_type codes)
#   C. POST /api/v1/users/invite
# Each section has a happy-path block and a matching unhappy-path block, so
# regressions in either direction (over-permissive or over-strict) are
# caught. Doesn't re-test agent-field-scoping itself -- that's already
# covered by test_us026_s1_invite_other_profile_types.sh's dedicated
# "tenant with malformed creci" case.
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

assert_true() {
  local condition="$1" label="$2"
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ "$condition" = "true" ]; then
    echo "PASS: $label"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo "FAIL: $label"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

psql_exec() {
  docker compose -f "${SCRIPT_DIR}/../18.0/docker-compose.yml" exec -T db psql -U odoo -d realestate -tAc "$1"
}

cleanup_test_data() {
  psql_exec "DELETE FROM real_estate_agent WHERE profile_id IN (SELECT id FROM thedevkitchen_estate_profile WHERE email LIKE 'us026_matrix_%@example.com') OR user_id IN (SELECT u.id FROM res_users u JOIN res_partner p ON u.partner_id = p.id WHERE p.email LIKE 'us026_matrix_%@example.com');" >/dev/null 2>&1
  psql_exec "DELETE FROM res_users WHERE login LIKE 'us026_matrix_%@example.com';" >/dev/null 2>&1
  psql_exec "DELETE FROM thedevkitchen_estate_profile WHERE email LIKE 'us026_matrix_%@example.com';" >/dev/null 2>&1
}

cleanup_test_data

# --- Auth: owner (company 5, most-privileged), agent (company 5, least-
# privileged of the seeded roles), owner-B (company 7, for cross-company). ---
BEARER_TOKEN=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"${OAUTH_CLIENT_ID}\",\"client_secret\":\"${OAUTH_CLIENT_SECRET}\"}" \
  | jq -r '.access_token')

OWNER_LOGIN=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" \
  -H "Content-Type: application/json" -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_OWNER}\",\"password\":\"${TEST_PASSWORD_OWNER}\"}")
OWNER_SESSION=$(echo "$OWNER_LOGIN" | jq -r '.session_id')
OWNER_COMPANY=$(echo "$OWNER_LOGIN" | jq -r '.user.default_company_id')
OWNER_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${OWNER_SESSION}" -H "X-Company-ID: ${OWNER_COMPANY}")

AGENT_LOGIN=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" \
  -H "Content-Type: application/json" -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_AGENT}\",\"password\":\"${TEST_PASSWORD_AGENT}\"}")
AGENT_SESSION=$(echo "$AGENT_LOGIN" | jq -r '.session_id')
AGENT_COMPANY=$(echo "$AGENT_LOGIN" | jq -r '.user.default_company_id')
AGENT_HEADERS=(-H "Authorization: Bearer ${BEARER_TOKEN}" -H "X-Openerp-Session-Id: ${AGENT_SESSION}" -H "X-Company-ID: ${AGENT_COMPANY}")

OWNER_B_LOGIN=$(curl -s -X POST "${BASE_URL}/api/v1/users/login" \
  -H "Content-Type: application/json" -H "Authorization: Bearer ${BEARER_TOKEN}" \
  -d "{\"login\":\"${TEST_USER_OWNER_B}\",\"password\":\"${TEST_PASSWORD_OWNER_B}\"}")
OWNER_B_COMPANY=$(echo "$OWNER_B_LOGIN" | jq -r '.user.default_company_id')

TIMESTAMP=$(date +%s)
CRECI_NUM=$((TIMESTAMP % 90000 + 10000))

# profile_type code -> freshly generated valid CPF, one per code so no
# cross-type document collisions inside this run. Plain case/function
# instead of an associative array: macOS ships bash 3.2, which predates
# bash 4's `declare -A`.
cpf_for_profile_type() {
  case "$1" in
    owner)           echo "01836572093" ;;
    director)        echo "80633430005" ;;
    manager)         echo "47728566920" ;;
    agent)           echo "51287738176" ;;
    prospector)      echo "15725000770" ;;
    receptionist)    echo "14181432513" ;;
    financial)       echo "32206817195" ;;
    legal)           echo "10627187633" ;;
    tenant)          echo "88768720602" ;;
    property_owner)  echo "44412611108" ;;
    rbac_forbidden)  echo "63373285232" ;;
    cross_company)   echo "05133811209" ;;
  esac
}

profile_type_id_for_code() {
  psql_exec "SELECT id FROM thedevkitchen_profile_type WHERE code = '$1' LIMIT 1;" | tr -d '[:space:]'
}

echo ""
echo "===== A. GET /api/v1/profile-types ====="

# A1 (happy): authenticated request lists active profile types.
A1_RESPONSE=$(curl -s -w "\n%{http_code}" "${BASE_URL}/api/v1/profile-types" "${OWNER_HEADERS[@]}")
A1_BODY=$(echo "$A1_RESPONSE" | sed '$d')
A1_STATUS=$(echo "$A1_RESPONSE" | tail -n 1)
assert_status "200" "$A1_STATUS" "list profile-types (happy path)"

A1_HAS_AGENT=$(echo "$A1_BODY" | jq -r '[.data[].code] | any(. == "agent")')
assert_true "$A1_HAS_AGENT" "profile-types list includes code='agent'"

A1_COUNT=$(echo "$A1_BODY" | jq -r '.count // 0')
TESTS_RUN=$((TESTS_RUN + 1))
if [ "$A1_COUNT" -ge 10 ] 2>/dev/null; then
  echo "PASS: profile-types list has >= 10 active types (count=$A1_COUNT)"
  TESTS_PASSED=$((TESTS_PASSED + 1))
else
  echo "FAIL: expected >= 10 active profile types, got count=$A1_COUNT"
  TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# A2 (unhappy): no Authorization header at all.
A2_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/profile-types")
assert_status "401" "$A2_STATUS" "list profile-types with no Authorization header"

# A3 (unhappy): garbage bearer token.
A3_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/v1/profile-types" \
  -H "Authorization: Bearer garbage.invalid.token")
assert_status "401" "$A3_STATUS" "list profile-types with an invalid/garbage bearer token"

echo ""
echo "===== B. POST /api/v1/profiles ====="

# B1 (happy): owner creates one profile per profile_type code -- proves the
# create+validation path (including Feature 026's agent-field handling)
# works uniformly across the whole matrix, not just 'agent'.
declare_profile_ids=""
for profile_code in owner director manager agent prospector receptionist financial legal tenant property_owner; do
  PROFILE_TYPE_ID=$(profile_type_id_for_code "$profile_code")
  if [ -z "$PROFILE_TYPE_ID" ]; then
    TESTS_RUN=$((TESTS_RUN + 1))
    echo "FAIL: profile_type '${profile_code}' not found in thedevkitchen_profile_type -- skipping"
    TESTS_FAILED=$((TESTS_FAILED + 1))
    continue
  fi

  CPF=$(cpf_for_profile_type "$profile_code")
  EMAIL="us026_matrix_${profile_code}_${TIMESTAMP}@example.com"
  EXTRA_FIELDS=""
  if [ "$profile_code" = "agent" ]; then
    EXTRA_FIELDS=',"creci":"CRECI/SP '"${CRECI_NUM}"'"'
  fi

  RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
    "${OWNER_HEADERS[@]}" -H "Content-Type: application/json" \
    -d '{"name":"US026 Matrix '"${profile_code}"'","company_id":'"${OWNER_COMPANY}"',"document":"'"${CPF}"'","email":"'"${EMAIL}"'","birthdate":"1990-01-01","profile_type_id":'"${PROFILE_TYPE_ID}"''"${EXTRA_FIELDS}"'}')
  BODY=$(echo "$RESPONSE" | sed '$d')
  STATUS=$(echo "$RESPONSE" | tail -n 1)
  assert_status "201" "$STATUS" "create profile for profile_type='${profile_code}' (happy path)"

  PROFILE_ID=$(echo "$BODY" | jq -r '.id // empty')
  case "$profile_code" in
    director) PROFILE_ID_DIRECTOR="$PROFILE_ID" ;;
    tenant)   PROFILE_ID_TENANT="$PROFILE_ID" ;;
  esac
done

# B2 (unhappy): missing required field ('document' omitted) -> 400.
B2_TYPE_ID=$(profile_type_id_for_code "manager")
B2_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${OWNER_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Matrix Missing Field","company_id":'"${OWNER_COMPANY}"',"email":"us026_matrix_missingfield_'"${TIMESTAMP}"'@example.com","birthdate":"1990-01-01","profile_type_id":'"${B2_TYPE_ID}"'}')
B2_STATUS=$(echo "$B2_RESPONSE" | tail -n 1)
assert_status "400" "$B2_STATUS" "create profile with missing required field 'document'"

# B3 (unhappy): malformed document (fails CPF/CNPJ checksum) -> 400.
B3_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${OWNER_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Matrix Bad Document","company_id":'"${OWNER_COMPANY}"',"document":"123","email":"us026_matrix_baddoc_'"${TIMESTAMP}"'@example.com","birthdate":"1990-01-01","profile_type_id":'"${B2_TYPE_ID}"'}')
B3_STATUS=$(echo "$B3_RESPONSE" | tail -n 1)
assert_status "400" "$B3_STATUS" "create profile with malformed document (fails CPF checksum)"

# B4 (unhappy): invalid/nonexistent profile_type_id -> 400.
B4_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${OWNER_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Matrix Bad Type","company_id":'"${OWNER_COMPANY}"',"document":"11144477735","email":"us026_matrix_badtype_'"${TIMESTAMP}"'@example.com","birthdate":"1990-01-01","profile_type_id":999999}')
B4_STATUS=$(echo "$B4_RESPONSE" | tail -n 1)
assert_status "400" "$B4_STATUS" "create profile with invalid/nonexistent profile_type_id"

# B5 (unhappy): duplicate (document, company_id, profile_type_id) -> 409,
# reusing B1's 'owner' profile document.
B5_TYPE_ID=$(profile_type_id_for_code "owner")
B5_CPF=$(cpf_for_profile_type "owner")
B5_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${OWNER_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Matrix Duplicate","company_id":'"${OWNER_COMPANY}"',"document":"'"${B5_CPF}"'","email":"us026_matrix_dup_'"${TIMESTAMP}"'@example.com","birthdate":"1990-01-01","profile_type_id":'"${B5_TYPE_ID}"'}')
B5_STATUS=$(echo "$B5_RESPONSE" | tail -n 1)
assert_status "409" "$B5_STATUS" "create profile with duplicate document+company+profile_type"

# B6 (unhappy): RBAC -- agent-role user is not authorized to create a
# 'director' profile (PROFILE_CREATION_MATRIX only allows agent to create
# tenant/property_owner) -> 403.
B6_TYPE_ID=$(profile_type_id_for_code "director")
B6_CPF=$(cpf_for_profile_type "rbac_forbidden")
B6_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${AGENT_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Matrix RBAC Forbidden","company_id":'"${AGENT_COMPANY}"',"document":"'"${B6_CPF}"'","email":"us026_matrix_rbac_'"${TIMESTAMP}"'@example.com","birthdate":"1990-01-01","profile_type_id":'"${B6_TYPE_ID}"'}')
B6_STATUS=$(echo "$B6_RESPONSE" | tail -n 1)
assert_status "403" "$B6_STATUS" "agent-role user forbidden from creating a 'director' profile (RBAC)"

# B7 (unhappy): cross-company -- owner (company 5) attempts to create a
# profile under owner-B's company (company 7), which they don't belong
# to -> 403.
B7_TYPE_ID=$(profile_type_id_for_code "manager")
B7_CPF=$(cpf_for_profile_type "cross_company")
B7_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/profiles" \
  "${OWNER_HEADERS[@]}" -H "Content-Type: application/json" \
  -d '{"name":"US026 Matrix Cross Company","company_id":'"${OWNER_B_COMPANY}"',"document":"'"${B7_CPF}"'","email":"us026_matrix_xcompany_'"${TIMESTAMP}"'@example.com","birthdate":"1990-01-01","profile_type_id":'"${B7_TYPE_ID}"'}')
B7_STATUS=$(echo "$B7_RESPONSE" | tail -n 1)
assert_status "403" "$B7_STATUS" "owner forbidden from creating a profile under a company they don't belong to"

echo ""
echo "===== C. POST /api/v1/users/invite ====="

if [ -z "${PROFILE_ID_TENANT:-}" ] || [ "${PROFILE_ID_TENANT:-null}" = "null" ]; then
  echo "FAIL: PROFILE_ID_TENANT unavailable from section B -- cannot run section C"
  TESTS_FAILED=$((TESTS_FAILED + 1))
  TESTS_RUN=$((TESTS_RUN + 1))
else
  # C1 (happy): invite the 'tenant' profile created in B1 -> 201.
  C1_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
    "${OWNER_HEADERS[@]}" -H "Content-Type: application/json" \
    -d '{"profile_id":'"${PROFILE_ID_TENANT}"'}')
  C1_STATUS=$(echo "$C1_RESPONSE" | tail -n 1)
  assert_status "201" "$C1_STATUS" "invite a freshly created 'tenant' profile (happy path)"

  # C4 (unhappy): inviting the SAME profile again -> 409 (already has a
  # linked user account).
  C4_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
    "${OWNER_HEADERS[@]}" -H "Content-Type: application/json" \
    -d '{"profile_id":'"${PROFILE_ID_TENANT}"'}')
  C4_STATUS=$(echo "$C4_RESPONSE" | tail -n 1)
  assert_status "409" "$C4_STATUS" "re-inviting an already-invited profile"
fi

# C2 (unhappy): missing profile_id -> 400.
C2_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${OWNER_HEADERS[@]}" -H "Content-Type: application/json" -d '{}')
assert_status "400" "$C2_STATUS" "invite with missing profile_id"

# C3 (unhappy): nonexistent profile_id -> 404.
C3_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
  "${OWNER_HEADERS[@]}" -H "Content-Type: application/json" -d '{"profile_id":999999999}')
assert_status "404" "$C3_STATUS" "invite with a nonexistent profile_id"

# C5 (unhappy): RBAC -- agent-role user is not authorized to invite a
# 'director' profile (INVITE_AUTHORIZATION only allows agent to invite
# tenant/property_owner) -> 403.
if [ -z "${PROFILE_ID_DIRECTOR:-}" ] || [ "${PROFILE_ID_DIRECTOR:-null}" = "null" ]; then
  echo "FAIL: PROFILE_ID_DIRECTOR unavailable from section B -- cannot run C5"
  TESTS_FAILED=$((TESTS_FAILED + 1))
  TESTS_RUN=$((TESTS_RUN + 1))
else
  C5_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/v1/users/invite" \
    "${AGENT_HEADERS[@]}" -H "Content-Type: application/json" \
    -d '{"profile_id":'"${PROFILE_ID_DIRECTOR}"'}')
  assert_status "403" "$C5_STATUS" "agent-role user forbidden from inviting a 'director' profile (RBAC)"
fi

cleanup_test_data

echo ""
echo "=== US026-S1 profile/invite happy+unhappy matrix: $TESTS_PASSED/$TESTS_RUN passed ==="
if [ "$TESTS_FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
