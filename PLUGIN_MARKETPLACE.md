# MockFactory Plugin Marketplace

**"Build it once, earn forever"** - Developer ecosystem for cloud service mocking with profit sharing.

## Overview

The MockFactory Plugin Marketplace enables developers to:
1. **Write plugins** that mock third-party services (Stripe, Twilio, Datadog, etc.)
2. **Publish to marketplace** with pricing/revenue share
3. **Earn passive income** from every API call (paid out 2x/month)
4. **Scale MockFactory** beyond what core team can build

## Business Model

### Revenue Split

**Default Split**: 70% Developer / 30% MockFactory

- Developer gets 70% of revenue from their plugin's API calls
- MockFactory gets 30% for platform, hosting, metering, payments
- Verified/Featured plugins can negotiate higher splits (75/25 or 80/20)

### Pricing Tiers

**Per API Call Pricing**:
- **Free Tier**: First 1,000 calls/month free (no revenue, but drives adoption)
- **Standard**: $0.001 per call ($1 per 1,000 calls)
- **Premium**: $0.005 per call (complex mocks like payment processing)
- **Enterprise**: Custom pricing (high-volume, SLA guarantees)

**Plugin Developer Sets**:
- Pricing tier (standard/premium/enterprise)
- Free tier limit (0-10,000 calls)
- Revenue share preference (if negotiated)

### Payouts

**Schedule**: 2x per month (1st and 15th)

**Minimum Payout**: $50
- Below $50 rolls over to next payout
- No maximum payout limit

**Payment Methods**:
- Stripe Connect (fastest, default)
- PayPal
- Wire transfer (for $5,000+)
- Cryptocurrency (USDC on Ethereum/Polygon)

**Tax Handling**:
- Developers submit W-9 (US) or W-8BEN (international)
- 1099 forms issued for US developers
- Developers responsible for their own taxes

## Plugin Architecture

### Plugin Structure

```
mockfactory-plugin-stripe/
├── manifest.json              # Plugin metadata
├── plugin.go (or .py, .js)   # Implementation
├── schema/                    # API request/response schemas
│   ├── charges.json
│   ├── customers.json
│   └── subscriptions.json
├── tests/                     # Required tests
│   └── plugin_test.go
├── README.md                  # Plugin documentation
└── LICENSE                    # MIT, Apache, etc.
```

### Manifest File (`manifest.json`)

```json
{
  "name": "stripe",
  "display_name": "Stripe Payment Processing",
  "version": "1.2.0",
  "author": {
    "name": "John Doe",
    "email": "john@example.com",
    "github": "johndoe"
  },
  "description": "Complete Stripe API mock with charges, customers, subscriptions, webhooks",
  "category": "payments",
  "tags": ["payments", "stripe", "billing", "subscriptions"],

  "pricing": {
    "tier": "premium",
    "per_call_price": 0.005,
    "free_tier_calls": 1000,
    "revenue_share": 0.70
  },

  "api": {
    "base_path": "/plugins/stripe/v1",
    "endpoints": [
      {"method": "POST", "path": "/charges", "description": "Create a charge"},
      {"method": "GET", "path": "/charges/:id", "description": "Retrieve charge"},
      {"method": "POST", "path": "/customers", "description": "Create customer"},
      {"method": "POST", "path": "/subscriptions", "description": "Create subscription"}
    ]
  },

  "runtime": {
    "language": "go",
    "version": "1.21",
    "memory_limit_mb": 128,
    "timeout_seconds": 10
  },

  "dependencies": {
    "external_apis": [],
    "mockfactory_apis": ["storage", "webhooks"],
    "packages": ["github.com/google/uuid"]
  },

  "compatibility": {
    "mockfactory_version": ">=1.0.0",
    "regions": ["us-east-1", "us-west-2", "eu-west-1"]
  },

  "verification": {
    "verified": true,
    "verified_at": "2026-01-15T10:30:00Z",
    "verified_by": "MockFactory Team"
  },

  "status": "active",
  "published_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-02-10T15:45:00Z"
}
```

### Plugin Interface (Go Example)

```go
package main

import (
    "github.com/mockfactory/plugin-sdk/go"
)

type StripePlugin struct {
    sdk *mockfactory.PluginSDK
}

func New(sdk *mockfactory.PluginSDK) mockfactory.Plugin {
    return &StripePlugin{sdk: sdk}
}

// Initialize is called once when plugin loads
func (p *StripePlugin) Initialize() error {
    // Setup state storage, load schemas, etc.
    return p.sdk.Storage.Initialize("stripe")
}

// HandleRequest processes API calls
func (p *StripePlugin) HandleRequest(req *mockfactory.Request) (*mockfactory.Response, error) {
    switch req.Path {
    case "/charges":
        return p.handleCharges(req)
    case "/customers":
        return p.handleCustomers(req)
    case "/subscriptions":
        return p.handleSubscriptions(req)
    default:
        return nil, mockfactory.ErrNotFound
    }
}

func (p *StripePlugin) handleCharges(req *mockfactory.Request) (*mockfactory.Response, error) {
    switch req.Method {
    case "POST":
        return p.createCharge(req)
    case "GET":
        return p.getCharge(req)
    default:
        return nil, mockfactory.ErrMethodNotAllowed
    }
}

func (p *StripePlugin) createCharge(req *mockfactory.Request) (*mockfactory.Response, error) {
    var input struct {
        Amount      int64  `json:"amount"`
        Currency    string `json:"currency"`
        Customer    string `json:"customer"`
        Description string `json:"description"`
    }

    if err := req.ParseJSON(&input); err != nil {
        return nil, err
    }

    // Create charge ID
    chargeID := "ch_" + p.sdk.GenerateID()

    // Store in plugin storage
    charge := map[string]interface{}{
        "id":          chargeID,
        "amount":      input.Amount,
        "currency":    input.Currency,
        "customer":    input.Customer,
        "description": input.Description,
        "status":      "succeeded",
        "created":     p.sdk.Now().Unix(),
    }

    if err := p.sdk.Storage.Put("charges", chargeID, charge); err != nil {
        return nil, err
    }

    // Trigger webhook (if configured)
    p.sdk.Webhooks.Send("charge.succeeded", charge)

    return &mockfactory.Response{
        StatusCode: 200,
        Body:       charge,
    }, nil
}

// Cleanup is called when plugin unloads
func (p *StripePlugin) Cleanup() error {
    return nil
}

// Health check
func (p *StripePlugin) Health() error {
    return nil
}

func main() {
    mockfactory.RunPlugin(New)
}
```

### Plugin SDK Features

The SDK provides plugins with:

1. **Storage**: Key-value store for plugin state
   ```go
   sdk.Storage.Put(collection, key, value)
   sdk.Storage.Get(collection, key)
   sdk.Storage.Query(collection, filter)
   ```

2. **Webhooks**: Send webhook events to customers
   ```go
   sdk.Webhooks.Send(eventType, payload)
   ```

3. **Utilities**:
   ```go
   sdk.GenerateID()           // UUID generation
   sdk.Now()                  // Current timestamp
   sdk.RandomString(n)        // Random string
   sdk.ValidateJSON(schema)   // JSON schema validation
   ```

4. **Metrics**: Usage tracking (automatic)
   ```go
   sdk.Metrics.Counter("charges_created")
   sdk.Metrics.Histogram("charge_amount", amount)
   ```

5. **Logging**:
   ```go
   sdk.Log.Info("Charge created", "id", chargeID)
   sdk.Log.Error("Failed to create charge", "error", err)
   ```

## Marketplace Platform

### Plugin Discovery

**Marketplace UI** at `https://mockfactory.io/marketplace`:

```
┌─────────────────────────────────────────────────────────────┐
│ MockFactory Plugin Marketplace                               │
│                                                              │
│ [Search plugins...]                 [Categories ▼] [Sort ▼] │
│                                                              │
│ ┌─────────────────────┐  ┌─────────────────────┐           │
│ │ 🔵 Stripe           │  │ 📞 Twilio           │           │
│ │ Payment processing  │  │ SMS & Voice APIs    │           │
│ │ ★★★★★ (1.2k)       │  │ ★★★★☆ (847)        │           │
│ │ $0.005/call         │  │ $0.003/call         │           │
│ │ [Install]           │  │ [Install]           │           │
│ └─────────────────────┘  └─────────────────────┘           │
│                                                              │
│ ┌─────────────────────┐  ┌─────────────────────┐           │
│ │ 📊 Datadog          │  │ 📧 SendGrid         │           │
│ │ Metrics & Monitoring│  │ Email delivery      │           │
│ │ ★★★★☆ (623)        │  │ ★★★★★ (1.5k)       │           │
│ │ $0.001/call         │  │ $0.002/call         │           │
│ │ [Install]           │  │ [Install]           │           │
│ └─────────────────────┘  └─────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

**Categories**:
- Payments (Stripe, PayPal, Square)
- Communication (Twilio, SendGrid, Mailgun)
- Monitoring (Datadog, New Relic, Sentry)
- Analytics (Segment, Mixpanel, Amplitude)
- Storage (AWS S3, GCS, Azure Blob)
- Databases (MongoDB, Redis, Elasticsearch)
- Authentication (Auth0, Okta, Firebase Auth)
- DevOps (GitHub, GitLab, CircleCI)

### Plugin Installation

**For End Users**:

```bash
# Via CLI
mocklib plugin install stripe

# Via API
POST /api/v1/plugins/install
{
  "plugin": "stripe",
  "version": "1.2.0"
}
```

**After Installation**:
- Plugin is enabled in user's account
- API calls to `/plugins/stripe/v1/*` are routed to plugin
- Usage metering starts
- Billing based on pricing tier

### Plugin Publishing

**Publishing Workflow**:

1. **Develop Plugin**
   ```bash
   mocklib plugin init --name stripe --language go
   # Edit plugin.go, manifest.json
   mocklib plugin test
   ```

2. **Submit for Review**
   ```bash
   mocklib plugin publish
   ```

   - Automated checks (tests, security scan, manifest validation)
   - Manual review by MockFactory team (1-3 business days)
   - Verification badge for high-quality plugins

3. **Plugin Goes Live**
   - Listed in marketplace
   - Users can install
   - Developer earns revenue

4. **Updates**
   ```bash
   mocklib plugin publish --version 1.3.0
   ```
   - Semantic versioning required
   - Breaking changes require major version bump
   - Auto-migration support

### Quality & Security

**Automated Checks**:
- ✅ All tests pass
- ✅ No security vulnerabilities (Snyk scan)
- ✅ Manifest validation
- ✅ Resource limits (memory, CPU, timeout)
- ✅ No external network calls (except allowed APIs)
- ✅ Code review (GPT-4 + manual for verified)

**Plugin Sandboxing**:
- Runs in isolated container
- Resource limits enforced
- No filesystem access (except SDK storage)
- No network access (except SDK webhooks)
- Crashes don't affect platform

**Monitoring**:
- Error rate tracking
- Latency monitoring
- Auto-disable if error rate >5%
- Developer notifications

## Revenue Sharing System

### Metering

**Every API call is tracked**:

```sql
CREATE TABLE plugin_api_calls (
    id BIGSERIAL PRIMARY KEY,
    plugin_name VARCHAR(255),
    plugin_version VARCHAR(50),
    user_id VARCHAR(255),
    endpoint VARCHAR(500),
    method VARCHAR(10),
    status_code INT,
    latency_ms INT,
    timestamp TIMESTAMPTZ,
    billable BOOLEAN,
    amount_cents INT
);

CREATE INDEX idx_plugin_calls_billing
ON plugin_api_calls(plugin_name, timestamp)
WHERE billable = true;
```

**Real-time Metering**:
- Every API call logs to database
- Aggregated every hour for real-time stats
- Final billing calculated at payout time

### Revenue Calculation

**Example**: Stripe plugin developer earnings for Jan 1-15, 2026

```
Total API Calls: 500,000
Free Tier Calls (across all users): 100,000
Billable Calls: 400,000

Price per call: $0.005
Total Revenue: 400,000 × $0.005 = $2,000

Developer Share (70%): $1,400
MockFactory Share (30%): $600

Developer Payout: $1,400
```

**Payout Dashboard** for Developers:

```
┌─────────────────────────────────────────────────────────────┐
│ Revenue Dashboard - Stripe Plugin                            │
│                                                              │
│ Current Period (Feb 1-15, 2026)                             │
│ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐      │
│ │ API Calls     │ │ Revenue       │ │ Payout        │      │
│ │ 1.2M          │ │ $6,000        │ │ $4,200        │      │
│ │ +15% vs last  │ │ +12% vs last  │ │ (70% share)   │      │
│ └───────────────┘ └───────────────┘ └───────────────┘      │
│                                                              │
│ Next Payout: Feb 15, 2026                                   │
│                                                              │
│ [View Detailed Analytics] [Download Invoice]                │
│                                                              │
│ ═══════════════════════════════════════════════════════════ │
│                                                              │
│ Lifetime Stats                                              │
│ Total API Calls: 15.3M                                      │
│ Total Revenue: $76,500                                      │
│ Total Payouts: $53,550                                      │
│ Active Users: 847                                           │
│ Plugin Rating: ★★★★★ (1,247 reviews)                       │
└─────────────────────────────────────────────────────────────┘
```

### Payout Automation

**Payout Process** (automated via Stripe Connect):

```python
# app/billing/plugin_payouts.py

def process_plugin_payouts(period_start, period_end):
    """Run on 1st and 15th of each month"""

    # Get all plugins
    plugins = Plugin.query.filter_by(status='active').all()

    for plugin in plugins:
        # Calculate revenue
        calls = db.session.query(
            func.count(PluginAPICall.id),
            func.sum(PluginAPICall.amount_cents)
        ).filter(
            PluginAPICall.plugin_name == plugin.name,
            PluginAPICall.billable == True,
            PluginAPICall.timestamp.between(period_start, period_end)
        ).first()

        total_calls, total_revenue_cents = calls

        if not total_revenue_cents or total_revenue_cents == 0:
            continue

        # Calculate developer share
        revenue_share = plugin.revenue_share  # 0.70
        payout_cents = int(total_revenue_cents * revenue_share)
        payout_dollars = payout_cents / 100

        # Skip if below minimum
        if payout_dollars < 50:
            logger.info(f"Skipping {plugin.name}: ${payout_dollars} below minimum")
            continue

        # Create payout via Stripe Connect
        try:
            payout = stripe.Transfer.create(
                amount=payout_cents,
                currency="usd",
                destination=plugin.author.stripe_account_id,
                description=f"Plugin revenue: {plugin.name} ({period_start} to {period_end})",
                metadata={
                    "plugin": plugin.name,
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "api_calls": total_calls,
                }
            )

            # Record payout
            PluginPayout.create(
                plugin_id=plugin.id,
                period_start=period_start,
                period_end=period_end,
                api_calls=total_calls,
                revenue_cents=total_revenue_cents,
                payout_cents=payout_cents,
                stripe_transfer_id=payout.id,
                status='completed'
            )

            logger.info(f"Paid ${payout_dollars} to {plugin.author.name} for {plugin.name}")

        except stripe.error.StripeError as e:
            logger.error(f"Payout failed for {plugin.name}: {e}")
            # Alert team, retry later
```

## Plugin Examples

### Example 1: Stripe Plugin (Payments)

**Usage** (after installing plugin):

```python
from mocklib import MockFactory

mf = MockFactory(api_key="mf_...")

# Create Stripe customer
customer = mf.stripe.customers.create(
    email="customer@example.com",
    name="John Doe"
)

# Create charge
charge = mf.stripe.charges.create(
    amount=2000,  # $20.00
    currency="usd",
    customer=customer.id,
    description="Test charge"
)

print(f"Charge ID: {charge.id}")
print(f"Status: {charge.status}")
```

**API Calls**:
- `POST /plugins/stripe/v1/customers` → $0.005
- `POST /plugins/stripe/v1/charges` → $0.005
- Total: $0.01 (developer earns $0.007)

### Example 2: Twilio Plugin (Communications)

```python
# Send SMS
message = mf.twilio.messages.create(
    to="+15551234567",
    from_="+15559876543",
    body="Test message from MockFactory"
)

print(f"Message SID: {message.sid}")
```

**API Call**: `POST /plugins/twilio/v1/messages` → $0.003

### Example 3: Datadog Plugin (Monitoring)

```python
# Send metrics
mf.datadog.metrics.send([
    {
        "metric": "api.requests",
        "points": [(time.time(), 142)],
        "tags": ["env:production"]
    }
])
```

**API Call**: `POST /plugins/datadog/v1/metrics` → $0.001

## Developer Incentives

### Verified Plugin Program

**Benefits**:
- ✅ Verified badge in marketplace
- ✅ Featured placement
- ✅ Higher revenue share (75/25 or 80/20)
- ✅ Priority support
- ✅ Co-marketing opportunities

**Requirements**:
- 100+ active users
- 4.5+ star rating
- <1% error rate
- Regular updates
- Comprehensive documentation
- Example projects

### Growth Incentives

**Milestone Bonuses**:
- 🎁 First 100 users: $500 bonus
- 🎁 First 1,000 users: $2,000 bonus
- 🎁 First 10,000 users: $10,000 bonus
- 🎁 1M API calls/month: $5,000 bonus

**Referral Program**:
- Developer refers another developer
- Both get 5% bonus on first 6 months of revenue

## Technical Implementation

### API Routing

```go
// app/api/plugin_router.go

func (r *Router) RoutePluginRequest(c *gin.Context) {
    // Extract plugin name from path: /plugins/{plugin}/v1/{endpoint}
    pluginName := c.Param("plugin")

    // Load plugin
    plugin, err := r.pluginRegistry.Get(pluginName)
    if err != nil {
        c.JSON(404, gin.H{"error": "Plugin not found"})
        return
    }

    // Check user has plugin installed
    if !r.userHasPlugin(c.GetString("user_id"), pluginName) {
        c.JSON(403, gin.H{"error": "Plugin not installed"})
        return
    }

    // Meter API call (for billing)
    callID := r.metering.Start(pluginName, c.Request.Method, c.Request.URL.Path)
    defer r.metering.End(callID)

    // Forward to plugin
    req := &mockfactory.Request{
        Method:  c.Request.Method,
        Path:    c.Param("endpoint"),
        Headers: c.Request.Header,
        Body:    c.Request.Body,
        UserID:  c.GetString("user_id"),
    }

    resp, err := plugin.HandleRequest(req)
    if err != nil {
        c.JSON(500, gin.H{"error": err.Error()})
        return
    }

    c.JSON(resp.StatusCode, resp.Body)
}
```

### Plugin Registry

```go
// app/plugins/registry.go

type PluginRegistry struct {
    plugins map[string]*LoadedPlugin
    loader  *PluginLoader
}

func (r *PluginRegistry) Load(pluginName string) error {
    // Load manifest
    manifest, err := r.loader.LoadManifest(pluginName)
    if err != nil {
        return err
    }

    // Validate manifest
    if err := r.validateManifest(manifest); err != nil {
        return err
    }

    // Load plugin binary/container
    plugin, err := r.loader.LoadPlugin(manifest)
    if err != nil {
        return err
    }

    // Initialize plugin
    if err := plugin.Initialize(); err != nil {
        return err
    }

    r.plugins[pluginName] = plugin
    return nil
}
```

## Marketing & Launch

### Launch Strategy

**Phase 1: Seed Plugins (Week 1-2)**
- MockFactory team builds 5 reference plugins:
  - Stripe (payments)
  - Twilio (SMS)
  - SendGrid (email)
  - Datadog (monitoring)
  - GitHub (API)
- Each demonstrates best practices
- Generates initial marketplace content

**Phase 2: Private Beta (Week 3-6)**
- Invite 20 selected developers
- Provide $500 development grant each
- Gather feedback, iterate on SDK
- First external plugins published

**Phase 3: Public Launch (Week 7)**
- Blog post: "Introducing MockFactory Plugin Marketplace"
- Launch on Product Hunt, Hacker News
- Email existing users
- Social media campaign

**Phase 4: Growth (Ongoing)**
- Developer meetups/hackathons
- Partnership with API companies (co-marketing)
- Featured plugin of the month
- Developer success stories

### Projected Economics

**Year 1 Projections**:

```
Developers: 200 plugin developers
Plugins: 150 active plugins
Plugin Users: 10,000 developers

API Calls: 500M calls/month
Avg Price: $0.002/call
Revenue: $1M/month

Developer Payouts: $700k/month (70%)
MockFactory Platform: $300k/month (30%)

Annual Run Rate: $12M revenue, $3.6M platform fee
```

**This creates**:
- Passive income for 200 developers ($3,500/month avg)
- Scalable platform without hiring massive team
- Network effects (more plugins = more value = more users)

## Next Steps

1. **Build Plugin SDK** (2-3 weeks)
   - Go, Python, Node.js SDKs
   - Storage, webhooks, utilities
   - Testing framework

2. **Implement Metering & Billing** (2 weeks)
   - API call tracking
   - Revenue calculation
   - Stripe Connect integration
   - Payout automation

3. **Create Marketplace UI** (2 weeks)
   - Plugin catalog
   - Search, categories, ratings
   - Developer dashboard
   - Analytics

4. **Build Reference Plugins** (2-3 weeks)
   - Stripe, Twilio, SendGrid, Datadog, GitHub
   - Documentation for each
   - Example projects

5. **Private Beta** (4 weeks)
   - 20 developers
   - Iterate based on feedback
   - First payouts!

6. **Public Launch** (Week 12)
   - Marketing campaign
   - Press release
   - Community launch

**Timeline**: 12 weeks to public launch

**Investment Required**: ~$50k (grants, legal, infrastructure)

**ROI**: Infinite - scales with zero marginal cost! 🚀
