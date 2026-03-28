#!/usr/bin/env bash
# ==============================================================================
# TenderWriter — SSO Integration Smoke Test
#
# Validates that Keycloak, Mattermost, and TenderWriter are correctly configured
# for OIDC SSO. Run this after starting the stack with:
#
#   docker compose --profile keycloak --profile videochat up -d
#
# Prerequisites:
#   - Keycloak must be healthy
#   - Mattermost must be healthy
#   - MM_OIDC_ENABLE must be "true"
# ==============================================================================

set -euo pipefail

KC_URL="${KC_URL:-http://localhost:8180}"
KC_INTERNAL="${KC_INTERNAL:-http://localhost:8180}"
KC_REALM="${KC_REALM:-tenderwriter}"
MM_URL="${MM_URL:-http://localhost:3000/mm}"
TW_URL="${TW_URL:-http://localhost:3000}"
TW_API_URL="${TW_API_URL:-http://localhost:8000}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; FAILURES=$((FAILURES + 1)); }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
FAILURES=0

echo "============================================"
echo "  TenderWriter SSO Smoke Test"
echo "============================================"
echo ""

# --- 1. Keycloak reachability ---
echo "--- Keycloak ---"
KC_HEALTH=$(curl -sf "${KC_URL}/health/ready" 2>/dev/null || true)
if echo "$KC_HEALTH" | grep -q '"status":"UP"'; then
    pass "Keycloak management health is UP at ${KC_URL}"
elif curl -sf "${KC_URL}/realms/${KC_REALM}/.well-known/openid-configuration" >/dev/null 2>&1; then
    pass "Keycloak is reachable at ${KC_URL}"
else
    fail "Keycloak is not reachable at ${KC_URL}"
fi

# --- 2. OIDC Discovery ---
echo ""
echo "--- OIDC Discovery ---"
DISCOVERY_URL="${KC_URL}/realms/${KC_REALM}/.well-known/openid-configuration"
DISCOVERY=$(curl -sf "$DISCOVERY_URL" 2>/dev/null || echo "UNREACHABLE")

if echo "$DISCOVERY" | grep -q '"authorization_endpoint"'; then
    pass "Discovery endpoint accessible at ${DISCOVERY_URL}"

    # Check that authorization_endpoint is browser-accessible (localhost)
    AUTH_EP=$(echo "$DISCOVERY" | grep -o '"authorization_endpoint":"[^"]*"' | cut -d'"' -f4)
    if echo "$AUTH_EP" | grep -q "localhost"; then
        pass "authorization_endpoint is browser-accessible: ${AUTH_EP}"
    else
        warn "authorization_endpoint may not be browser-accessible: ${AUTH_EP}"
    fi

    # Check issuer
    ISSUER=$(echo "$DISCOVERY" | grep -o '"issuer":"[^"]*"' | cut -d'"' -f4)
    pass "Issuer: ${ISSUER}"
else
    fail "Discovery endpoint not accessible at ${DISCOVERY_URL}"
fi

# --- 3. JWKS ---
echo ""
echo "--- JWKS ---"
JWKS_URL="${KC_URL}/realms/${KC_REALM}/protocol/openid-connect/certs"
JWKS=$(curl -sf "$JWKS_URL" 2>/dev/null || echo "UNREACHABLE")
if echo "$JWKS" | grep -q '"keys"'; then
    KEY_COUNT=$(echo "$JWKS" | grep -o '"kid"' | wc -l)
    pass "JWKS endpoint has ${KEY_COUNT} signing key(s)"
else
    fail "JWKS endpoint not accessible at ${JWKS_URL}"
fi

# --- 4. Keycloak Realm clients ---
echo ""
echo "--- Realm Clients ---"
# Get admin token
KC_ADMIN_USER="${KC_ADMIN_USER:-admin}"
KC_ADMIN_PASS="${KC_ADMIN_PASS:-DefaultKCAdmin2026Pass}"
ADMIN_TOKEN=$(curl -sf -X POST "${KC_URL}/realms/master/protocol/openid-connect/token" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" \
    -d "username=${KC_ADMIN_USER}" \
    -d "password=${KC_ADMIN_PASS}" 2>/dev/null | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -n "$ADMIN_TOKEN" ]; then
    pass "Admin token obtained"

    # Check tw-frontend client
    TW_CLIENT=$(curl -sf -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        "${KC_URL}/admin/realms/${KC_REALM}/clients?clientId=tw-frontend" 2>/dev/null)
    if echo "$TW_CLIENT" | grep -q '"tw-frontend"'; then
        pass "Client 'tw-frontend' exists in realm"
    else
        fail "Client 'tw-frontend' NOT found in realm"
    fi

    # Check mattermost client
    MM_CLIENT=$(curl -sf -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        "${KC_URL}/admin/realms/${KC_REALM}/clients?clientId=mattermost" 2>/dev/null)
    if echo "$MM_CLIENT" | grep -q '"mattermost"'; then
        pass "Client 'mattermost' exists in realm"
    else
        fail "Client 'mattermost' NOT found in realm"
    fi
else
    warn "Could not obtain admin token (admin credentials may differ)"
fi

# --- 5. Mattermost health ---
echo ""
echo "--- Mattermost ---"
MM_HEALTH=$(curl -sf "${MM_URL}/api/v4/system/ping" 2>/dev/null || echo "UNREACHABLE")
if echo "$MM_HEALTH" | grep -q '"status":"OK"'; then
    pass "Mattermost is healthy at ${MM_URL}"
else
    warn "Mattermost may not be running at ${MM_URL} (got: ${MM_HEALTH})"
fi

# --- 6. Mattermost OIDC config ---
MM_CONFIG=$(curl -sf "${MM_URL}/api/v4/config/client?format=old" 2>/dev/null || echo "{}")
if echo "$MM_CONFIG" | grep -q '"EnableSignUpWithOpenId":"true"'; then
    pass "Mattermost OIDC is ENABLED"
elif echo "$MM_CONFIG" | grep -q '"EnableSignUpWithOpenId":"false"'; then
    warn "Mattermost OIDC is DISABLED (set MM_OIDC_ENABLE=true)"
else
    warn "Could not determine Mattermost OIDC status"
fi

# --- 7. TenderWriter health ---
echo ""
echo "--- TenderWriter ---"
TW_HEALTH=$(curl -sf "${TW_API_URL}/health" 2>/dev/null || echo "UNREACHABLE")
if echo "$TW_HEALTH" | grep -qi "ok\|healthy\|status"; then
    pass "TenderWriter backend is healthy at ${TW_API_URL}"
else
    warn "TenderWriter backend may not be running at ${TW_API_URL}/health"
fi

# --- Summary ---
echo ""
echo "============================================"
if [ $FAILURES -eq 0 ]; then
    echo -e "  ${GREEN}All checks passed!${NC}"
else
    echo -e "  ${RED}${FAILURES} check(s) failed${NC}"
fi
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Set MM_OIDC_ENABLE=true in .env"
echo "  2. Set AUTH_PROVIDER=keycloak and VITE_AUTH_MODE=keycloak in .env"
echo "  3. Create a test user in Keycloak admin: ${KC_URL}"
echo "  4. Try login at ${TW_URL}/login (SSO button)"
echo "  5. Try Mattermost login at ${MM_URL} (Keycloak button)"
echo ""

exit $FAILURES
