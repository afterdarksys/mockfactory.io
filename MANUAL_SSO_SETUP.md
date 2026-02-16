# MockFactory SSO - Manual Setup (Because Authentik Permissions Suck)

This is the manual workaround until we have proper infrastructure tooling.

## The Problem

- Authentik tokens need specific permissions to create providers/apps via API
- Can't create those tokens programmatically without existing privileged tokens
- UI is the only way to bootstrap (chicken-and-egg problem)

## The Solution (2 Minutes Manual)

### Step 1: Create OAuth Provider

1. Go to: https://adsas.id/if/admin/#/core/providers
2. Click "Create" → "OAuth2/OpenID Provider"
3. Fill in:
   - **Name**: `MockFactory OAuth Provider`
   - **Authorization flow**: `default-authentication-flow`
   - **Client type**: `Confidential`
   - **Client ID**: `mockfactory`
   - **Client Secret**: Click "Generate" (copy this!)
   - **Redirect URIs**:
     ```
     https://mockfactory.io/api/v1/auth/sso/callback
     https://www.mockfactory.io/api/v1/auth/sso/callback
     ```
   - **Scopes**: Select `openid`, `email`, `profile`, `offline_access`
   - **Subject mode**: `Based on the User's hashed ID`
   - **Include claims in ID token**: ✅ Checked

4. Click "Create"

### Step 2: Create Application

1. Go to: https://adsas.id/if/admin/#/core/applications
2. Click "Create"
3. Fill in:
   - **Name**: `MockFactory`
   - **Slug**: `mockfactory`
   - **Provider**: Select the provider you just created
   - **Launch URL**: `https://mockfactory.io`

4. Click "Create"

### Step 3: Update MockFactory Config

Update `/Users/ryan/development/mockfactory.io/.env`:
```bash
OAUTH_CLIENT_ID=mockfactory
OAUTH_CLIENT_SECRET=<paste_the_secret_from_step_1>
```

Update production:
```bash
ssh opc@129.213.31.167
nano /home/opc/mockfactory/.env
# Update OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET
docker compose -f docker-compose.prod.yml restart api
```

### Step 4: Test

Go to: https://mockfactory.io/login.html
Click "Sign in with After Dark Systems"

## The REAL Solution (TODO)

Build proper infrastructure tooling that:
1. Uses Authentik's management commands directly via container exec
2. Or uses database-level token creation
3. Or uses a bootstrap token stored in secure vault
4. Fully automates this without any UI clicking

This is 2026, we shouldn't be clicking through UIs to configure infrastructure.
