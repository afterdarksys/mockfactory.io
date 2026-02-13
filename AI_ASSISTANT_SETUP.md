# AI Assistant Setup Guide

## Overview
The AI Assistant is a **paywalled feature** that uses Claude 3.5 Haiku to provide intelligent help with PostgreSQL, SQL generation, and database concepts. It's gated behind paid tiers and generates profit through markup pricing.

## Prerequisites

1. **Anthropic API Key**
   - Sign up at https://console.anthropic.com/
   - Create an API key
   - Add at least $5 in credits

2. **Database Migration**
   - Run the migration to create the `ai_usage` table
   - Tracks all AI interactions and costs

3. **Updated User Tiers**
   - Ensure users have proper tier assignments

## Setup Steps

### 1. Add Environment Variable

Add to your `.env` file:

```bash
# AI Assistant (Claude)
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 2. Run Database Migration

```bash
# Apply the ai_usage table migration
alembic upgrade head
```

Or manually:

```sql
-- Run the SQL from alembic/versions/add_ai_usage_table.py
CREATE TABLE ai_usage (
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

CREATE INDEX ix_ai_usage_user_id ON ai_usage(user_id);
CREATE INDEX ix_ai_usage_created_at ON ai_usage(created_at);
```

### 3. Test the API

```bash
# Start the server
uvicorn app.main:app --reload

# Test the endpoint (requires auth token)
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello Claude!"}'
```

### 4. Set User Tiers

Users need to be upgraded to paid tiers to access AI:

```sql
-- Upgrade a user to Student tier (10 msgs/day)
UPDATE users SET tier = 'student' WHERE email = 'user@example.com';

-- Upgrade to Professional (100 msgs/day)
UPDATE users SET tier = 'professional' WHERE email = 'user@example.com';

-- Give unlimited access (Enterprise/Employee)
UPDATE users SET tier = 'enterprise' WHERE email = 'user@example.com';
```

## Pricing Tiers

| Tier | Monthly | Messages/Day | Access |
|------|---------|--------------|--------|
| Anonymous | Free | 0 | ❌ No access |
| Beginner | Free | 0 | ❌ No access |
| **Student** | **$4.99** | **10** | ✅ Limited |
| **Professional** | **$19.99** | **100** | ✅ Full |
| **Government** | Custom | 500 | ✅ Heavy |
| **Enterprise** | Custom | Unlimited | ✅ Unlimited |
| Employee | Free | Unlimited | ✅ Perk |

## Cost Analysis

### Claude 3.5 Haiku Costs (What we pay)
- Input: $0.80 per million tokens
- Output: $4.00 per million tokens

### Our Markup (What users pay)
- Input: $2.40 per MTok (300% markup)
- Output: $10.00 per MTok (250% markup)

### Profit Per Message
Average message (100 input / 300 output tokens):
- Our cost: **$0.00128**
- User cost: **$0.00324**
- **Profit: $0.00196 (152% margin)** 💰

### Monthly Projections

**Student Tier (300 messages/month):**
- Revenue: $4.99
- Costs: ~$0.38
- **Profit: $4.61 (92% margin)**

**Professional Tier (3,000 messages/month):**
- Revenue: $19.99
- Costs: ~$3.84
- **Profit: $16.15 (81% margin)**

## Frontend Integration

### Real AI (Paywalled)
The real AI assistant is in `claude-assistant-real.js`:
- Calls `/api/v1/ai/chat` endpoint
- Shows paywall for free users
- Displays usage limits
- Tracks costs per message

### Demo AI (Free)
The fake demo assistant is in `claude-assistant.js`:
- Keyword-based responses
- No API costs
- Good for testing/demos

### Switching Between Them

Edit `app.html`:

```html
<!-- Real AI (requires ANTHROPIC_API_KEY) -->
<script src="static/js/claude-assistant-real.js"></script>

<!-- OR Fake demo AI (no costs) -->
<script src="static/js/claude-assistant.js"></script>
```

## Monitoring & Analytics

### Check Usage

```bash
# Get AI usage for a user
curl http://localhost:8000/api/v1/ai/usage \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "tier": "professional",
  "daily_limit": 100,
  "daily_used": 42,
  "daily_remaining": 58,
  "lifetime_messages": 850,
  "lifetime_cost": 2.75,
  "has_access": true
}
```

### Query Database

```sql
-- Total profit from AI assistant
SELECT
    COUNT(*) as total_messages,
    SUM(api_cost) as total_api_cost,
    SUM(user_cost) as total_revenue,
    SUM(profit) as total_profit,
    AVG(profit) as avg_profit_per_message
FROM ai_usage;

-- Top AI users
SELECT
    u.email,
    u.tier,
    COUNT(*) as messages,
    SUM(ai.profit) as profit_generated
FROM ai_usage ai
JOIN users u ON ai.user_id = u.id
GROUP BY u.id, u.email, u.tier
ORDER BY profit_generated DESC
LIMIT 10;

-- Daily usage trends
SELECT
    DATE(created_at) as date,
    COUNT(*) as messages,
    SUM(profit) as daily_profit
FROM ai_usage
GROUP BY DATE(created_at)
ORDER BY date DESC
LIMIT 30;
```

## Upsell Strategy

### When Free User Tries AI
```
🔒 Unlock AI Assistant

Chat with Claude to get help with PostgreSQL,
generate SQL, and more!

Student: $4.99/mo · 10 msgs/day
Professional: $19.99/mo · 100 msgs/day
Enterprise: Custom · Unlimited

[View Pricing]
```

### When Daily Limit Reached
```
⚠️ Daily Limit Reached

You've used all 10 messages today.
Resets at midnight UTC.

Upgrade to Professional for 100/day!

[Upgrade Plan]
```

### Show Value
```
💡 Tip: You've used $2.75 worth of AI this month.
Professional plan is only $19.99 with 10x more messages!
```

## Security Notes

1. **Never expose API key to frontend**
   - All Claude calls go through backend
   - Frontend only calls `/api/v1/ai/chat`

2. **Rate limiting**
   - Daily message limits enforced
   - Prevents abuse and runaway costs

3. **Cost tracking**
   - Every message logged with exact costs
   - Monitor for unusual usage patterns

4. **User authentication**
   - All endpoints require valid JWT token
   - Tier checking on every request

## Troubleshooting

### "AI Assistant is not configured"
- Check `ANTHROPIC_API_KEY` in `.env`
- Restart the server
- Verify API key is valid at console.anthropic.com

### "Payment required" error
- User tier is Anonymous or Beginner
- Upgrade user: `UPDATE users SET tier='student' WHERE ...`

### "Daily limit reached"
- User has exhausted daily messages
- Resets at midnight UTC
- Upgrade user tier for more messages

### High API costs
- Check `ai_usage` table for unusual patterns
- Look for users making very long prompts
- Consider adding max token limits

## Making Money! 💰

To maximize profit:

1. **Promote the feature** - Show it prominently in UI
2. **Demonstrate value** - Show SQL examples, quick wins
3. **Soft upsells** - Remind users when low on messages
4. **Track conversion** - Monitor free → paid upgrades
5. **A/B test pricing** - Try different tier prices

Remember: This feature has **80%+ profit margins**. Even if only 10% of users upgrade, it's highly profitable!

## Questions?

See `PRICING_MODEL.md` for detailed revenue projections.
