# MockFactory.io - Pricing Tiers

**6-Tier Pricing Model: $0 - $500/month**

Pricing based on three factors:
1. **Services**: Number of PostgreSQL instances & cloud services
2. **Data Volume**: How much mock data you generate/seed
3. **Processing**: Hours of active usage per month

---

## Pricing Tiers

### Tier 1: FREE - **$0/month**

**For:** Hobbyists, students, quick tests

**Includes:**
- 10 hours/month of runtime
- 1 PostgreSQL instance at a time
- Up to 1,000 mock data records
- Basic templates (Medical, IT)
- Auto-shutdown after 2 hours
- ❌ No custom hostnames
- ❌ No DNS management

**Best for:** Learning, tutorials, quick prototypes

---

### Tier 2: STARTER - **$20/month**

**For:** Solo developers, side projects

**Includes:**
- 40 hours/month of runtime
- Up to 2 services running simultaneously (PostgreSQL + Redis)
- Up to 10,000 mock data records/month
- All data templates
- Auto-shutdown after 4 hours
- Email support
- ✅ 1 custom hostname per environment
- ✅ 10 DNS records per environment

**Best for:** Personal projects, testing local apps

**Monthly limit:** ~$0.50/hr × 40 hrs = $20

---

### Tier 3: DEVELOPER - **$50/month**

**For:** Professional developers, small teams

**Includes:**
- 100 hours/month of runtime
- Up to 4 services simultaneously (PostgreSQL + Supabase + Redis + S3)
- Up to 50,000 mock data records/month
- All PostgreSQL variants (pgvector, PostGIS)
- All data templates + custom seeding
- Auto-shutdown configurable (2-8 hours)
- Priority email support
- ✅ 2 custom hostnames per environment
- ✅ 50 DNS records per environment
- ✅ UDP DNS server access

**Best for:** Active development, CI/CD integration

**Monthly limit:** ~$0.50/hr × 100 hrs = $50

---

### Tier 4: TEAM - **$150/month**

**For:** Small teams (2-5 developers)

**Includes:**
- 300 hours/month of runtime (shared across team)
- Up to 6 services simultaneously
- Up to 200,000 mock data records/month
- Multiple environments per user
- Team collaboration features
- Database branching (Neon-style)
- Auto-shutdown configurable (1-24 hours)
- Slack support
- ✅ 5 custom hostnames per environment
- ✅ 200 DNS records per environment
- ✅ UDP DNS server access
- ✅ Bulk DNS record operations

**Best for:** Team development, staging environments

**Monthly limit:** ~$0.50/hr × 300 hrs = $150

---

### Tier 5: BUSINESS - **$300/month**

**For:** Growing companies, heavy usage

**Includes:**
- 600 hours/month of runtime
- Unlimited services simultaneously
- Up to 1,000,000 mock data records/month
- Persistent environments (don't auto-destroy)
- Custom data templates
- API rate limit: 10,000 req/hr
- Snapshots & backups
- Auto-shutdown configurable (unlimited)
- Phone & Slack support
- ✅ 10 custom hostnames per environment
- ✅ 1,000 DNS records per environment
- ✅ UDP DNS server access
- ✅ Bulk DNS record operations
- ✅ DNS zone file import

**Best for:** Production-like testing, load testing

**Monthly limit:** ~$0.50/hr × 600 hrs = $300

---

### Tier 6: ENTERPRISE - **$500+/month**

**For:** Large organizations, mission-critical testing

**Includes:**
- Unlimited hours
- Dedicated infrastructure
- Unlimited services & data
- Custom integrations
- SLA guarantees (99.9% uptime)
- Dedicated support engineer
- On-premise deployment option
- Custom contracts
- ✅ Unlimited custom hostnames
- ✅ Unlimited DNS records
- ✅ Private DNS server (dedicated instance)
- ✅ DNS zone file import/export
- ✅ Custom DNS record types

**Best for:** Fortune 500, regulated industries

**Custom pricing:** Based on usage

---

## Pricing Breakdown by Factor

### 1. Services (Hourly Rate)

| Service Type | Cost/Hour |
|--------------|-----------|
| PostgreSQL Standard | $0.10 |
| PostgreSQL + Supabase | $0.15 |
| PostgreSQL + pgvector | $0.12 |
| PostgreSQL + PostGIS | $0.12 |
| Redis | $0.10 |
| AWS S3 | $0.05 |
| AWS SQS/SNS | $0.03 |

**Example:**
- PostgreSQL + Redis + S3 = $0.25/hour
- Running 100 hours/month = $25
- **Fits in Developer tier ($50)**

### 2. Data Volume (One-time Charges)

| Data Records | Cost |
|--------------|------|
| 0 - 1,000 | Free |
| 1,001 - 10,000 | Free (included in tier) |
| 10,001 - 50,000 | Free (included in Developer+) |
| 50,001 - 200,000 | Free (included in Team+) |
| 200,001 - 1M | Free (included in Business+) |
| 1M+ | $0.001/record (Enterprise) |

**Example:**
- Generate 100,000 medical records
- Seed into PostgreSQL
- **Requires Team tier or higher**

### 3. Processing (Included in Runtime)

| Metric | Free | Starter | Developer | Team | Business | Enterprise |
|--------|------|---------|-----------|------|----------|-----------|
| **Runtime Hours** | 10 | 40 | 100 | 300 | 600 | Unlimited |
| **API Requests** | 1,000/hr | 2,000/hr | 5,000/hr | 7,500/hr | 10,000/hr | Unlimited |
| **Data Throughput** | 1 GB/mo | 10 GB/mo | 50 GB/mo | 200 GB/mo | 1 TB/mo | Unlimited |
| **Concurrent Envs** | 1 | 1 | 2 | 5 | 10 | Unlimited |

---

## Usage Examples

### Example 1: Solo Developer

**Use Case:** Testing a SaaS app with PostgreSQL + Redis

**Monthly Usage:**
- 50 hours of runtime
- PostgreSQL ($0.10/hr) + Redis ($0.10/hr) = $0.20/hr
- 50 hrs × $0.20 = $10
- 15,000 mock records generated

**Recommended Tier:** **Starter ($20/month)** ✅

**Why:** Falls well within 40 hr limit, under data cap

---

### Example 2: Small Team

**Use Case:** Team of 3 devs, each testing separately

**Monthly Usage:**
- 180 hours total (60 hrs/dev)
- PostgreSQL + Supabase + Redis + S3 = $0.30/hr
- 180 hrs × $0.30 = $54
- 75,000 mock records

**Recommended Tier:** **Developer ($50/month)** ⚠️ or **Team ($150/month)** ✅

**Why:** Slightly over Developer limit, but Team gives breathing room

---

### Example 3: CI/CD Heavy Usage

**Use Case:** Running tests in CI pipeline, 20 builds/day

**Monthly Usage:**
- Each build runs 30 min = 0.5 hrs
- 20 builds × 30 days = 600 builds/month
- 600 × 0.5 = 300 hours
- Services: PostgreSQL + pgvector = $0.12/hr
- 300 × $0.12 = $36
- 500,000 mock records for realistic tests

**Recommended Tier:** **Business ($300/month)** ✅

**Why:** High data volume, need persistent envs for fast CI

---

### Example 4: Load Testing

**Use Case:** Load testing PostgreSQL with millions of records

**Monthly Usage:**
- 100 hours of runtime
- PostgreSQL + PostGIS + Redis = $0.22/hr
- 100 × $0.22 = $22
- 5,000,000 mock records
- Need snapshots to replay tests

**Recommended Tier:** **Enterprise ($500+/month)** ✅

**Why:** Massive data volume exceeds Business tier

---

## Overage Pricing

If you exceed your tier limits:

| Tier | Runtime Overage | Data Overage |
|------|----------------|--------------|
| FREE | $0.60/hr | Not allowed |
| Starter | $0.60/hr | $0.002/record |
| Developer | $0.55/hr | $0.0015/record |
| Team | $0.50/hr | $0.001/record |
| Business | $0.45/hr | $0.0005/record |
| Enterprise | Custom | Custom |

**Auto-upgrade option:** Automatically move to next tier if overages > tier cost

---

## Annual Discounts

Pay annually, get 2 months free:

| Tier | Monthly | Annual | Savings |
|------|---------|--------|---------|
| Starter | $20 | $200 (10 mo) | $40 |
| Developer | $50 | $500 (10 mo) | $100 |
| Team | $150 | $1,500 (10 mo) | $300 |
| Business | $300 | $3,000 (10 mo) | $600 |

---

## Add-Ons (Optional)

**For any tier:**

- **Extra Runtime**: $0.50/hr (bulk: $40 for 100 hrs)
- **Extra Data**: $0.001/record (bulk: $50 for 100K records)
- **Custom Templates**: $200 one-time (we build your data schema)
- **Dedicated Support**: $100/month (phone + Slack)
- **SLA 99.9%**: $200/month
- **Priority Queue**: $50/month (faster provisioning)

---

## Comparison to Competitors

| Platform | Lowest Tier | Mid Tier | Enterprise |
|----------|-------------|----------|-----------|
| **MockFactory** | $0 (10 hrs) | $50 (100 hrs) | $500+ |
| **LocalStack** | $0 (limited) | $50/mo (1 user) | $500+/mo |
| **AWS RDS** | ~$15/mo (always on) | ~$100/mo | $1,000+/mo |
| **Supabase** | $0 (paused) | $25/mo | $599/mo |

**Our advantage:** Pay only for what you use, auto-shutdown prevents bills

---

## Recommendations

**Choose FREE if:** You're learning or need quick one-off tests

**Choose STARTER if:** Solo dev, testing personal projects

**Choose DEVELOPER if:** Professional dev, active daily testing

**Choose TEAM if:** 2-5 devs, need collaboration

**Choose BUSINESS if:** Heavy CI/CD usage, load testing

**Choose ENTERPRISE if:** Large org, compliance requirements

---

*Pricing effective February 2026*
