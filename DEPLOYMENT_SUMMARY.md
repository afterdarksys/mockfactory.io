# 🏭 MockFactory.io - Deployment Summary

## ✅ Completed Setup

### 1. DNS Configuration
**Domain**: mockfactory.io
- ✅ DNS Zone created in OCI
- ✅ A record: `mockfactory.io` → `141.148.79.30` (undateable-lb)
- ✅ CNAME record: `www.mockfactory.io` → `mockfactory.io`
- ✅ Nameservers: ns1-4.p201.dns.oraclecloud.net

**Status**: Live and ready

### 2. Authentik SSO Integration
- ✅ OAuth2/OIDC provider configured
- ✅ Support for user groups (students, employees, afterdark-employees)
- ✅ Automatic tier assignment based on groups
- ✅ Full documentation: `docs/AUTHENTIK_SETUP.md`

**Authentik Group → Tier Mapping**:
- `employees` or `afterdark-employees` → **Employee** (unlimited)
- `students` → **Student** (25 runs/month)
- No group → **Beginner** (10 runs/month)

### 3. Tier Structure

| Tier | Price | Executions/Month | Target Audience |
|------|-------|------------------|-----------------|
| Anonymous | Free | 5 | Unauthenticated users |
| Beginner | Free | 10 | Registered users |
| **Student** | **Free** | **25** | **Students with verified accounts** |
| Professional | $19.99/mo | 100 | Individual developers |
| Government | $49.99/mo | 500 | Government agencies |
| Enterprise | $99.99/mo | Unlimited | Large organizations |
| Custom | Contact Sales | Custom | Special requirements |
| Employee | Free | Unlimited | After Dark Systems staff |

### 4. Stripe Billing Integration
- ✅ Complete subscription management
- ✅ Customer portal for self-service
- ✅ Webhook handlers for all lifecycle events
- ✅ Monthly usage reset on successful payment
- ✅ Automatic tier downgrade on cancellation
- ✅ Setup script: `app/stripe_setup.py`
- ✅ Full documentation: `docs/STRIPE_SETUP.md`

**Payment Features**:
- Stripe Checkout for new subscriptions
- Customer Portal for managing subscriptions
- Automatic billing cycle management
- Failed payment handling with grace period

### 5. Authentication Methods
✅ **Dual Authentication Support**:

1. **Authentik SSO** (Primary)
   - OAuth2/OIDC integration
   - Group-based tier assignment
   - Automatic student verification

2. **Manual Email/Password**
   - Standard signup/signin
   - Email validation
   - Password hashing with bcrypt

### 6. Security Features
- ✅ Docker container sandboxing
- ✅ No root access for code execution
- ✅ Network isolation (no internet access)
- ✅ Read-only filesystem
- ✅ Seccomp syscall filtering
- ✅ Resource limits (CPU, memory, time)
- ✅ Container escape detection
- ✅ Security violation monitoring

### 7. Multi-Language Support
✅ Supported languages:
- Python 3.11
- PHP 8.2
- Perl 5.38
- JavaScript/Node.js 20
- Go 1.21
- Shell (Alpine)
- HTML

## 📁 Project Structure

```
mockfactory.io/
├── app/
│   ├── api/
│   │   ├── auth.py          # Authentik SSO + Email auth
│   │   ├── execute.py        # Code execution API
│   │   └── payments.py       # Stripe billing
│   ├── core/
│   │   ├── config.py         # Tier limits & settings
│   │   └── database.py       # PostgreSQL connection
│   ├── models/
│   │   ├── user.py           # 8 tier system
│   │   └── execution.py      # Execution tracking
│   ├── security/
│   │   ├── auth.py           # JWT authentication
│   │   └── oauth.py          # Authentik OAuth client
│   ├── services/
│   │   └── usage_tracker.py  # Tier-based limits
│   ├── sandboxes/
│   │   └── docker_sandbox.py # Secure execution
│   ├── main.py               # FastAPI app
│   └── stripe_setup.py       # Stripe product creator
├── docs/
│   ├── AUTHENTIK_SETUP.md    # SSO configuration guide
│   └── STRIPE_SETUP.md       # Billing setup guide
├── frontend/
│   └── index.html            # Web interface
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## 🚀 Next Steps

### 1. Complete Authentik Configuration
Run through `docs/AUTHENTIK_SETUP.md`:
1. Create OAuth2 provider in Authentik
2. Configure redirect URIs
3. Create user groups (students, employees)
4. Copy client ID/secret to `.env`

### 2. Set Up Stripe Billing
Run through `docs/STRIPE_SETUP.md`:
1. Run `python -m app.stripe_setup` to create products
2. Configure webhook endpoint
3. Copy product/price IDs to `.env`
4. Test with Stripe test mode

### 3. Update Environment Variables

Create `.env` file:
```bash
# Database
DATABASE_URL=postgresql://mockfactory:password@postgres:5432/mockfactory
REDIS_URL=redis://redis:6379/0

# Authentik OAuth2
OAUTH_CLIENT_ID=<from-authentik>
OAUTH_CLIENT_SECRET=<from-authentik>
OAUTH_AUTHORIZE_URL=https://authentik.yourcompany.com/application/o/authorize/
OAUTH_TOKEN_URL=https://authentik.yourcompany.com/application/o/token/
OAUTH_USERINFO_URL=https://authentik.yourcompany.com/application/o/userinfo/
OAUTH_LOGOUT_URL=https://authentik.yourcompany.com/application/o/mockfactory/end-session/
OAUTH_PROVIDER_NAME=Authentik

# JWT
SECRET_KEY=<generate-with-openssl-rand-hex-32>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Stripe
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_live_xxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx

STRIPE_PRODUCT_PROFESSIONAL=prod_xxxxxxxxxxxxx
STRIPE_PRICE_PROFESSIONAL=price_xxxxxxxxxxxxx
STRIPE_PRODUCT_GOVERNMENT=prod_xxxxxxxxxxxxx
STRIPE_PRICE_GOVERNMENT=price_xxxxxxxxxxxxx
STRIPE_PRODUCT_ENTERPRISE=prod_xxxxxxxxxxxxx
STRIPE_PRICE_ENTERPRISE=price_xxxxxxxxxxxxx

# Usage Limits
RUNS_ANONYMOUS=5
RUNS_BEGINNER=10
RUNS_STUDENT=25
RUNS_PROFESSIONAL=100
RUNS_GOVERNMENT=500
RUNS_ENTERPRISE=-1
RUNS_EMPLOYEE=-1

AFTERDARK_EMPLOYEE_DOMAIN=@afterdarksystems.com

# Docker Security
DOCKER_SOCKET=/var/run/docker.sock
MAX_EXECUTION_TIME=30
MAX_MEMORY_MB=256
MAX_CPU_QUOTA=50000

# API
API_V1_PREFIX=/api/v1
CORS_ORIGINS=["https://mockfactory.io"]
```

### 4. Deploy to Production

**Option A: Docker Compose** (Quick start)
```bash
cd /Users/ryan/development/mockfactory.io
docker-compose up -d
```

**Option B: OCI Deployment** (Production)
```bash
# Build and push
docker build -t mockfactory:latest .
docker push your-registry/mockfactory:latest

# Deploy to OCI instance (141.148.79.30)
ssh oci-instance
docker run -d \
  --name mockfactory \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --env-file .env \
  --restart unless-stopped \
  your-registry/mockfactory:latest
```

### 5. Configure Load Balancer

Add backend to `undateable-lb` (141.148.79.30):
- Backend: MockFactory instance on port 8000
- Health check: `/health`
- Path routing: `mockfactory.io/*` → MockFactory backend

### 6. SSL/TLS Certificate

Set up SSL:
- Option A: OCI Load Balancer SSL termination
- Option B: Let's Encrypt with certbot
- Option C: Cloudflare proxy with SSL

## 📊 API Endpoints

### Authentication
- `POST /api/v1/auth/signup` - Email/password signup
- `POST /api/v1/auth/signin` - Email/password signin
- `GET /api/v1/auth/sso/login` - Initiate Authentik SSO
- `GET /api/v1/auth/sso/callback` - SSO callback
- `GET /api/v1/auth/me` - Get current user

### Code Execution
- `POST /api/v1/code/execute` - Execute code
- `GET /api/v1/code/usage` - Get usage info
- `GET /api/v1/code/languages` - List supported languages

### Payments
- `POST /api/v1/payments/create-checkout-session` - Start subscription
- `GET /api/v1/payments/customer-portal` - Manage subscription
- `POST /api/v1/payments/webhook` - Stripe webhooks
- `GET /api/v1/payments/pricing` - Get pricing tiers
- `GET /api/v1/payments/my-subscription` - Get subscription status

### System
- `GET /` - API info
- `GET /health` - Health check
- `GET /docs` - Swagger UI

## 🔐 Security Checklist

Before going live:
- [ ] Change all default secrets
- [ ] Enable HTTPS/SSL
- [ ] Configure Stripe live keys
- [ ] Set up webhook signatures
- [ ] Enable rate limiting
- [ ] Configure CORS properly
- [ ] Set up monitoring/logging
- [ ] Test container escape detection
- [ ] Verify resource limits
- [ ] Test all tier upgrades/downgrades

## 📈 Monitoring

Key metrics to track:
- Executions per tier
- Active subscriptions
- Monthly Recurring Revenue (MRR)
- Failed payments
- Container escape attempts
- API response times
- Error rates

## 📝 Documentation

- **README.md**: Overview and quick start
- **docs/AUTHENTIK_SETUP.md**: SSO configuration
- **docs/STRIPE_SETUP.md**: Billing setup
- **examples/examples.md**: Code examples
- **Swagger UI**: https://mockfactory.io/docs

## 🎉 Ready to Launch!

MockFactory.io is fully built with:
✅ Authentik SSO integration
✅ 8-tier subscription system
✅ Stripe billing
✅ Secure code execution
✅ Complete documentation
✅ DNS configured
✅ Production-ready architecture

Next: Complete Authentik + Stripe configuration and deploy!
