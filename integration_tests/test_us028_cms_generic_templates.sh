#!/usr/bin/env bash
# integration_tests/test_us028_cms_generic_templates.sh
# Feature 028: CMS Generic Templates (Platform Catalog) — E2E API tests

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/get_oauth2_token.sh"

BASE_URL="${BASE_URL:-http://localhost:8069}"
API_BASE="$BASE_URL/api/v1"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; SKIP=0

_pass() { echo -e "${GREEN}  [PASS] $1${NC}"; ((PASS++)) || true; }
_fail() { echo -e "${RED}  [FAIL] $1 — $2${NC}"; ((FAIL++)) || true; }
_skip() { echo -e "${YELLOW}  [SKIP] $1${NC}"; ((SKIP++)) || true; }

echo "========================================"
echo "Feature 028 CMS Generic Templates Tests"
echo "========================================"

BEARER_TOKEN=$(get_oauth2_token) || { echo "Failed to get OAuth2 token"; exit 1; }

login_user() {
    local resp=$(curl -s -X POST "$API_BASE/users/login" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $BEARER_TOKEN" \
        -d "{\"login\": \"$1\", \"password\": \"$2\"}")
    local sid=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
    local cid=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('user',{}).get('default_company_id',''))" 2>/dev/null)
    [ -z "$sid" ] && { echo ""; return 1; }; echo "$sid|$cid"
}

OWNER_DATA=$(login_user "owner@seed.com.br" "seed123") || { echo "Owner login failed"; exit 1; }
OWNER_SID=$(echo "$OWNER_DATA" | cut -d'|' -f1); OWNER_CID=$(echo "$OWNER_DATA" | cut -d'|' -f2)

AGENT_DATA=$(login_user "agent@seed.com.br" "seed123") || AGENT_DATA=""
AGENT_SID=$(echo "$AGENT_DATA" | cut -d'|' -f1); AGENT_CID=$(echo "$AGENT_DATA" | cut -d'|' -f2)

OWNER_B_DATA=$(login_user "owner_urban@seed.com.br" "seed123") || OWNER_B_DATA=""
OWNER_B_SID=$(echo "$OWNER_B_DATA" | cut -d'|' -f1); OWNER_B_CID=$(echo "$OWNER_B_DATA" | cut -d'|' -f2)

cms_req() {
    local method="$1" url="$2" sid="$3" cid="$4"; shift 4
    curl -s "${@}" -X "$method" "$url" \
        -H "Authorization: Bearer $BEARER_TOKEN" \
        -H "X-Openerp-Session-Id: $sid" \
        -H "X-Company-Id: $cid"
}

# ---- S1: List generic templates as owner ----
echo ""; echo "S1: GET /api/v1/cms/templates/generic — owner list"
RESP=$(cms_req GET "$API_BASE/cms/templates/generic" "$OWNER_SID" "$OWNER_CID" -o /tmp/gt_list.json -w "%{http_code}")
if [ "$RESP" = "200" ]; then
    _pass "GET /templates/generic returns 200"
    GT_ID=$(python3 -c "import json; items=json.load(open('/tmp/gt_list.json'))['items']; print(next((i['id'] for i in items if i['name']=='seed_generic_landing'), ''))" 2>/dev/null || echo "")
else
    _fail "GET /templates/generic" "Expected 200, got $RESP"
    GT_ID=""
fi

# ---- S2: List filters by category ----
echo ""; echo "S2: GET /api/v1/cms/templates/generic?category=property"
RESP=$(cms_req GET "$API_BASE/cms/templates/generic?category=property" "$OWNER_SID" "$OWNER_CID" -o /tmp/gt_list_cat.json -w "%{http_code}")
if [ "$RESP" = "200" ]; then
    ALL_PROPERTY=$(python3 -c "import json; items=json.load(open('/tmp/gt_list_cat.json'))['items']; print(all(i['category']=='property' for i in items))" 2>/dev/null || echo "False")
    [ "$ALL_PROPERTY" = "True" ] && _pass "Category filter returns only 'property' items" || _fail "Category filter" "Non-property item present"
else
    _fail "GET /templates/generic?category=property" "Expected 200, got $RESP"
fi

# ---- S3: List response never includes content ----
echo ""; echo "S3: listing never includes 'content' field"
HAS_CONTENT=$(python3 -c "import json; items=json.load(open('/tmp/gt_list.json'))['items']; print(any('content' in i for i in items))" 2>/dev/null || echo "True")
[ "$HAS_CONTENT" = "False" ] && _pass "Listing excludes content field" || _fail "Listing excludes content" "content leaked into list payload"

# ---- S4: Get detail includes content ----
echo ""; echo "S4: GET /api/v1/cms/templates/generic/:id — detail includes content"
if [ -n "$GT_ID" ]; then
    RESP=$(cms_req GET "$API_BASE/cms/templates/generic/$GT_ID" "$OWNER_SID" "$OWNER_CID" -o /tmp/gt_detail.json -w "%{http_code}")
    if [ "$RESP" = "200" ]; then
        HAS_CONTENT_KEY=$(python3 -c "import json; print('content' in json.load(open('/tmp/gt_detail.json')))" 2>/dev/null || echo "False")
        [ "$HAS_CONTENT_KEY" = "True" ] && _pass "GET detail returns 200 with content" || _fail "GET detail content" "content key missing"
    else
        _fail "GET /templates/generic/:id" "Expected 200, got $RESP"
    fi
else
    _skip "S4: no GT_ID (seed_generic_landing not found)"
fi

# ---- S5: Agent forbidden from list/detail/copy ----
echo ""; echo "S5: Agent (non-management role) forbidden on all 3 endpoints"
if [ -n "$AGENT_SID" ]; then
    RESP=$(cms_req GET "$API_BASE/cms/templates/generic" "$AGENT_SID" "$AGENT_CID" -o /tmp/gt_agent_list.json -w "%{http_code}")
    [ "$RESP" = "403" ] && _pass "Agent GET /templates/generic returns 403" || _fail "Agent list" "Expected 403, got $RESP"

    if [ -n "$GT_ID" ]; then
        RESP=$(cms_req GET "$API_BASE/cms/templates/generic/$GT_ID" "$AGENT_SID" "$AGENT_CID" -o /tmp/gt_agent_detail.json -w "%{http_code}")
        [ "$RESP" = "403" ] && _pass "Agent GET /templates/generic/:id returns 403" || _fail "Agent detail" "Expected 403, got $RESP"
    fi

    RESP=$(cms_req POST "$API_BASE/cms/templates/generic/${GT_ID:-1}/copy" "$AGENT_SID" "$AGENT_CID" \
        -o /tmp/gt_agent_copy.json -w "%{http_code}" -H "Content-Type: application/json" -d '{}')
    [ "$RESP" = "403" ] && _pass "Agent POST copy returns 403" || _fail "Agent copy" "Expected 403, got $RESP"
else
    _skip "S5: Agent session not available"
fi

# ---- S6: Owner copies generic template into own company ----
echo ""; echo "S6: POST /api/v1/cms/templates/generic/:id/copy — owner copies"
COPY_ID=""
if [ -n "$GT_ID" ]; then
    RESP=$(cms_req POST "$API_BASE/cms/templates/generic/$GT_ID/copy" "$OWNER_SID" "$OWNER_CID" \
        -o /tmp/gt_copy.json -w "%{http_code}" -H "Content-Type: application/json" -d '{}')
    if [ "$RESP" = "201" ]; then
        COPY_ID=$(python3 -c "import json; print(json.load(open('/tmp/gt_copy.json'))['id'])" 2>/dev/null || echo "")
        SRC_OK=$(python3 -c "import json; d=json.load(open('/tmp/gt_copy.json')); print(d.get('source_generic_template_id') == $GT_ID)" 2>/dev/null || echo "False")
        [ "$SRC_OK" = "True" ] && _pass "POST copy returns 201 with source_generic_template_id=$GT_ID (id=$COPY_ID)" \
            || _fail "POST copy source_generic_template_id" "Mismatch or missing"
    else
        _fail "POST /templates/generic/:id/copy" "Expected 201, got $RESP — $(cat /tmp/gt_copy.json)"
    fi
else
    _skip "S6: no GT_ID"
fi

# ---- S7: Copy does not leak into a different company ----
echo ""; echo "S7: Copy isolation — Company B (owner_urban) does not see Company A's copy"
if [ -n "$OWNER_B_SID" ] && [ -n "$COPY_ID" ]; then
    RESP=$(cms_req GET "$API_BASE/cms/templates" "$OWNER_B_SID" "$OWNER_B_CID" -o /tmp/gt_companyb_templates.json -w "%{http_code}")
    if [ "$RESP" = "200" ]; then
        LEAKED=$(python3 -c "import json; items=json.load(open('/tmp/gt_companyb_templates.json'))['items']; print(any(i['id']==$COPY_ID for i in items))" 2>/dev/null || echo "True")
        [ "$LEAKED" = "False" ] && _pass "Company B cannot see Company A's copied template" || _fail "Copy isolation" "Company B sees Company A's copy — isolation broken!"
    else
        _fail "GET /templates (company B)" "Expected 200, got $RESP"
    fi
else
    _skip "S7: owner_urban session or COPY_ID not available"
fi

# ---- S8: Copy of nonexistent generic returns 404 ----
echo ""; echo "S8: POST copy on nonexistent generic template → 404"
RESP=$(cms_req POST "$API_BASE/cms/templates/generic/999999/copy" "$OWNER_SID" "$OWNER_CID" \
    -o /tmp/gt_copy_404.json -w "%{http_code}" -H "Content-Type: application/json" -d '{}')
[ "$RESP" = "404" ] && _pass "POST copy on nonexistent id returns 404" || _fail "POST copy 404" "Expected 404, got $RESP"

# ---- S9: Copy remains accessible independent of the generic source's later state ----
echo ""; echo "S9: Existing copy stays accessible regardless of the generic source's state"
if [ -n "$COPY_ID" ]; then
    RESP=$(cms_req GET "$API_BASE/cms/templates/$COPY_ID" "$OWNER_SID" "$OWNER_CID" -o /tmp/gt_copy_after.json -w "%{http_code}")
    [ "$RESP" = "200" ] && _pass "Copy $COPY_ID still accessible (snapshot independent of source)" || _fail "Copy independence" "Expected 200, got $RESP"
else
    _skip "S9: no COPY_ID"
fi

echo ""; echo "========================================"
echo "Results: PASS=$PASS  FAIL=$FAIL  SKIP=$SKIP"
echo "========================================"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
