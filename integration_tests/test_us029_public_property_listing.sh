#!/usr/bin/env bash
# integration_tests/test_us029_public_property_listing.sh
# Feature 029: Public Property Listing API — list + image endpoints

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../18.0/.env"
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
else
    echo "ERROR: .env file not found at $ENV_FILE"
    exit 1
fi

source "${SCRIPT_DIR}/lib/get_oauth2_token.sh"

BASE_URL="${BASE_URL:-${ODOO_BASE_URL:-http://localhost:8069}}"
API_BASE="$BASE_URL/api/v1"
API_USER_EMAIL="${OWNER_EMAIL:-${SEED_OWNER_EMAIL:-}}"
API_USER_PASS="${OWNER_PASS:-${SEED_OWNER_PASSWORD:-}}"
: "${API_USER_EMAIL:?OWNER_EMAIL or SEED_OWNER_EMAIL is required in 18.0/.env}"
: "${API_USER_PASS:?OWNER_PASS or SEED_OWNER_PASSWORD is required in 18.0/.env}"

PASS=0; FAIL=0
_pass() { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
_fail() { echo "  [FAIL] $1 — $2"; FAIL=$((FAIL + 1)); }

echo "========================================"
echo "Feature 029: Public Property Listing Tests"
echo "========================================"

BEARER_TOKEN=$(get_oauth2_token) || { echo "Failed to get OAuth2 token"; exit 1; }

LOGIN_RESPONSE=$(curl -s -X POST "$API_BASE/users/login" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    -d "{\"email\":\"$API_USER_EMAIL\",\"password\":\"$API_USER_PASS\"}")
SID=$(echo "$LOGIN_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))")
COMPANY_ID=$(echo "$LOGIN_RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print((d.get('user') or {}).get('company_id') or d.get('company_id') or '')")
[ -z "$SID" ] && { echo "Owner login failed"; exit 1; }

H=(-H "Authorization: Bearer $BEARER_TOKEN" -H "X-Openerp-Session-Id: $SID" -H "Content-Type: application/json")
pub_req() {
    # Public endpoints: only the Bearer token is needed, no session header.
    curl -s "${@}" -H "Authorization: Bearer $BEARER_TOKEN"
}

# ── Setup: master data + company_slug ─────────────────────────────────────
PROPERTY_TYPE_ID=$(curl -s "$BASE_URL/api/v1/property-types" "${H[@]}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')")
LOCATION_TYPE_ID=$(curl -s "$BASE_URL/api/v1/location-types" "${H[@]}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')")
STATE_ID=$(curl -s "$BASE_URL/api/v1/states?country_id=31" "${H[@]}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else '')")
[ -n "$PROPERTY_TYPE_ID" ] && [ -n "$LOCATION_TYPE_ID" ] && [ -n "$STATE_ID" ] || { echo "Required master data not found"; exit 1; }

TS=$(date +%s)
COMPANY_SLUG="test-props-$TS"
curl -s -X PUT "$API_BASE/cms/settings" "${H[@]}" \
    -d "{\"company_slug\": \"$COMPANY_SLUG\"}" -o /dev/null

_create_property() {
    local name="$1" status="$2" advertise="$3"
    curl -s -X POST "$API_BASE/properties" "${H[@]}" -d "$(cat <<JSON
{
  "name": "$name",
  "property_type_id": $PROPERTY_TYPE_ID,
  "location_type_id": $LOCATION_TYPE_ID,
  "state_id": $STATE_ID,
  "area": 80,
  "zip_code": "01310-100",
  "city": "Sao Paulo",
  "street": "Av. Paulista",
  "street_number": "1000",
  "company_ids": [$COMPANY_ID],
  "price": 300000,
  "for_sale": true,
  "property_status": "$status",
  "advertise": $advertise
}
JSON
)" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo ""
}

PROP_AVAILABLE=$(_create_property "US029 Available Published $TS" "available" "true")
PROP_SOLD=$(_create_property "US029 Sold Published $TS" "sold" "true")
PROP_UNPUBLISHED=$(_create_property "US029 Unpublished $TS" "available" "false")

[ -n "$PROP_AVAILABLE" ] && [ -n "$PROP_SOLD" ] && [ -n "$PROP_UNPUBLISHED" ] || { echo "Property fixture setup failed"; exit 1; }
echo "Setup complete: slug=$COMPANY_SLUG available=$PROP_AVAILABLE sold=$PROP_SOLD unpublished=$PROP_UNPUBLISHED"

# ---- S1: Happy path list ----
echo ""; echo "S1: GET public property list — happy path"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG" -o /tmp/us029_list.json -w "%{http_code}")
if [ "$RESP" = "200" ]; then
    _pass "List returns 200"
    COUNT=$(python3 -c "import json; print(json.load(open('/tmp/us029_list.json'))['count'])")
    [ "$COUNT" -ge 2 ] && _pass "List includes published properties (count=$COUNT)" || _fail "Count" "Expected >=2, got $COUNT"
else
    _fail "List happy path" "Expected 200, got $RESP"
fi

# ---- S2: Unpublished property never returned ----
echo ""; echo "S2: Unpublished property excluded"
IDS=$(python3 -c "import json; print([p['id'] for p in json.load(open('/tmp/us029_list.json'))['data']])")
if echo "$IDS" | grep -q "$PROP_UNPUBLISHED"; then
    _fail "Unpublished exclusion" "Unpublished property $PROP_UNPUBLISHED leaked into results"
else
    _pass "Unpublished property not in results"
fi

# ---- S3: status filter ----
echo ""; echo "S3: status=sold filter"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG?status=sold" -o /tmp/us029_sold.json -w "%{http_code}")
[ "$RESP" = "200" ] && _pass "status=sold returns 200" || _fail "status=sold" "Expected 200, got $RESP"
SOLD_IDS=$(python3 -c "import json; print([p['id'] for p in json.load(open('/tmp/us029_sold.json'))['data']])")
echo "$SOLD_IDS" | grep -q "$PROP_SOLD" && _pass "Sold property present in status=sold results" || _fail "status filter" "Expected $PROP_SOLD in $SOLD_IDS"

# ---- S4: invalid status → 400 ----
echo ""; echo "S4: status=maintenance → 400 (out-of-scope model value)"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG?status=maintenance" -o /tmp/us029_bad_status.json -w "%{http_code}")
[ "$RESP" = "400" ] && _pass "Invalid status returns 400" || _fail "Invalid status" "Expected 400, got $RESP"

# ---- S5: ids filter, cross-company excluded silently ----
echo ""; echo "S5: ids filter"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG?ids=$PROP_AVAILABLE,999999999" -o /tmp/us029_ids.json -w "%{http_code}")
[ "$RESP" = "200" ] && _pass "ids filter returns 200" || _fail "ids filter" "Expected 200, got $RESP"
IDS_COUNT=$(python3 -c "import json; print(json.load(open('/tmp/us029_ids.json'))['count'])")
[ "$IDS_COUNT" = "1" ] && _pass "Only the matching id is returned (nonexistent id silently dropped)" || _fail "ids filter count" "Expected 1, got $IDS_COUNT"

# ---- S5b: ids filter, REAL cross-company property excluded (ADR-008 anti-enumeration) ----
echo ""; echo "S5b: ids filter — real cross-company property id"
CROSS_COMPANY_PROPERTY_ID=$(docker compose -f "$SCRIPT_DIR/../18.0/docker-compose.yml" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -At -c \"SELECT id FROM real_estate_property WHERE company_id != $COMPANY_ID AND active = true LIMIT 1;\"" 2>/dev/null || true)
if [ -n "$CROSS_COMPANY_PROPERTY_ID" ]; then
    RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG?ids=$PROP_AVAILABLE,$CROSS_COMPANY_PROPERTY_ID" -o /tmp/us029_cross_company_ids.json -w "%{http_code}")
    [ "$RESP" = "200" ] && _pass "cross-company ids filter returns 200" || _fail "cross-company ids filter" "Expected 200, got $RESP"
    CROSS_IDS=$(python3 -c "import json; print([p['id'] for p in json.load(open('/tmp/us029_cross_company_ids.json'))['data']])")
    if echo "$CROSS_IDS" | grep -q "$CROSS_COMPANY_PROPERTY_ID"; then
        _fail "cross-company isolation" "Cross-company property $CROSS_COMPANY_PROPERTY_ID leaked into results via ids filter"
    else
        _pass "Real cross-company property silently excluded from ids filter results (anti-enumeration)"
    fi
else
    echo "  [SKIP] No cross-company property found in dev DB to test against"
fi

# ---- S6: unknown company_slug → 404 ----
echo ""; echo "S6: unknown company_slug → 404"
RESP=$(pub_req -X GET "$API_BASE/public/properties/nonexistent-slug-$TS" -o /dev/null -w "%{http_code}")
[ "$RESP" = "404" ] && _pass "Unknown slug returns 404" || _fail "Unknown slug" "Expected 404, got $RESP"

# ---- S7: missing bearer token → 401 ----
echo ""; echo "S7: missing token → 401"
RESP=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$API_BASE/public/properties/$COMPANY_SLUG")
[ "$RESP" = "401" ] && _pass "Missing token returns 401" || _fail "Missing token" "Expected 401, got $RESP"

# ---- S8: image endpoint — no image set → 404 ----
echo ""; echo "S8: image endpoint — property has no image → 404"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG/$PROP_AVAILABLE/image" -o /dev/null -w "%{http_code}")
[ "$RESP" = "404" ] && _pass "No-image property returns 404 on image route" || _fail "Image 404" "Expected 404, got $RESP"

# ---- S9: image endpoint — non-public property → 404 (anti-enumeration) ----
echo ""; echo "S9: image endpoint — unpublished property → 404"
RESP=$(pub_req -X GET "$API_BASE/public/properties/$COMPANY_SLUG/$PROP_UNPUBLISHED/image" -o /dev/null -w "%{http_code}")
[ "$RESP" = "404" ] && _pass "Unpublished property image returns 404" || _fail "Image visibility gate" "Expected 404, got $RESP"

echo ""; echo "========================================"
echo "Results: PASS=$PASS FAIL=$FAIL"
echo "========================================"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
