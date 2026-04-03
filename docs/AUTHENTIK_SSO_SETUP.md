# Authentik SSO Setup for MockFactory

This guide will help you configure Authentik OAuth2/OIDC integration for MockFactory.io

## Step 1: Create OAuth2/OIDC Provider in Authentik

1. Login to your Authentik admin panel at: **https://auth.afterdarksystems.com**

2. Navigate to **Applications** → **Providers**

3. Click **Create** and select **OAuth2/OpenID Provider**

4. Configure the provider:
   - **Name**: `MockFactory OAuth Provider`
   - **Authorization flow**: `default-authentication-flow (or your custom flow)`
   - **Client type**: `Confidential`
   - **Client ID**: `mockfactory` (or your preferred client ID)
   - **Client Secret**: Generate a strong secret (save this for .env file)
   - **Redirect URIs**:
     ```
     https://mockfactory.io/api/v1/auth/sso/callback
     https://www.mockfactory.io/api/v1/auth/sso/callback
     ```
   - **Scopes**: Select the following:
     - `openid` (required)
     - `email` (required)
     - `profile` (recommended)

5. **Advanced settings**:
   - **Subject mode**: `Based on the User's hashed ID`
   - **Include claims in ID token**: ✅ Enabled
   - **Issuer mode**: `Per Provider`

6. Click **Create**

## Step 2: Create Application in Authentik

1. Navigate to **Applications** → **Applications**

2. Click **Create**

3. Configure the application:
   - **Name**: `MockFactory`
   - **Slug**: `mockfactory`
   - **Provider**: Select the provider you just created
   - **Launch URL**: `https://mockfactory.io`
   - **Icon**: (Optional) Upload MockFactory logo

4. Click **Create**

## Step 3: Configure Group Mappings (Optional but Recommended)

To automatically grant employee access based on Authentik groups:

1. Navigate to **Customization** → **Property Mappings**

2. Create a new **Scope Mapping**:
   - **Name**: `MockFactory Groups Scope`
   - **Scope name**: `groups`
   - **Expression**:
     ```python
     return {
         "groups": [group.name for group in user.ak_groups.all()]
     }
     ```

3. Add this scope mapping to your OAuth provider:
   - Go back to your provider
   - Under **Scope Mappings**, add the `groups` mapping

## Step 4: Update MockFactory .env File

Update your `.env` file with the Authentik credentials:

```bash
# OAuth/OIDC Configuration
OAUTH_CLIENT_ID=mockfactory  # Use your client ID from Step 1
OAUTH_CLIENT_SECRET=your_secret_from_step_1  # Use the secret you generated
OAUTH_AUTHORIZE_URL=https://auth.afterdarksystems.com/application/o/authorize/
OAUTH_TOKEN_URL=https://auth.afterdarksystems.com/application/o/token/
OAUTH_USERINFO_URL=https://auth.afterdarksystems.com/application/o/userinfo/
OAUTH_LOGOUT_URL=https://auth.afterdarksystems.com/application/o/mockfactory/end-session/
OAUTH_PROVIDER_NAME=After Dark Systems
```

## Step 5: Restart MockFactory Services

```bash
# On production server
cd /home/opc/mockfactory
docker compose -f docker-compose.prod.yml restart api
```

## Step 6: Test SSO Login

1. Go to **https://mockfactory.io/login.html**
2. Click **"Sign in with After Dark Systems"**
3. You should be redirected to Authentik
4. Login with your After Dark Systems credentials
5. You should be redirected back to MockFactory dashboard

## Automatic Tier Assignment

Users are automatically assigned tiers based on:

1. **Email Domain**:
   - `@afterdarksystems.com` → Employee tier (unlimited)

2. **Authentik Groups**:
   - `employees` or `afterdark-employees` → Employee tier (unlimited)
   - `students` → Student tier (25 runs/month)
   - None of the above → Beginner tier (10 runs/month)

## Troubleshooting

### Error: "Invalid redirect URI"
- Make sure both `https://mockfactory.io/api/v1/auth/sso/callback` and `https://www.mockfactory.io/api/v1/auth/sso/callback` are added to Authentik provider

### Error: "Failed to get user info"
- Verify that `email` and `profile` scopes are enabled in the provider
- Check that the client secret matches between Authentik and .env file

### Error: "Invalid client credentials"
- Double-check OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET in .env
- Restart the API container after updating .env

### Users not getting employee tier
- Ensure group mappings are configured (Step 3)
- Verify users are in the correct Authentik groups
- Check that the `groups` scope is included in the OAuth provider

## Security Notes

1. **Client Secret**: Keep the OAuth client secret secure. Never commit it to git.
2. **HTTPS Only**: SSO will only work over HTTPS in production
3. **State Validation**: The current implementation has basic state validation. For production, consider implementing Redis-backed state management.
4. **Session Security**: JWT tokens expire after 30 minutes by default (configurable via ACCESS_TOKEN_EXPIRE_MINUTES)

## Integration with Other After Dark Systems Services

This same Authentik instance can be used for:
- **DarkStorage** - File storage service
- **AEIMS** - AI Email Intelligence Management System
- **HostScience** - DNS and network intelligence
- **WebScience** - Web reconnaissance platform

Just create separate OAuth providers/applications in Authentik for each service using this same pattern.
