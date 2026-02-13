# MockFactory.io OIDC/OAuth Setup with Authentik

**Status:** ✅ Configured on Production Server
**Date:** February 12, 2026
**Authentik Server:** https://adsas.id

---

## Production Configuration

The MockFactory.io API has been configured with the following OIDC credentials:

```bash
OAUTH_CLIENT_ID=mockfactory
OAUTH_CLIENT_SECRET=Vpb25obWwu7Ks4FfLPSs3HHeBthvgaeeDm5umZfMTbc
OAUTH_AUTHORIZE_URL=https://adsas.id/application/o/authorize/
OAUTH_TOKEN_URL=https://adsas.id/application/o/token/
OAUTH_USERINFO_URL=https://adsas.id/application/o/userinfo/
OAUTH_LOGOUT_URL=https://adsas.id/application/o/mockfactory/end-session/
OAUTH_PROVIDER_NAME=Authentik
```

**Redirect URIs:**
- https://mockfactory.io/api/v1/auth/oidc/callback
- https://mockfactory.io/auth/callback
- http://localhost:8000/api/v1/auth/oidc/callback (for local testing)

---

## Authentik Provider Setup

### Option 1: Automated Setup (Recommended)

Use the setup script:

```bash
# Get an Authentik API token from https://adsas.id/if/admin/
export AUTHENTIK_TOKEN='your-token-here'

# Run the setup script
/tmp/setup-mockfactory-authentik.sh
```

### Option 2: Manual Setup via Web UI

1. **Log into Authentik Admin**
   - URL: https://adsas.id/if/admin/

2. **Create OAuth2/OIDC Provider**
   - Navigate to **Applications → Providers**
   - Click **Create**
   - Select **OAuth2/OpenID Provider**

   **Provider Settings:**
   - Name: `MockFactory.io`
   - Authorization flow: `default-provider-authorization-implicit-consent`
   - Client type: `Confidential`
   - Client ID: `mockfactory`
   - Client Secret: `Vpb25obWwu7Ks4FfLPSs3HHeBthvgaeeDm5umZfMTbc`
   - Redirect URIs:
     ```
     https://mockfactory.io/api/v1/auth/oidc/callback
     https://mockfactory.io/auth/callback
     http://localhost:8000/api/v1/auth/oidc/callback
     ```
   - Sub mode: `Hashed user ID`
   - Issuer mode: `Per provider`
   - Signing Key: Select default signing key

3. **Create Application**
   - Navigate to **Applications → Applications**
   - Click **Create**

   **Application Settings:**
   - Name: `MockFactory.io`
   - Slug: `mockfactory`
   - Provider: Select the provider created above
   - Launch URL: `https://mockfactory.io`
   - Description: `Cloud development environment platform with PostgreSQL-first testing environments`
   - Publisher: `MockFactory`
   - Policy engine mode: `Any`
   - Open in new tab: ✓

4. **Save and Test**
   - Click **Create**
   - Test the OAuth flow by visiting https://mockfactory.io

---

## OIDC Endpoints

Once the provider is created in Authentik, the following endpoints will be available:

- **Issuer:** `https://adsas.id/application/o/mockfactory/`
- **Authorization:** `https://adsas.id/application/o/authorize/`
- **Token:** `https://adsas.id/application/o/token/`
- **UserInfo:** `https://adsas.id/application/o/userinfo/`
- **JWKS:** `https://adsas.id/application/o/mockfactory/jwks/`
- **End Session:** `https://adsas.id/application/o/mockfactory/end-session/`
- **OpenID Configuration:** `https://adsas.id/application/o/mockfactory/.well-known/openid-configuration`

---

## Testing the OAuth Flow

### 1. Test Authorization Endpoint

```bash
curl -I "https://adsas.id/application/o/authorize/?client_id=mockfactory&redirect_uri=https://mockfactory.io/api/v1/auth/oidc/callback&response_type=code&scope=openid+profile+email"
```

Should return a 302 redirect to the Authentik login page.

### 2. Test Discovery Endpoint

```bash
curl -s "https://adsas.id/application/o/mockfactory/.well-known/openid-configuration" | jq
```

Should return the OIDC discovery document with all endpoints.

### 3. Test Full OAuth Flow

1. Visit https://mockfactory.io
2. Click "Sign in with SSO" or OAuth login button
3. Should redirect to Authentik login at adsas.id
4. Log in with Authentik credentials
5. Should redirect back to MockFactory.io with authentication

---

## API Integration

The MockFactory.io API `/api/v1/auth/` endpoints now support OAuth/OIDC:

- **GET `/api/v1/auth/oidc/login`** - Initiate OAuth flow
- **GET `/api/v1/auth/oidc/callback`** - OAuth callback handler
- **POST `/api/v1/auth/oidc/logout`** - Logout and end OIDC session

---

## Troubleshooting

### OAuth Flow Fails

**Check provider configuration:**
```bash
curl -s -H "Authorization: Bearer $AUTHENTIK_TOKEN" \
  https://adsas.id/api/v3/providers/oauth2/ | jq '.results[] | select(.client_id == "mockfactory")'
```

### Invalid Client Error

Verify the client ID and secret match in both:
1. Authentik provider configuration
2. MockFactory.io `.env` file on the production server

### Redirect URI Mismatch

Ensure all redirect URIs are added to the Authentik provider:
- Exact match required (no trailing slashes unless specified)
- HTTPS required for production URIs

### Check API Configuration

SSH to production server and verify environment:
```bash
ssh opc@129.213.31.167
cd mockfactory
grep OAUTH .env
docker compose -f docker-compose.prod.yml logs api | grep -i oauth
```

---

## Security Notes

- ✅ Client secret is securely generated (32-byte URL-safe token)
- ✅ Confidential client type prevents token exposure
- ✅ HTTPS enforced for all production redirect URIs
- ✅ Hashed user IDs prevent user enumeration
- ⚠️ Client secret stored in `.env` - ensure proper file permissions
- ⚠️ Rotate client secret periodically (every 90 days recommended)

---

## Next Steps

1. **Complete Authentik Setup**
   - Run `/tmp/setup-mockfactory-authentik.sh` or manually create provider
   - Verify provider appears in https://adsas.id/if/admin/

2. **Test OAuth Flow**
   - Attempt login via https://mockfactory.io
   - Verify successful authentication
   - Check API logs for any OIDC errors

3. **Add OAuth Button to Frontend**
   - Update `frontend/index.html` with "Sign in with SSO" button
   - Link to `/api/v1/auth/oidc/login`

4. **Configure User Provisioning**
   - Set up automatic user creation on first OIDC login
   - Map Authentik claims to MockFactory user attributes

---

## Files Modified

- `/home/opc/mockfactory/.env` - Updated with OAuth credentials
- Production API container - Restarted with new config

## Related Documentation

- Authentik OAuth2/OIDC Provider: https://docs.goauthentik.io/docs/providers/oauth2
- OpenID Connect Specification: https://openid.net/specs/openid-connect-core-1_0.html
- MockFactory API Docs: https://mockfactory.io/docs

---

*Configuration generated: 2026-02-12*
*Last updated: 2026-02-12*
