# MockFactory AI Assistant Pricing Model

## Overview
The AI Assistant feature is **paywalled** and generates profit by adding markup to Claude API costs.

## Tier Access & Limits

| Tier | Monthly Cost | AI Messages/Day | Monthly Messages | Value |
|------|-------------|-----------------|------------------|-------|
| **Anonymous** | $0 | 0 | 0 | ❌ No access |
| **Beginner** | $0 | 0 | 0 | ❌ No access |
| **Student** | $4.99 | 10 | ~300 | ✅ Great for learning |
| **Professional** | $19.99 | 100 | ~3,000 | ✅ Daily usage |
| **Government** | Custom | 500 | ~15,000 | ✅ Heavy usage |
| **Enterprise** | Custom | Unlimited | Unlimited | ✅✅ Power users |
| **Employee** | Free | Unlimited | Unlimited | 🎁 Perk |

## Cost Structure (Claude 3.5 Haiku)

### What We Pay (Anthropic Direct)
- Input: **$0.80** per million tokens
- Output: **$4.00** per million tokens

### What Users Pay (Our Pricing)
- Input: **$2.40** per million tokens (300% markup)
- Output: **$10.00** per million tokens (250% markup)

### Profit Margins
- Input: **$1.60** profit per MTok (200% margin)
- Output: **$6.00** profit per MTok (150% margin)

## Example Calculations

### Average Message (100 input / 300 output tokens)
```
Our Cost:
- Input: 100 × $0.80 / 1M = $0.00008
- Output: 300 × $4.00 / 1M = $0.0012
- Total: $0.00128

User Cost:
- Input: 100 × $2.40 / 1M = $0.00024
- Output: 300 × $10.00 / 1M = $0.0030
- Total: $0.00324

Profit Per Message: $0.00196 (152% margin)
```

### Student Tier (10 messages/day = 300/month)
```
User Pays: $4.99/month
Our Costs: ~$0.384/month (300 × $0.00128)
Gross Profit: $4.61/month
Margin: 92.3% 💰
```

### Professional Tier (100 messages/day = 3,000/month)
```
User Pays: $19.99/month
Our Costs: ~$3.84/month (3,000 × $0.00128)
Gross Profit: $16.15/month
Margin: 80.8% 💰💰
```

### Government Tier (500 messages/day = 15,000/month)
```
User Pays: $49.99/month (suggested)
Our Costs: ~$19.20/month (15,000 × $0.00128)
Gross Profit: $30.79/month
Margin: 61.6% 💰💰💰
```

## Revenue Projections

### Conservative (100 paid users)
- 50 Students: 50 × $4.99 = **$249.50/mo**
- 40 Professional: 40 × $19.99 = **$799.60/mo**
- 10 Government: 10 × $49.99 = **$499.90/mo**

**Total Revenue: $1,549/month**
**Estimated Costs: ~$200/month**
**Net Profit: ~$1,349/month (87% margin)**

### Moderate (500 paid users)
- 250 Students: $1,247.50/mo
- 200 Professional: $3,998/mo
- 50 Government: $2,499.50/mo

**Total Revenue: $7,745/month**
**Estimated Costs: ~$1,000/month**
**Net Profit: ~$6,745/month (87% margin)**

### Aggressive (2,000 paid users)
- 1,000 Students: $4,990/mo
- 800 Professional: $15,992/mo
- 200 Government: $9,998/mo

**Total Revenue: $30,980/month**
**Estimated Costs: ~$4,000/month**
**Net Profit: ~$26,980/month (87% margin)**

## Why This Works

1. **High Perceived Value**: AI assistant is "magical" and users expect premium pricing
2. **Low Actual Cost**: Haiku is dirt cheap but still high-quality
3. **Usage Limits**: Daily caps prevent abuse and keep costs predictable
4. **Sticky Feature**: Once users rely on AI, they won't downgrade
5. **Margin Protection**: Even heavy users stay profitable

## Upsell Strategy

### Free → Student ($4.99)
- "Get 10 AI-powered queries per day"
- "Let Claude help you write SQL"
- "Only $0.16/day"

### Student → Professional ($19.99)
- "Unlock 100 messages/day"
- "Never hit the limit again"
- "Includes priority support"

### Professional → Government/Enterprise
- "Unlimited AI access"
- "Custom data templates"
- "Dedicated support"

## Implementation Notes

1. **Track Everything**: Log every message, token count, and cost
2. **Show Value**: Display "You've used $X.XX worth of AI this month"
3. **Soft Limits**: Warn at 80% of daily limit
4. **Upsell Points**: Show upgrade CTA when limit reached
5. **Analytics**: Track which tiers convert best

## Competitive Advantage

Unlike ChatGPT Plus ($20/mo for general chat):
- Our AI is **context-aware** (knows your environments)
- Can **take actions** (create databases, generate SQL)
- **Specialized** for PostgreSQL/database work
- Integrated into your workflow

This justifies premium pricing even though our costs are lower! 🚀
