# Stripe Billing Integration Setup

Complete guide to setting up Stripe billing for MockFactory.io.

## Step 1: Create Stripe Products

Run the automated setup script to create all tier products in Stripe:

```bash
cd /Users/ryan/development/mockfactory.io
python -m app.stripe_setup
```

This will create:
- **Professional** tier: $19.99/month (100 executions)
- **Government** tier: $49.99/month (500 executions)
- **Enterprise** tier: $99.99/month (unlimited executions)

The script will output the Product IDs and Price IDs to add to your `.env` file.

## Step 2: Update Environment Variables

Add the Stripe IDs to your `.env`:

```bash
# From stripe_setup.py output
STRIPE_PRODUCT_PROFESSIONAL=prod_xxxxxxxxxxxxx
STRIPE_PRICE_PROFESSIONAL=price_xxxxxxxxxxxxx

STRIPE_PRODUCT_GOVERNMENT=prod_xxxxxxxxxxxxx
STRIPE_PRICE_GOVERNMENT=price_xxxxxxxxxxxxx

STRIPE_PRODUCT_ENTERPRISE=prod_xxxxxxxxxxxxx
STRIPE_PRICE_ENTERPRISE=price_xxxxxxxxxxxxx
```

## Step 3: Configure Stripe Webhooks

### Create Webhook Endpoint

1. Go to [Stripe Dashboard](https://dashboard.stripe.com/webhooks)
2. Click **Add endpoint**
3. Enter endpoint URL:
   ```
   https://mockfactory.io/api/v1/payments/webhook
   ```

4. Select events to listen for:
   ```
   checkout.session.completed
   customer.subscription.created
   customer.subscription.updated
   customer.subscription.deleted
   invoice.payment_succeeded
   invoice.payment_failed
   ```

5. Click **Add endpoint**

### Get Webhook Secret

1. Click on your newly created webhook
2. Click **Reveal** under "Signing secret"
3. Copy the webhook secret (starts with `whsec_`)
4. Add to `.env`:
   ```bash
   STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
   ```

## Step 4: Test Stripe Integration

### Test Mode

1. Use Stripe test keys for development:
   ```bash
   STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxxx
   STRIPE_PUBLISHABLE_KEY=pk_test_xxxxxxxxxxxxx
   ```

2. Test credit cards:
   ```
   Success: 4242 4242 4242 4242
   Decline: 4000 0000 0000 0002
   3D Secure: 4000 0027 6000 3184
   ```

### Test Flow

1. Sign up for a MockFactory account
2. Click "Upgrade to Professional"
3. Complete Stripe checkout with test card
4. Verify webhook received
5. Check user tier updated to "professional"
6. Verify execution limits increased to 100

## Stripe Webhook Events

MockFactory handles these Stripe events:

| Event | Action |
|-------|--------|
| `checkout.session.completed` | Upgrade user to paid tier, create subscription |
| `customer.subscription.updated` | Update subscription status |
| `customer.subscription.deleted` | Downgrade to Beginner tier |
| `invoice.payment_succeeded` | Reset monthly usage counter |
| `invoice.payment_failed` | Mark subscription as past_due |

## Subscription Lifecycle

### New Subscription
1. User clicks "Upgrade" in MockFactory
2. MockFactory creates Stripe checkout session
3. User completes payment
4. Stripe sends `checkout.session.completed`
5. MockFactory upgrades user tier
6. Usage counter resets

### Monthly Billing
1. Stripe charges customer automatically
2. Stripe sends `invoice.payment_succeeded`
3. MockFactory resets monthly usage counter
4. User gets fresh execution quota

### Failed Payment
1. Stripe sends `invoice.payment_failed`
2. MockFactory marks subscription as `past_due`
3. User can still execute code (grace period)
4. After retries fail, Stripe sends `customer.subscription.deleted`
5. MockFactory downgrades user to Beginner tier

### Cancellation
1. User cancels via Stripe Customer Portal
2. Subscription remains active until period end
3. Stripe sends `customer.subscription.deleted` at period end
4. MockFactory downgrades to Beginner tier

## Customer Portal

Users can manage their subscription via Stripe Customer Portal:

**Endpoint**: `GET /api/v1/payments/customer-portal`

This allows users to:
- Update payment method
- View invoices
- Cancel subscription
- Update billing information

Redirect:
```javascript
const response = await fetch('/api/v1/payments/customer-portal', {
    headers: { 'Authorization': `Bearer ${token}` }
});
const data = await response.json();
window.location.href = data.portal_url;
```

## Pricing Tiers

| Tier | Price | Executions | Stripe Product |
|------|-------|------------|----------------|
| Anonymous | Free | 5 | - |
| Beginner | Free | 10 | - |
| Student | Free | 25 | - |
| **Professional** | **$19.99/mo** | **100** | ✓ Required |
| **Government** | **$49.99/mo** | **500** | ✓ Required |
| **Enterprise** | **$99.99/mo** | **Unlimited** | ✓ Required |
| Custom | Contact Sales | Custom | - |
| Employee | Free | Unlimited | - |

## Testing Webhooks Locally

### Using Stripe CLI

1. Install Stripe CLI:
   ```bash
   brew install stripe/stripe-cli/stripe
   ```

2. Login:
   ```bash
   stripe login
   ```

3. Forward webhooks to localhost:
   ```bash
   stripe listen --forward-to localhost:8000/api/v1/payments/webhook
   ```

4. Get webhook signing secret from CLI output
5. Add to `.env`:
   ```bash
   STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
   ```

6. Trigger test events:
   ```bash
   stripe trigger checkout.session.completed
   stripe trigger invoice.payment_succeeded
   ```

## Production Deployment

### Before Going Live

1. ✓ Switch to live Stripe keys
2. ✓ Update webhook endpoint to production URL
3. ✓ Test complete upgrade flow
4. ✓ Verify webhook signatures
5. ✓ Test subscription cancellation
6. ✓ Monitor Stripe dashboard for errors

### Environment Variables (Production)

```bash
# Live Stripe keys
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_live_xxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx

# Product IDs (from stripe_setup.py)
STRIPE_PRODUCT_PROFESSIONAL=prod_xxxxxxxxxxxxx
STRIPE_PRICE_PROFESSIONAL=price_xxxxxxxxxxxxx
STRIPE_PRODUCT_GOVERNMENT=prod_xxxxxxxxxxxxx
STRIPE_PRICE_GOVERNMENT=price_xxxxxxxxxxxxx
STRIPE_PRODUCT_ENTERPRISE=prod_xxxxxxxxxxxxx
STRIPE_PRICE_ENTERPRISE=price_xxxxxxxxxxxxx
```

## Monitoring

### Key Metrics

Monitor in Stripe Dashboard:
- Monthly Recurring Revenue (MRR)
- Customer Lifetime Value (LTV)
- Churn rate
- Failed payments
- Subscription growth

### Alerts

Set up alerts for:
- Failed webhook deliveries
- Failed payments
- Subscription cancellations
- Revenue thresholds

## Troubleshooting

### Webhook Not Received

**Check**:
- Webhook endpoint is accessible (https://mockfactory.io/api/v1/payments/webhook)
- Firewall allows Stripe IPs
- SSL certificate is valid
- Webhook secret is correct

**Test**:
```bash
curl -X POST https://mockfactory.io/api/v1/payments/webhook \
  -H "Content-Type: application/json" \
  -d '{}'
```

### User Tier Not Updating

**Check**:
- Webhook received (check Stripe dashboard)
- Webhook signature valid
- User ID in metadata matches database
- Database connection working

**Debug**:
- Check MockFactory logs
- Verify webhook handler executed
- Check database for user tier

### Payment Declined

**Common Reasons**:
- Insufficient funds
- Card expired
- 3D Secure required
- Card blocked by issuer

**Solution**:
- User updates payment method via Customer Portal
- Stripe retries automatically

## Security

### Best Practices

1. **Verify Webhook Signatures**: Always verify `stripe-signature` header
2. **Use HTTPS**: Never use HTTP in production
3. **Protect Secret Keys**: Never commit to git
4. **Rotate Keys**: Rotate API keys if compromised
5. **Monitor Access**: Review Stripe audit logs regularly

### PCI Compliance

MockFactory uses Stripe Checkout and Customer Portal:
- ✓ No credit card data touches our servers
- ✓ PCI DSS Level 1 compliant (via Stripe)
- ✓ Strong Customer Authentication (SCA) supported
- ✓ 3D Secure 2 ready

## Support

- **Stripe Issues**: https://support.stripe.com
- **MockFactory Billing**: support@afterdarksystems.com
- **Stripe API Docs**: https://stripe.com/docs/api

## Reference

- [Stripe Checkout Documentation](https://stripe.com/docs/payments/checkout)
- [Stripe Webhooks Guide](https://stripe.com/docs/webhooks)
- [Stripe Customer Portal](https://stripe.com/docs/billing/subscriptions/customer-portal)
