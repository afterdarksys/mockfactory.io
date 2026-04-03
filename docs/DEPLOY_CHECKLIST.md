# Deployment Checklist

## Pre-Deployment

- [x] All files committed to git
- [ ] `.env` has ANTHROPIC_API_KEY (get from https://console.anthropic.com/)
- [x] `requirements.txt` includes anthropic package
- [x] Database migration SQL ready (migration_ai.sql)
- [x] Admin access script ready

## Deployment Steps

### Option 1: Automated (Recommended) ⚡

```bash
export SERVER_IP=your.server.ip.address
export ANTHROPIC_API_KEY=sk-ant-api03-xxx  # Optional but recommended
./deploy-with-ai.sh
```

This handles everything automatically! ✅

### Option 2: Manual

1. **Upload Files**
   ```bash
   rsync -avz --exclude 'node_modules' --exclude '__pycache__' \
     ./ ubuntu@your-server:/opt/mockfactory/
   ```

2. **SSH to Server**
   ```bash
   ssh ubuntu@your-server
   cd /opt/mockfactory
   ```

3. **Add API Key to .env** (on server)
   ```bash
   echo "ANTHROPIC_API_KEY=sk-ant-xxx" >> .env
   ```

4. **Run Database Migration**
   ```bash
   # Make sure postgres is running
   docker-compose -f docker-compose.prod.yml up -d postgres
   sleep 5

   # Run migration
   docker exec -i mockfactory_postgres_1 \
     psql -U mockfactory -d mockfactory < migration_ai.sql
   ```

5. **Rebuild & Restart Containers**
   ```bash
   docker-compose -f docker-compose.prod.yml down
   docker-compose -f docker-compose.prod.yml build
   docker-compose -f docker-compose.prod.yml up -d
   ```

6. **Verify Deployment**
   ```bash
   # Check containers
   docker-compose ps

   # Check logs
   docker-compose logs -f mockfactory

   # Test endpoints
   curl https://mockfactory.io/
   curl https://mockfactory.io/app.html
   curl https://mockfactory.io/docs
   ```

## Post-Deployment Verification

### 1. Website & Dashboard
- [ ] Landing page loads: https://mockfactory.io/
- [ ] Dashboard loads: https://mockfactory.io/app.html
- [ ] Can sign in with SSO (rjc@afterdarksys.com)
- [ ] No JavaScript errors in console

### 2. AI Assistant
- [ ] Chat icon appears in bottom-right corner
- [ ] Click chat icon - sidebar slides in
- [ ] Shows "Tier: employee · Unlimited"
- [ ] Send message: "Hello Claude!"
- [ ] Get intelligent response within 2-3 seconds
- [ ] Message count updates

### 3. Database
```bash
# SSH to server and check
ssh ubuntu@your-server

# Verify ai_usage table exists
docker exec mockfactory_postgres_1 \
  psql -U mockfactory -d mockfactory \
  -c "\d ai_usage"

# Check admin user
docker exec mockfactory_postgres_1 \
  psql -U mockfactory -d mockfactory \
  -c "SELECT email, is_employee, tier FROM users WHERE email = 'rjc@afterdarksys.com';"

# Check if any AI messages recorded
docker exec mockfactory_postgres_1 \
  psql -U mockfactory -d mockfactory \
  -c "SELECT COUNT(*), SUM(profit) FROM ai_usage;"
```

### 4. Logs
```bash
# Should see these in logs:
# "AI Assistant enabled with model: claude-3-5-haiku-20241022"
# "MockFactory.io starting up..."
# "Background tasks started successfully"

docker-compose logs mockfactory | grep -i "ai\|claude\|error"
```

## Testing AI Features

### Basic Test
1. Go to https://mockfactory.io/app.html
2. Sign in with rjc@afterdarksys.com
3. Click chat icon
4. Send: "Hello! Can you help me?"
5. Should get friendly response

### SQL Generation Test
1. Send: "Generate a sample SQL query to create a users table"
2. Should get proper CREATE TABLE statement
3. Code should be in monospace font

### Context-Aware Test
1. Create an environment in the dashboard
2. Ask: "What environments do I have?"
3. Should mention your environment (context-aware)

### Cost Tracking Test
1. Send several messages
2. Check database:
   ```sql
   SELECT
     COUNT(*) as messages_sent,
     SUM(api_cost) as anthropic_cost,
     SUM(user_cost) as charged_to_user,
     SUM(profit) as your_profit
   FROM ai_usage
   WHERE user_id = (SELECT id FROM users WHERE email = 'rjc@afterdarksys.com');
   ```
3. Should see profit calculations

## Rollback (if needed)

```bash
# SSH to server
ssh ubuntu@your-server
cd /opt/mockfactory

# Option 1: Just disable AI (keep everything else)
# Remove API key from .env
sed -i '/ANTHROPIC_API_KEY/d' .env
docker-compose restart mockfactory

# Option 2: Revert database (removes ai_usage table)
docker exec mockfactory_postgres_1 \
  psql -U mockfactory -d mockfactory \
  -c "DROP TABLE IF EXISTS ai_usage CASCADE;"

# Option 3: Full rollback (previous git commit)
git log --oneline | head -5  # Find previous commit
git checkout <previous-commit>
docker-compose -f docker-compose.prod.yml up -d --build
```

## Monitoring Production

### Real-time Logs
```bash
# All services
docker-compose logs -f

# Just API
docker-compose logs -f mockfactory

# Just database
docker-compose logs -f postgres
```

### AI Usage Dashboard (SQL)
```sql
-- Today's AI stats
SELECT
    COUNT(*) as total_messages,
    COUNT(DISTINCT user_id) as unique_users,
    SUM(api_cost) as anthropic_charged_us,
    SUM(user_cost) as we_charged_users,
    SUM(profit) as net_profit,
    AVG(profit) as avg_profit_per_message
FROM ai_usage
WHERE created_at > CURRENT_DATE;

-- This week's top users
SELECT
    u.email,
    u.tier,
    COUNT(*) as messages,
    ROUND(SUM(ai.profit)::numeric, 2) as profit_generated
FROM ai_usage ai
JOIN users u ON ai.user_id = u.id
WHERE ai.created_at > NOW() - INTERVAL '7 days'
GROUP BY u.email, u.tier
ORDER BY profit_generated DESC
LIMIT 10;

-- Hourly usage pattern
SELECT
    DATE_TRUNC('hour', created_at) as hour,
    COUNT(*) as messages,
    ROUND(SUM(profit)::numeric, 2) as profit
FROM ai_usage
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;
```

### Anthropic Dashboard
Visit: https://console.anthropic.com/settings/usage
- Check daily spend
- Monitor rate limits
- View usage graphs

### Alerts to Set Up
1. **High Cost Alert** - If daily Anthropic cost > $10
2. **Error Rate Alert** - If AI errors > 5%
3. **Usage Spike** - If hourly messages > 100
4. **Low Balance** - If Anthropic credits < $5

## Troubleshooting

### "Connection refused" to postgres
```bash
# Start postgres first
docker-compose -f docker-compose.prod.yml up -d postgres
sleep 10  # Wait for startup
# Then run migration
```

### "Role mockfactory does not exist"
```bash
# Create database user
docker exec mockfactory_postgres_1 \
  psql -U postgres -c "CREATE USER mockfactory WITH PASSWORD 'your-password';"
docker exec mockfactory_postgres_1 \
  psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE mockfactory TO mockfactory;"
```

### "AI Assistant is not configured"
```bash
# Check if API key is set
docker exec mockfactory_api_1 printenv | grep ANTHROPIC

# If not, add to .env and restart
echo "ANTHROPIC_API_KEY=sk-ant-xxx" >> .env
docker-compose restart
```

### "402 Payment Required" when testing AI
```bash
# Your user tier isn't set correctly
docker exec mockfactory_postgres_1 \
  psql -U mockfactory -d mockfactory \
  -c "UPDATE users SET tier='employee', is_employee=TRUE WHERE email='rjc@afterdarksys.com';"
```

### Chat icon not appearing
- Check browser console for JS errors
- Verify app.html loaded correctly
- Clear browser cache
- Check that claude-assistant-real.js is loaded

### AI responds but no data in database
- Check database connection in logs
- Verify ai_usage table exists
- Check user_id is correct in requests

## Success Criteria ✅

Your deployment is successful when:

- [x] Landing page loads without errors
- [x] Dashboard fully functional
- [x] Can sign in with SSO
- [x] AI chat icon visible and clickable
- [x] AI responds to messages correctly
- [x] Database records AI usage
- [x] Admin user has unlimited access
- [x] No errors in Docker logs
- [x] SSL certificates valid
- [x] All API endpoints responding

## What's New in This Deployment

### Features Added ✨
- Interactive dashboard UI (app.html)
- Real Claude AI assistant integration
- Paywalled AI with tier-based access
- Usage tracking and profitability analytics
- Admin/employee unlimited access
- Cost transparency ($X.XX per message)

### Files Changed 📝
- `app/main.py` - Added AI router
- `app/models/` - New ai_usage model
- `app/api/` - New ai_assistant endpoint
- `frontend/` - Complete new dashboard
- `requirements.txt` - Added anthropic SDK

### Database Changes 💾
- New table: `ai_usage` (tracks all AI interactions)
- Updated: `users.tier` values (added 'employee')
- Updated: `users.is_employee` flags

### Revenue Model 💰
- Student: $4.99/mo - 10 msgs/day
- Professional: $19.99/mo - 100 msgs/day
- Employee: Free - Unlimited
- Profit margin: 80-90% 🚀

## Next Steps After Deployment

1. **Monitor First 24 Hours**
   - Watch logs for errors
   - Check Anthropic usage dashboard
   - Test with real users

2. **Invite Beta Testers**
   - Upgrade 5-10 users to Student tier
   - Get feedback on AI quality
   - Monitor usage patterns

3. **Set Up Analytics**
   - Daily revenue reports
   - User conversion tracking
   - AI usage dashboards

4. **Marketing Launch**
   - Announce AI assistant feature
   - Create demo videos
   - Update website copy

5. **Iterate**
   - Adjust pricing based on usage
   - Add more AI features (SQL execution, etc.)
   - Scale up as needed

---

**Questions?** Check:
- `DEPLOY.md` - Full deployment guide
- `MONETIZE_CLAUDE.md` - How to make money
- `AI_ASSISTANT_SETUP.md` - Technical details
