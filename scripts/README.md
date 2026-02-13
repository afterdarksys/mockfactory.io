# Admin Scripts

## Grant Admin Access

Grant yourself (or any user) admin/employee access with unlimited AI assistant usage.

### Method 1: Python Script (Recommended)

```bash
# Grant admin access to your SSO email
python scripts/grant_admin.py rjc@afterdarksys.com

# Or any other email
python scripts/grant_admin.py user@example.com
```

**What this does:**
- Sets `is_employee = True`
- Sets `tier = 'employee'`
- Grants unlimited AI messages
- Gives access to all premium features

### Method 2: SQL Script

```bash
# If you prefer SQL directly
psql $DATABASE_URL -f scripts/grant_admin.sql

# Or manually connect and paste the SQL
psql mockfactory < scripts/grant_admin.sql
```

### Method 3: Manual SQL

```sql
-- Connect to your database
psql mockfactory

-- Grant admin access
UPDATE users
SET
    is_employee = TRUE,
    tier = 'employee',
    is_active = TRUE
WHERE email = 'rjc@afterdarksys.com';

-- Verify
SELECT email, is_employee, tier FROM users WHERE email = 'rjc@afterdarksys.com';
```

## Employee Benefits

Once granted employee access, you get:

✅ **Unlimited Environments** - Create as many as you need
✅ **Unlimited AI Messages** - Chat with Claude without limits
✅ **$0 Cost** - Employee perk, no charges
✅ **Priority Support** - Because you work here!
✅ **All Features** - Access to everything

## Checking Your Access

```bash
# Via API (requires auth token)
curl http://localhost:8000/api/v1/ai/usage \
  -H "Authorization: Bearer YOUR_TOKEN"

# Should return:
# {
#   "tier": "employee",
#   "daily_limit": 99999,
#   "daily_used": 0,
#   "daily_remaining": 99999,
#   "has_access": true
# }
```

## Testing

After granting admin access:

1. Sign in with SSO: `rjc@afterdarksys.com`
2. Go to dashboard: http://localhost:8000/app.html
3. Click chat icon (bottom-right)
4. Should see: "Tier: employee · Unlimited"
5. Chat away! No paywalls, no limits 🎉

## Revoking Admin Access

```sql
-- Downgrade to Professional
UPDATE users
SET
    is_employee = FALSE,
    tier = 'professional'
WHERE email = 'user@example.com';

-- Or completely disable
UPDATE users
SET is_active = FALSE
WHERE email = 'user@example.com';
```
