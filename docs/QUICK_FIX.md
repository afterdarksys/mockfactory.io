# Quick Fix - Add MockFactory to Existing OAuth Provider

## The Smart Way (You Were Right!)

Instead of creating a NEW OAuth provider, we should add MockFactory to the EXISTING After Dark Systems provider.

## What to Do (30 seconds):

1. Go to: https://adsas.id/if/admin/#/core/providers
2. Find the "After Dark Systems" provider (or "after-dark-sys-main")
3. Click Edit
4. Find "Redirect URIs" field
5. Add these two lines:
   ```
   https://mockfactory.io/api/v1/auth/sso/callback
   https://www.mockfactory.io/api/v1/auth/sso/callback
   ```
6. Click "Update"

## Done!

Now test at: https://mockfactory.io/login.html

All After Dark Systems users will be able to login to MockFactory with their existing credentials!

## Why This is Better:

- ✅ One provider for ALL After Dark Systems services
- ✅ Single Sign-On across entire platform
- ✅ Users only authenticate ONCE
- ✅ Centralized user management
- ✅ Consistent permissions/groups across all services

## Current Config:

```bash
OAUTH_CLIENT_ID=MTXBKk8uGrO6KbC2djGR7oVNS0qEcg5WRWKeuWrc
OAUTH_CLIENT_SECRET=5PDljtcenYj2UcTa6L4vpxmFrDKcEQhvBuVTIKl18xXtnEgQ6BtOAlFjIui5mRQEZpFmC3mKtlhhWbHqTBdOgU1hdGTtFvbGiNshPXN0z6TLgj6ZrcLk2QN0Hparnj2y
```

Both local and production configs are updated ✅
API has been restarted ✅

Just add the redirect URIs to the provider and we're DONE!
