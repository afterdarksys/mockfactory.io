# 🚀 Deployment Guide

## Quick Deploy (All-in-One)

Deploy MockFactory with the new AI assistant feature:

```bash
# Set your server IP and API key
export SERVER_IP=your.server.ip.address
export ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxx

# Deploy everything
./deploy-with-ai.sh
```

This script will:
1. ✅ Create deployment package with all new AI features
2. ✅ Upload to your OCI server
3. ✅ Run database migrations (add `ai_usage` table)
4. ✅ Build and start Docker containers
5. ✅ Grant you admin access (rjc@afterdarksys.com)
6. ✅ Verify deployment

## Step-by-Step Manual Deployment

### 1. Prepare Local Environment

```bash
# Install dependencies
pip install -r requirements.txt

# Get Anthropic API key
# Visit: https://console.anthropic.com/
# Add at least $5 in credits
# Copy your API key
```

### 2. Configure Environment

Add to your `.env` file:

```bash
# Add AI Assistant
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. Run Database Migration

**Option A: Using Alembic** (if you have local DB)
```bash
alembic upgrade head
```

**Option B: Manual SQL**
```bash
# Connect to your database
psql $DATABASE_URL

# Run migration
\i alembic/versions/add_ai_usage_table.py
```

**Option C: Production Database** (on server)
```bash
# SSH to server
ssh ubuntu@your-server-ip

# Connect to database
docker exec -it mockfactory_postgres_1 psql -U mockfactory -d mockfactory

# Run this SQL:
CREATE TABLE IF NOT EXISTS ai_usage (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    prompt TEXT NOT NULL,
    response TEXT NOT NULL,
    model VARCHAR NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    api_cost FLOAT NOT NULL,
    user_cost FLOAT NOT NULL,
    profit FLOAT NOT NULL,
    session_id VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_ai_usage_user_id ON ai_usage(user_id);
CREATE INDEX IF NOT EXISTS ix_ai_usage_created_at ON ai_usage(created_at);
```

### 4. Grant Admin Access

```bash
# Option A: Python script
python scripts/grant_admin.py rjc@afterdarksys.com

# Option B: SQL script
psql $DATABASE_URL -f scripts/grant_admin.sql

# Option C: Manual SQL
psql $DATABASE_URL -c "
UPDATE users
SET is_employee = TRUE, tier = 'employee', is_active = TRUE
WHERE email = 'rjc@afterdarksys.com';
"
```

### 5. Deploy to Server

**Using existing deploy script:**
```bash
SERVER_IP=your.server.ip ./deploy-production.sh
```

**Or use the new AI-enabled script:**
```bash
SERVER_IP=your.server.ip \
ANTHROPIC_API_KEY=sk-ant-xxx \
./deploy-with-ai.sh
```

## Verify Deployment

### 1. Check Website

```bash
# Landing page
curl https://mockfactory.io/

# Dashboard
curl https://mockfactory.io/app.html

# API health
curl https://mockfactory.io/api/v1/ai/usage
```

### 2. Check Database

```bash
# SSH to server
ssh ubuntu@your-server-ip

# Check ai_usage table exists
docker exec -it mockfactory_postgres_1 \
  psql -U mockfactory -d mockfactory \
  -c "\d ai_usage"

# Check your admin account
docker exec -it mockfactory_postgres_1 \
  psql -U mockfactory -d mockfactory \
  -c "SELECT email, is_employee, tier FROM users WHERE email = 'rjc@afterdarksys.com';"
```

### 3. Test AI Assistant

1. Go to: https://mockfactory.io/app.html
2. Sign in with SSO (rjc@afterdarksys.com)
3. Click chat icon in bottom-right
4. Should see: "Tier: employee · Unlimited"
5. Send a message to Claude
6. Verify response comes back!

## Environment Variables

Make sure your production `.env` has:

```bash
# Database
DATABASE_URL=postgresql://mockfactory:password@postgres:5432/mockfactory

# AI Assistant
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxx

# Authentik SSO (your existing setup)
AUTHENTIK_CLIENT_ID=...
AUTHENTIK_CLIENT_SECRET=...
AUTHENTIK_OIDC_URL=...

# Stripe (your existing setup)
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
```

## Deployment Checklist

- [ ] `requirements.txt` includes `anthropic==0.39.0`
- [ ] `.env` has `ANTHROPIC_API_KEY`
- [ ] Database migration run (ai_usage table created)
- [ ] Admin access granted (rjc@afterdarksys.com)
- [ ] Frontend updated with new dashboard
- [ ] Docker containers rebuilt and restarted
- [ ] SSL certificates valid
- [ ] API responding at /api/v1/ai/chat
- [ ] Dashboard accessible at /app.html
- [ ] Chat icon visible in UI
- [ ] AI assistant responds to messages

## Troubleshooting

### "Connection refused" during migration
Database isn't running yet. Start it first:
```bash
docker-compose up -d postgres
sleep 5  # Wait for startup
alembic upgrade head
```

### "AI Assistant is not configured"
Missing `ANTHROPIC_API_KEY` in environment:
```bash
# Add to .env
echo "ANTHROPIC_API_KEY=sk-ant-xxx" >> .env

# Restart containers
docker-compose restart
```

### "Table already exists"
Migration already ran. Skip it or check:
```sql
SELECT COUNT(*) FROM ai_usage;  -- Should work
```

### "User not found"
Create admin account manually:
```bash
python scripts/grant_admin.py rjc@afterdarksys.com
```

### "402 Payment Required" error
Your user tier isn't set correctly:
```sql
UPDATE users SET tier='employee', is_employee=TRUE WHERE email='rjc@afterdarksys.com';
```

## Files Changed/Added

### New Files
- `app/models/ai_usage.py` - AI usage tracking model
- `app/api/ai_assistant.py` - Claude API endpoint
- `frontend/app.html` - New dashboard UI
- `frontend/static/js/app.js` - Dashboard logic
- `frontend/static/js/claude-assistant-real.js` - Real AI integration
- `frontend/static/js/claude-assistant.js` - Demo version
- `scripts/grant_admin.py` - Admin access script
- `scripts/grant_admin.sql` - SQL version
- `alembic/versions/add_ai_usage_table.py` - Migration
- `deploy-with-ai.sh` - All-in-one deploy script

### Modified Files
- `app/main.py` - Added AI router
- `frontend/index.html` - Updated links to dashboard
- `requirements.txt` - Added anthropic SDK
- `.env` - Added ANTHROPIC_API_KEY

## Rollback

If something goes wrong:

```bash
# Revert database
psql $DATABASE_URL -c "DROP TABLE IF EXISTS ai_usage;"

# Revert code
git checkout main
./deploy-production.sh

# Or just disable AI
# Remove ANTHROPIC_API_KEY from .env
# Edit app.html to use fake assistant:
# <script src="static/js/claude-assistant.js"></script>
```

## Monitoring

### Check AI Usage
```bash
# SSH to server
ssh ubuntu@your-server-ip

# View logs
docker-compose logs -f mockfactory

# Check AI usage in DB
docker exec -it mockfactory_postgres_1 \
  psql -U mockfactory -d mockfactory \
  -c "SELECT COUNT(*), SUM(profit) FROM ai_usage WHERE created_at > NOW() - INTERVAL '24 hours';"
```

### Monitor Costs
```sql
-- Today's AI profit
SELECT
    COUNT(*) as messages,
    SUM(api_cost) as anthropic_charged_us,
    SUM(user_cost) as we_charged_users,
    SUM(profit) as our_profit
FROM ai_usage
WHERE created_at > CURRENT_DATE;

-- Top users this week
SELECT
    u.email,
    COUNT(*) as messages,
    SUM(ai.profit) as profit_generated
FROM ai_usage ai
JOIN users u ON ai.user_id = u.id
WHERE ai.created_at > NOW() - INTERVAL '7 days'
GROUP BY u.email
ORDER BY profit_generated DESC;
```

## Next Steps

After deployment:

1. **Test Everything** - Make sure AI works end-to-end
2. **Monitor Costs** - Watch Anthropic usage dashboard
3. **Invite Beta Users** - Get feedback on AI features
4. **Set Pricing** - Decide on tier prices ($4.99/$19.99/etc)
5. **Marketing** - Promote the AI assistant!

## Support

Questions? Check:
- `MONETIZE_CLAUDE.md` - Revenue model
- `AI_ASSISTANT_SETUP.md` - Technical setup
- `PRICING_MODEL.md` - Financial projections

Or just ask Claude! 😉
