## API Separation: Public vs Private

MockFactory has two distinct API surfaces:

### 1. Public API (Customer-Facing)
**Base URL**: `https://api.mockfactory.io/v1`

**Authentication**: Bearer token (API key)
**Rate Limiting**: Yes (tier-based)
**Billing**: Pay-per-use credits

**Endpoints**:
```
POST   /aws/vpc                 # VPC operations
POST   /aws/lambda              # Lambda operations
POST   /aws/dynamodb            # DynamoDB operations
POST   /aws/sqs                 # SQS operations
POST   /storage/bucket          # S3/GCS/Azure storage
GET    /environments            # List environments
POST   /environments            # Create environment
DELETE /environments/:id        # Delete environment
```

**Used By**:
- MockLib SDKs (Python, Node, Go, PHP)
- Terraform provider
- Ansible module
- Direct API calls (curl, etc.)

**Design Principles**:
- AWS-compatible API signatures where possible
- Consistent error responses
- Structured JSON responses
- Versioned API (v1, v2, etc.)

---

### 2. Private API (Internal Only)
**Base URL**: `https://mockfactory.io/api/internal`

**Authentication**: Internal service tokens (not customer API keys)
**Rate Limiting**: No
**Billing**: No charges

**Endpoints**:
```
POST   /internal/admin/users/:id/credits          # Add/remove credits
GET    /internal/metrics/usage                    # System-wide metrics
GET    /internal/health/detailed                  # Detailed health check
POST   /internal/admin/environments/:id/force-delete
GET    /internal/billing/reconcile                # Billing reconciliation
POST   /internal/admin/api-keys/revoke            # Revoke API keys
GET    /internal/audit-log                        # Full audit log
```

**Used By**:
- Admin dashboard (internal)
- Background workers
- Monitoring systems
- Support tools

**Design Principles**:
- NOT exposed to customers
- No SDK wrapping
- Can change without versioning
- Optimized for internal use

---

## Implementation in FastAPI

### Current Structure (app/api/)
```
app/api/
├── auth.py                  # PUBLIC: Authentication
├── payments.py              # PUBLIC: Stripe integration
├── environments.py          # PUBLIC: Environment management
├── cloud_emulation.py       # PUBLIC: S3/GCS/Azure
├── aws_vpc_emulator.py      # PUBLIC: VPC operations
├── aws_lambda_emulator.py   # PUBLIC: Lambda operations
├── aws_dynamodb_emulator.py # PUBLIC: DynamoDB operations
├── aws_sqs_emulator.py      # PUBLIC: SQS operations
└── execute.py               # PUBLIC: Code execution
```

### Proposed Structure
```
app/api/
├── public/                  # Customer-facing APIs
│   ├── __init__.py
│   ├── auth.py
│   ├── environments.py
│   ├── aws/
│   │   ├── vpc.py
│   │   ├── lambda_fn.py
│   │   ├── dynamodb.py
│   │   └── sqs.py
│   ├── storage.py
│   └── billing.py
│
└── internal/                # Internal-only APIs
    ├── __init__.py
    ├── admin.py             # Admin operations
    ├── metrics.py           # System metrics
    ├── health.py            # Detailed health
    └── audit.py             # Audit logging
```

### Routing in main.py
```python
# Public API (customer-facing)
app.include_router(
    public_router,
    prefix="/api/v1",  # or use api.mockfactory.io
    tags=["public"]
)

# Private API (internal only)
app.include_router(
    internal_router,
    prefix="/api/internal",
    tags=["internal"],
    dependencies=[Depends(verify_internal_token)]  # Block customers!
)
```

---

## Subdomain Strategy (Recommended)

### Option A: Separate Subdomains
```
https://api.mockfactory.io/v1/*           # Public API
https://internal.mockfactory.io/api/*     # Private API
https://mockfactory.io/*                  # Marketing site
https://app.mockfactory.io/*              # Dashboard
```

**Benefits**:
- Clear separation
- Can deploy on different infrastructure
- Easy firewall rules (block `internal.` from internet)
- Different rate limits per subdomain

### Option B: Path-based (Current)
```
https://mockfactory.io/api/v1/*           # Public API
https://mockfactory.io/api/internal/*     # Private API
https://mockfactory.io/*                  # Marketing + Dashboard
```

**Benefits**:
- Simpler deployment
- One SSL cert
- Easier for development

**Recommendation**: Use Option A for production, Option B for dev.

---

## Security Considerations

### Public API
- ✅ Rate limiting (per API key)
- ✅ API key authentication
- ✅ Request validation
- ✅ Credit deduction on usage
- ✅ Audit logging
- ❌ No admin operations exposed

### Private API
- ✅ Internal token authentication (not customer API keys!)
- ✅ IP whitelist (only from known internal IPs)
- ✅ No rate limiting (trusted traffic)
- ✅ Extra audit logging
- ❌ NEVER exposed to public internet
- ❌ No CORS (not browser-accessible)

### Token Types
```python
# Customer API key
mf_1234567890abcdef1234567890abcdef

# Internal service token (different format!)
internal_sk_abcdef1234567890abcdef1234567890

# Admin session token
admin_sess_xyz123...
```

---

## Migration Plan

### Phase 1: Add Internal Router (1 day)
```python
# app/api/internal/__init__.py
from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import verify_internal_token

router = APIRouter()

@router.get("/metrics/usage")
async def get_system_metrics(token=Depends(verify_internal_token)):
    # Return system-wide usage metrics
    pass

@router.post("/admin/users/{user_id}/credits")
async def adjust_credits(user_id: str, amount: int, token=Depends(verify_internal_token)):
    # Add/remove credits (admin only)
    pass
```

### Phase 2: Move Public APIs to /api/v1 (2 days)
- Create public/ directory
- Move existing endpoints
- Update imports
- Test SDK compatibility

### Phase 3: Separate Subdomains (1 day)
- Add `api.mockfactory.io` to DNS
- Update nginx config
- Deploy separate containers (optional)

---

## Example: Admin Credit Adjustment

### Public API (BLOCKED)
```bash
# Customers CANNOT do this
curl -X POST https://api.mockfactory.io/v1/admin/credits \
  -H "Authorization: Bearer mf_customer_key" \
  -d '{"user_id": "...", "amount": 1000}'

# Response: 403 Forbidden
```

### Private API (ALLOWED)
```bash
# Internal services CAN do this
curl -X POST https://internal.mockfactory.io/api/admin/credits \
  -H "Authorization: Bearer internal_sk_..." \
  -d '{"user_id": "...", "amount": 1000}'

# Response: 200 OK
```

---

## Monitoring & Alerts

### Public API
- Track: Requests/sec, error rate, latency
- Alert: High error rate, slow responses
- Dashboard: Customer-facing metrics

### Private API
- Track: Background job status, system health
- Alert: Failed reconciliations, billing errors
- Dashboard: Internal ops metrics

---

## Summary

**Public API**: Customers → MockLib SDK → `api.mockfactory.io/v1` → Billing
**Private API**: Admins → Direct calls → `internal.mockfactory.io/api` → No billing

**Next Steps**:
1. Create `app/api/internal/` directory
2. Move admin operations to internal API
3. Add internal token authentication
4. Deploy api.mockfactory.io subdomain
5. Update MockLib SDKs to use `api.mockfactory.io`
