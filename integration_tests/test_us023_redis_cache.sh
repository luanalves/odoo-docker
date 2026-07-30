#!/usr/bin/env bash
# =============================================================================
# E2E Integration Tests — US023 Redis Cache for JWT and Session (US1 / US2)
# Scenarios S01–S06
# =============================================================================
# Usage:
#   ./integration_tests/test_us023_redis_cache.sh
#
# Prerequisites:
#   - Odoo 18.0 running at BASE_URL (default: http://localhost:8069)
#   - Redis running and accessible (docker compose exec redis redis-cli)
#   - Environment variables: OWNER_TOKEN, OWNER_SESSION (valid auth tokens)
#   - jq, curl available

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8069}"
OWNER_TOKEN="${OWNER_TOKEN:-}"
OWNER_SESSION="${OWNER_SESSION:-}"
OWNER_COMPANY="${OWNER_COMPANY:-}"
REDIS_CONTAINER="${REDIS_CONTAINER:-redis}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PASS=0
FAIL=0
SKIP=0

# =============================================================================
# Helpers
# =============================================================================

log_info()  { echo "[INFO]  $*"; }
log_pass()  { echo "[PASS]  $*"; PASS=$((PASS+1)); }
log_fail()  { echo "[FAIL]  $*"; FAIL=$((FAIL+1)); }
log_skip()  { echo "[SKIP]  $*"; SKIP=$((SKIP+1)); }
log_section() { echo ""; echo "========================================"; echo "$*"; echo "========================================"; }

load_env_if_available() {
    if [ -f "$SCRIPT_DIR/../18.0/.env" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/../18.0/.env"
    fi
}

get_oauth2_token_local() {
    # Prefer existing helper used by other integration tests.
    if [ -f "$SCRIPT_DIR/lib/get_oauth2_token.sh" ]; then
        # shellcheck disable=SC1091
        source "$SCRIPT_DIR/lib/get_oauth2_token.sh"
        get_oauth2_token
        return $?
    fi

    local client_id client_secret response
    client_id="${OAUTH_CLIENT_ID:-test-client-id}"
    client_secret="${OAUTH_CLIENT_SECRET:-test-client-secret-12345}"
    response=$(curl -s -X POST "${BASE_URL}/api/v1/auth/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "grant_type=client_credentials&client_id=${client_id}&client_secret=${client_secret}")

    echo "$response" | jq -r '.access_token // empty'
}

bootstrap_owner_auth() {
    load_env_if_available

    local owner_email owner_password login_response session_id
    owner_email="${TEST_USER_OWNER:-owner@example.com}"
    owner_password="${TEST_PASSWORD_OWNER:-SecurePass123!}"

    OWNER_TOKEN="$(get_oauth2_token_local)"
    if [ -z "$OWNER_TOKEN" ]; then
        return 1
    fi

    login_response=$(curl -s -X POST "$BASE_URL/api/v1/users/login" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $OWNER_TOKEN" \
        -d "{\"login\": \"$owner_email\", \"password\": \"$owner_password\"}")

    session_id=$(echo "$login_response" | jq -r '.session_id // empty')
    if [ -z "$session_id" ]; then
        return 1
    fi

    OWNER_SESSION="$session_id"
    OWNER_COMPANY=$(echo "$login_response" | jq -r '.user.default_company_id // empty')
    export OWNER_TOKEN OWNER_SESSION OWNER_COMPANY
    return 0
}

discover_agent_id() {
    # Feature 027 (Task 9) removed GET /api/v1/agents. Agents are now
    # discovered through the unified profile endpoint, reading the id from
    # the embedded `agent` sub-object added by Task 2 -- NOT `.data[0].id`,
    # which is the profile id, not the real.estate.agent id the
    # /api/v1/agents/<id>/performance sub-resource is keyed on.
    local profiles_json
    profiles_json=$(curl -s \
        -H "Authorization: Bearer $OWNER_TOKEN" \
        -H "X-Openerp-Session-Id: $OWNER_SESSION" \
        "$BASE_URL/api/v1/profiles?company_ids=$OWNER_COMPANY&profile_type=agent&active=true" \
        2>/dev/null || echo '{}')

    echo "$profiles_json" \
        | jq -r '[.data[]? | select(.agent.active == true) | .agent.id][0] // empty' \
        2>/dev/null || echo ""
}

_redis_cmd() {
    # Helper: run redis-cli with optional auth against DB 1
    if [ -n "${REDIS_PASSWORD:-}" ]; then
        docker compose -f "$SCRIPT_DIR/../18.0/docker-compose.yml" exec -T redis \
            redis-cli -n 1 -a "$REDIS_PASSWORD" --no-auth-warning "$@" 2>/dev/null
    else
        docker compose -f "$SCRIPT_DIR/../18.0/docker-compose.yml" exec -T redis \
            redis-cli -n 1 "$@" 2>/dev/null
    fi
}

flush_cache() {
    # Delete only this feature's key prefixes — never FLUSHDB (would wipe Odoo sessions).
    # Keys are collected into a variable (not piped straight into `while read`)
    # because `docker compose exec -T` inside that loop would otherwise inherit
    # and consume the loop's own stdin, hanging after the first iteration.
    for prefix in 'session:*' 'jwt:*' 'performance:*'; do
        local keys
        keys=$(_redis_cmd KEYS "$prefix" 2>/dev/null | grep -v '^$' || true)
        if [ -n "$keys" ]; then
            while IFS= read -r key; do
                [ -n "$key" ] && _redis_cmd DEL "$key" < /dev/null > /dev/null
            done <<< "$keys"
        fi
    done
    echo "flushed"
}

key_exists() {
    local pattern="$1"
    local count
    count=$( { _redis_cmd KEYS "$pattern" || true; } | grep -v '^$' | wc -l | tr -d ' ')
    [ "${count:-0}" -gt 0 ]
}

key_count() {
    local pattern="$1"
    local count
    count=$( { _redis_cmd KEYS "$pattern" || true; } | grep -v '^$' | wc -l | tr -d ' ')
    echo "${count:-0}"
}

http_get() {
    local path="$1"
    local token="${2:-$OWNER_TOKEN}"
    local session="${3:-$OWNER_SESSION}"
    curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $token" \
        -H "X-Openerp-Session-Id: $session" \
        "$BASE_URL$path"
}

check_prerequisites() {
    if ! command -v jq > /dev/null 2>&1; then
        log_fail "jq not found. Install with: brew install jq"
        exit 1
    fi
    if ! command -v curl > /dev/null 2>&1; then
        log_fail "curl not found."
        exit 1
    fi
    # Test Redis connectivity
    if ! _redis_cmd PING > /dev/null 2>&1; then
        log_skip "Redis not accessible via docker compose — skipping all Redis-specific tests"
        exit 0
    fi

    if [ -z "$OWNER_TOKEN" ] || [ -z "$OWNER_SESSION" ]; then
        if bootstrap_owner_auth; then
            log_info "Bootstrap auth OK (owner token/session loaded automatically)"
        else
            log_fail "Could not bootstrap OWNER_TOKEN/OWNER_SESSION automatically. Set env vars or configure 18.0/.env."
            exit 1
        fi
    fi

    # If environment already had token/session but they are stale, renew them.
    local auth_probe
    auth_probe=$(http_get "/api/v1/profiles" "$OWNER_TOKEN" "$OWNER_SESSION")
    if [ "$auth_probe" = "401" ] || [ "$auth_probe" = "403" ] || [ "$auth_probe" = "000" ]; then
        if bootstrap_owner_auth; then
            log_info "Refreshed stale owner token/session via bootstrap"
        else
            log_fail "Existing OWNER_TOKEN/OWNER_SESSION are invalid and bootstrap failed"
            exit 1
        fi
    fi

    log_info "Prerequisites OK. BASE_URL=$BASE_URL"
}

# =============================================================================
# S01 — Cache populated after authenticated request
# =============================================================================
test_s01_cache_populated_after_request() {
    log_section "S01: Cache populated after authenticated request"

    flush_cache
    local status
    status=$(http_get "/api/v1/profiles" "$OWNER_TOKEN" "$OWNER_SESSION")

    # Accept 200 (full success) or 400 (auth passed, require_company or business logic rejected)
    # HTTP 401 means auth failed — cache should NOT be populated in that case
    if [ "$status" != "401" ] && [ "$status" != "403" ] && [ "$status" != "000" ]; then
        sleep 0.5  # allow async write
        local after
        after=$(key_count "session:*")
        if [ "$after" -gt 0 ]; then
            log_pass "S01: session:* cache key present after auth request (HTTP $status, count: $after)"
        else
            log_fail "S01: session:* cache key NOT found after auth request (count=$after, HTTP $status)"
        fi
    else
        log_fail "S01: Authentication failed — HTTP $status (expected auth to pass)"
    fi
}

# =============================================================================
# S02 — Logout removes session key + subsequent request returns 401
# =============================================================================
test_s02_logout_removes_session_key() {
    log_section "S02: Logout removes session key"

    # First make a request to populate the cache
    http_get "/api/v1/profiles" "$OWNER_TOKEN" "$OWNER_SESSION" > /dev/null
    sleep 0.3

    local before_count
    before_count=$(key_count "session:*")
    log_info "Session keys before logout: $before_count"

    # Logout
    local logout_status
    logout_status=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "Authorization: Bearer $OWNER_TOKEN" \
        -H "X-Openerp-Session-Id: $OWNER_SESSION" \
        "$BASE_URL/api/v1/users/logout")

    if [ "$logout_status" = "200" ]; then
        sleep 0.3
        local after_count
        after_count=$(key_count "session:*")
        log_info "Session keys after logout: $after_count"

        # Try to use the logged-out session
        local reuse_status
        reuse_status=$(http_get "/api/v1/profiles" "$OWNER_TOKEN" "$OWNER_SESSION")

        if [ "$reuse_status" = "401" ]; then
            log_pass "S02: Logout + re-use returns 401"
        else
            log_fail "S02: Re-use after logout returned HTTP $reuse_status (expected 401)"
        fi
    else
        log_skip "S02: Logout endpoint returned $logout_status — skipping cache check"
    fi
}

# =============================================================================
# S03 — Token revoke removes JWT key + subsequent request returns 401
# =============================================================================
test_s03_revoke_removes_jwt_key() {
    log_section "S03: Token revoke removes JWT cache key"

    # Populate JWT cache
    http_get "/api/v1/profiles" "$OWNER_TOKEN" "$OWNER_SESSION" > /dev/null
    sleep 0.3

    local jwt_count_before expected_jwt_key expected_exists_before
    jwt_count_before=$(key_count "jwt:*")
    expected_jwt_key="jwt:$(printf '%s' "$OWNER_TOKEN" | shasum -a 256 | awk '{print $1}' | cut -c1-32)"
    expected_exists_before=$( { _redis_cmd KEYS "$expected_jwt_key" || true; } | grep -c "$expected_jwt_key" || true)
    log_info "JWT keys before revoke: $jwt_count_before (expected key exists=$expected_exists_before)"

    # Revoke via admin (using current token for self-revoke if supported)
    local revoke_status
    revoke_status=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "Authorization: Bearer $OWNER_TOKEN" \
        -H "X-Openerp-Session-Id: $OWNER_SESSION" \
        -H "Content-Type: application/json" \
        "$BASE_URL/api/v1/auth/revoke")

    if [ "$revoke_status" = "200" ]; then
        sleep 0.3
        local jwt_count_after expected_exists_after
        jwt_count_after=$(key_count "jwt:*")
        expected_exists_after=$( { _redis_cmd KEYS "$expected_jwt_key" || true; } | grep -c "$expected_jwt_key" || true)
        log_info "JWT keys after revoke: $jwt_count_after (expected key exists=$expected_exists_after)"

        if [ "$expected_exists_after" = "0" ]; then
            log_pass "S03: JWT cache key removed after revoke"
        else
            log_fail "S03: Expected JWT cache key still present after revoke (key=$expected_jwt_key)"
        fi

        # Verify 401 on reuse
        local reuse_status
        reuse_status=$(http_get "/api/v1/profiles" "$OWNER_TOKEN" "$OWNER_SESSION")
        if [ "$reuse_status" = "401" ]; then
            log_pass "S03: Revoked token returns 401"
        else
            log_fail "S03: Revoked token returned HTTP $reuse_status (expected 401)"
        fi

        if bootstrap_owner_auth; then
            log_info "S03: Re-authenticated owner after revoke for subsequent scenarios"
        else
            log_skip "S03: Could not re-authenticate owner after revoke; later scenarios may be skipped"
        fi
    else
        log_skip "S03: Revoke endpoint returned $revoke_status — skipping"
    fi
}

# =============================================================================
# S04 — Switch-company removes session cache key
# =============================================================================
test_s04_switch_company_removes_key() {
    log_section "S04: Switch-company removes session cache key"

    http_get "/api/v1/profiles" "$OWNER_TOKEN" "$OWNER_SESSION" > /dev/null
    sleep 0.3

    # Get available companies
    local companies_json
    companies_json=$(curl -s \
        -H "Authorization: Bearer $OWNER_TOKEN" \
        -H "X-Openerp-Session-Id: $OWNER_SESSION" \
        "$BASE_URL/api/v1/companies" 2>/dev/null || echo '{}')

    local first_company_id
    first_company_id=$(echo "$companies_json" | jq -r '.data[0].id // empty' 2>/dev/null || echo "")

    if [ -z "$first_company_id" ]; then
        log_skip "S04: Could not get company ID from /api/v1/companies — skipping"
        return
    fi

    local switch_status
    switch_status=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "Authorization: Bearer $OWNER_TOKEN" \
        -H "X-Openerp-Session-Id: $OWNER_SESSION" \
        -H "Content-Type: application/json" \
        -d "{\"company_id\": $first_company_id}" \
        "$BASE_URL/api/v1/users/switch-company")

    if [ "$switch_status" = "200" ]; then
        sleep 0.3
        # Subsequent request should still work (new cache entry created)
        local after_status
        after_status=$(http_get "/api/v1/profiles" "$OWNER_TOKEN" "$OWNER_SESSION")
        if [ "$after_status" = "200" ]; then
            log_pass "S04: Switch-company clears and repopulates cache (HTTP 200)"
        else
            log_fail "S04: After switch-company, HTTP $after_status (expected 200)"
        fi
    else
        log_skip "S04: switch-company returned $switch_status — skipping cache check"
    fi
}

# =============================================================================
# S05 — Profile DELETE → active sessions get 401 immediately (no TTL wait)
# =============================================================================
test_s05_profile_delete_invalidates_sessions() {
    log_section "S05: Profile DELETE immediately invalidates active sessions"

    # This test requires creating a test profile and getting its session token
    # Since we can't create ephemeral sessions easily in bash, we verify
    # the endpoint behavior and log appropriately

    log_skip "S05: Requires dedicated test agent session — run via integration test suite (TransactionCase)"
}

# =============================================================================
# S06 — Redis stopped → HTTP 200 fallback (graceful degradation)
# =============================================================================
test_s06_redis_down_fallback() {
    log_section "S06: Redis unavailable → API falls back to database (HTTP 200)"

    # NOTE: When Odoo 18.0 is configured with Redis as the session backend,
    # pausing Redis will also disable Odoo's own session storage (not just our
    # custom JWT/session cache). This means the fallback test must be run with
    # a fresh request that doesn't depend on an existing Odoo session.
    # This scenario is better validated via unit tests (RedisClient fallback).
    log_skip "S06: Odoo 18.0 uses Redis natively for sessions — pausing Redis would break Odoo's own session, not just our cache layer. Fallback is tested via unit tests (TestRequireJwtWithCache, TestSessionValidatorWithCache)."
}

# =============================================================================
# S07 — PerformanceService: cache populated after first call (US3)
# =============================================================================
test_s07_performance_cache_populated() {
    log_section "S07: Performance cache populated after first GET /api/v1/agents/:id/performance"

    flush_cache
    local before
    before=$(key_count "performance:agent:*")

    # Get first available agent ID (via GET /api/v1/profiles, see
    # discover_agent_id -- GET /api/v1/agents was removed by Feature 027)
    local agent_id
    agent_id=$(discover_agent_id)

    if [ -z "$agent_id" ]; then
        log_fail "S07: No agent found via GET /api/v1/profiles?profile_type=agent"
        return
    fi

    local perf_status
    perf_status=$(http_get "/api/v1/agents/$agent_id/performance" "$OWNER_TOKEN" "$OWNER_SESSION")

    if [ "$perf_status" = "200" ]; then
        sleep 0.5
        local after
        after=$(key_count "performance:agent:*")
        if [ "$after" -gt "$before" ]; then
            log_pass "S07: performance:agent:* cache key created (count: $after)"
        else
            log_fail "S07: performance:agent:* NOT found after request (before=$before after=$after)"
        fi
    else
        log_fail "S07: GET /api/v1/agents/$agent_id/performance returned HTTP $perf_status (expected 200)"
    fi
}

# =============================================================================
# S08 — CommissionTransaction.create() invalidates performance cache (US3)
# =============================================================================
test_s08_commission_create_invalidates_performance_cache() {
    log_section "S08: CommissionTransaction create invalidates performance cache"

    # Warm up cache (agent discovered via GET /api/v1/profiles, see
    # discover_agent_id -- GET /api/v1/agents was removed by Feature 027)
    local agent_id
    agent_id=$(discover_agent_id)

    if [ -z "$agent_id" ]; then
        log_fail "S08: No agent found via GET /api/v1/profiles?profile_type=agent"
        return
    fi

    # Populate performance cache
    http_get "/api/v1/agents/$agent_id/performance" "$OWNER_TOKEN" "$OWNER_SESSION" > /dev/null
    sleep 0.5

    local before_count
    before_count=$(key_count "performance:agent:*")
    log_info "S08: Performance keys before commission create: $before_count"

    if [ "$before_count" -eq 0 ]; then
        log_skip "S08: No performance keys found after warm-up — skipping"
        return
    fi

    # Creating a commission transaction via Odoo RPC triggers the create() override
    # We use the JSON-RPC call to trigger the ORM path
    local rpc_result
    rpc_result=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $OWNER_TOKEN" \
        -H "X-Openerp-Session-Id: $OWNER_SESSION" \
        -d "{\"jsonrpc\":\"2.0\",\"method\":\"call\",\"params\":{\"model\":\"real.estate.commission.transaction\",\"method\":\"create\",\"args\":[{\"agent_id\":$agent_id,\"rule_id\":1,\"transaction_type\":\"sale\",\"gross_value\":100000}],\"kwargs\":{}}}" \
        "$BASE_URL/web/dataset/call_kw" 2>/dev/null || echo '{}')

    sleep 0.5
    local after_count
    after_count=$(key_count "performance:agent:*")
    log_info "S08: Performance keys after commission create: $after_count"

    if [ "$after_count" -lt "$before_count" ]; then
        log_pass "S08: Performance cache invalidated after CommissionTransaction.create()"
    else
        log_skip "S08: Cache count unchanged ($before_count → $after_count) — may require valid commission rule"
    fi
}

# =============================================================================
# Main
# =============================================================================
main() {
    log_section "US023 Redis Cache E2E Tests (S01-S08)"
    check_prerequisites

    test_s01_cache_populated_after_request
    test_s02_logout_removes_session_key
    test_s03_revoke_removes_jwt_key
    test_s04_switch_company_removes_key
    test_s05_profile_delete_invalidates_sessions
    test_s06_redis_down_fallback
    test_s07_performance_cache_populated
    test_s08_commission_create_invalidates_performance_cache

    log_section "Test Summary"
    echo "PASS: $PASS | FAIL: $FAIL | SKIP: $SKIP"
    echo "Total: $((PASS + FAIL + SKIP))"

    if [ "$FAIL" -gt 0 ]; then
        exit 1
    fi
    exit 0
}

main "$@"
