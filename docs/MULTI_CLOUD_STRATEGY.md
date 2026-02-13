# Multi-Cloud Emulation Strategy

**One platform to test AWS, Azure, GCP, Digital Ocean, Supabase, Cloudflare, and Neon**

## Vision

Developers write code for **any cloud provider** → MockFactory emulates the API → OCI provides the backend.

**No cloud accounts needed. Pay one hourly rate.**

---

## Service Mapping

### **AWS** (Already Implemented ✅)

| AWS Service | MockFactory Backend | Status |
|------------|---------------------|---------|
| S3 | OCI Object Storage | ✅ Done |
| SQS | ElasticMQ Container | ✅ Done |
| SNS | ElasticMQ Container | ✅ Done |
| ECR | OCI Container Registry | ✅ Done |
| Route53 | In-memory JSON | ✅ Done |
| IAM | In-memory JSON | ✅ Done |
| Lambda | Mock execution | ✅ Done |
| RDS MySQL | MySQL Docker | ✅ Done |
| RDS PostgreSQL | PostgreSQL Docker | ✅ Done |
| ElastiCache | Redis Docker | ✅ Done |
| DynamoDB | LocalStack / In-memory | 🔄 TODO |

---

### **Azure**

| Azure Service | MockFactory Backend | Implementation |
|--------------|---------------------|----------------|
| Blob Storage | OCI Object Storage | ✅ Done |
| SQL Database | MySQL/PostgreSQL Docker | Use existing |
| Cosmos DB | MongoDB Docker | Use existing MongoDB |
| Functions | Mock execution | Similar to Lambda |
| Service Bus | ElasticMQ / RabbitMQ | Use existing |
| Container Registry (ACR) | OCIR | Same as ECR |
| Redis Cache | Redis Docker | ✅ Done |

**API Endpoint Pattern:**
```
https://azure.env-abc123.mockfactory.io/
  → /blob/... (Blob Storage)
  → /sql/... (SQL Database)
  → /cosmos/... (Cosmos DB)
  → /functions/... (Azure Functions)
```

---

### **GCP (Google Cloud Platform)**

| GCP Service | MockFactory Backend | Implementation |
|------------|---------------------|----------------|
| Cloud Storage | OCI Object Storage | ✅ Done |
| Cloud SQL | MySQL/PostgreSQL Docker | Use existing |
| Firestore | MongoDB Docker (document store) | Compatible |
| Cloud Functions | Mock execution | Similar to Lambda |
| Pub/Sub | ElasticMQ / Custom | Message queue |
| Container Registry (GCR) | OCIR | ✅ Done |
| Cloud Run | Dokku on OCI | Deploy containers |
| Memorystore | Redis Docker | ✅ Done |

**API Endpoint Pattern:**
```
https://gcp.env-abc123.mockfactory.io/
  → /storage/v1/... (Cloud Storage)
  → /sql/v1/... (Cloud SQL)
  → /firestore/v1/... (Firestore)
  → /pubsub/v1/... (Pub/Sub)
```

---

### **Digital Ocean**

| DO Service | MockFactory Backend | Implementation |
|-----------|---------------------|----------------|
| Spaces (S3-compatible) | OCI Object Storage | S3 API emulation |
| Managed Databases | MySQL/PostgreSQL/Redis Docker | ✅ Done |
| Managed MongoDB | MongoDB Docker | ✅ Done |
| App Platform | Dokku on OCI | Git push deploy |
| Droplets (VMs) | OCI Compute | Lightsail-like |
| Container Registry | OCIR | Same as ECR |

**API Endpoint Pattern:**
```
https://digitalocean.env-abc123.mockfactory.io/
  → /v2/spaces (Spaces)
  → /v2/databases (Managed DB)
  → /v2/apps (App Platform)
  → /v2/droplets (VMs)
```

**Note:** Digital Ocean uses standard REST APIs, easier to emulate than AWS.

---

### **Supabase**

| Supabase Service | MockFactory Backend | Implementation |
|-----------------|---------------------|----------------|
| PostgreSQL Database | PostgreSQL Docker | ✅ Done |
| Auth | Custom JWT service | Lightweight auth |
| Storage | OCI Object Storage | S3-compatible |
| Realtime | PostgreSQL logical replication | Use existing PG |
| Edge Functions | Mock Deno runtime | Similar to Lambda |

**API Endpoint Pattern:**
```
https://supabase.env-abc123.mockfactory.io/
  → /rest/v1/... (PostgREST API)
  → /auth/v1/... (Auth)
  → /storage/v1/... (Storage)
  → /realtime/v1/... (Realtime)
  → /functions/v1/... (Edge Functions)
```

**Special Features:**
- Supabase = PostgreSQL + PostgREST (auto-generate REST API from schema)
- We can run **PostgREST** Docker container pointing to our PostgreSQL
- Instant REST API for tables!

**Implementation:**
```yaml
services:
  postgres:
    image: postgres:15
  postgrest:
    image: postgrest/postgrest:latest
    environment:
      PGRST_DB_URI: postgres://postgres@db:5432/testdb
      PGRST_DB_SCHEMA: public
```

---

### **Cloudflare**

| Cloudflare Service | MockFactory Backend | Implementation |
|-------------------|---------------------|----------------|
| R2 Storage (S3-compatible) | OCI Object Storage | S3 API emulation |
| Workers | Mock V8 runtime | Similar to Lambda |
| KV (Key-Value) | Redis Docker | Redis with KV API wrapper |
| D1 (SQLite) | SQLite container | Lightweight SQL |
| Durable Objects | In-memory state | Mock storage |
| Queues | ElasticMQ / RabbitMQ | ✅ Done |

**API Endpoint Pattern:**
```
https://cloudflare.env-abc123.mockfactory.io/
  → /client/v4/accounts/.../r2 (R2 Storage)
  → /client/v4/accounts/.../workers (Workers)
  → /client/v4/accounts/.../storage/kv (KV)
  → /client/v4/accounts/.../d1 (D1)
```

**Special Focus:**
- **Cloudflare Workers** are V8 isolates - very fast serverless
- We can mock with Node.js worker threads
- **R2** is S3-compatible → easy!
- **KV** is just Redis with different API

---

### **Neon**

| Neon Service | MockFactory Backend | Implementation |
|-------------|---------------------|----------------|
| Serverless PostgreSQL | PostgreSQL Docker | ✅ Done |
| Database Branching | Multiple PG containers | Git-like branches |
| Connection Pooling | PgBouncer | Add pooler |
| Auto-scaling | Mock (fixed size) | Future: scale containers |

**API Endpoint Pattern:**
```
https://neon.env-abc123.mockfactory.io/
  → /api/v2/projects (Projects)
  → /api/v2/branches (Branches)
  → postgresql://env-abc123.mockfactory.io:5432/main (Connection)
```

**Special Features:**
- **Database Branching** = Copy-on-write PostgreSQL instances
- We can simulate with separate Docker containers per branch
- `main` branch = primary container
- `dev` branch = cloned container

**Implementation:**
```python
# Create branch
POST /api/v2/branches
{
  "project_id": "env-abc123",
  "parent_id": "main",
  "name": "dev"
}

# We provision:
# 1. Dump main DB
# 2. Create new container
# 3. Restore dump to new container
# 4. Return connection string for "dev" branch
```

---

## Unified Pricing

Instead of per-service pricing, we offer **provider packages:**

### Package Pricing:

| Package | Services Included | Price/Hour |
|---------|------------------|------------|
| **AWS Starter** | S3, SQS, Redis, MySQL | $0.33 |
| **AWS Full** | All AWS services | $0.75 |
| **Azure Starter** | Blob, SQL, Redis | $0.33 |
| **GCP Starter** | Storage, SQL, Redis | $0.33 |
| **Supabase Complete** | PostgreSQL + PostgREST + Auth + Storage | $0.40 |
| **Cloudflare Dev** | R2, KV, D1 | $0.25 |
| **Neon Branching** | PostgreSQL with branching | $0.35 |
| **Digital Ocean Stack** | Spaces, DB, App Platform | $0.40 |
| **Multi-Cloud** | Pick any 5 services | $0.50 |
| **Everything** | All providers, all services | $1.00 |

---

## Implementation Priority

### Phase 1 (Current POC):
✅ AWS (S3, SQS, SNS, ECR, Route53, IAM, Lambda)
✅ Containers (Redis, MySQL, PostgreSQL, MongoDB)

### Phase 2 (Next Week):
1. **Supabase** (easiest - just add PostgREST container)
2. **Cloudflare R2** (S3-compatible, super easy)
3. **Digital Ocean Spaces** (also S3-compatible)

### Phase 3 (Week 3):
4. **Azure Service Bus** (use RabbitMQ)
5. **GCP Pub/Sub** (use RabbitMQ)
6. **Cloudflare KV** (Redis wrapper)

### Phase 4 (Week 4):
7. **Neon Branching** (PostgreSQL cloning)
8. **Supabase Realtime** (PostgreSQL logical replication)
9. **Cloudflare Workers** (Node.js worker threads)

---

## Developer Experience

### Single Command to Get Everything:

```bash
curl -X POST https://mockfactory.io/api/v1/environments \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "my-multicloud-test",
    "provider": "multi-cloud",
    "services": [
      "aws_s3",
      "azure_blob",
      "gcp_storage",
      "cloudflare_r2",
      "supabase_postgres",
      "neon_postgres"
    ]
  }'
```

**Returns:**
```json
{
  "id": "env-abc123",
  "endpoints": {
    "aws_s3": "https://s3.env-abc123.mockfactory.io",
    "azure_blob": "https://azure.env-abc123.mockfactory.io/blob",
    "gcp_storage": "https://gcp.env-abc123.mockfactory.io/storage",
    "cloudflare_r2": "https://cloudflare.env-abc123.mockfactory.io/r2",
    "supabase_postgres": "postgresql://localhost:30150/testdb",
    "neon_postgres": "postgresql://localhost:30151/main"
  },
  "hourly_rate": 0.85
}
```

### Provider-Specific Code:

**AWS S3:**
```python
s3 = boto3.client('s3', endpoint_url='https://s3.env-abc123.mockfactory.io')
```

**Cloudflare R2:**
```python
r2 = boto3.client('s3', endpoint_url='https://cloudflare.env-abc123.mockfactory.io/r2')
```

**Supabase:**
```python
from supabase import create_client
supabase = create_client(
    'https://supabase.env-abc123.mockfactory.io',
    'mock-anon-key'
)
supabase.table('users').select('*').execute()
```

**Digital Ocean Spaces:**
```python
spaces = boto3.client('s3', endpoint_url='https://digitalocean.env-abc123.mockfactory.io/v2/spaces')
```

---

## Competitive Advantages

### vs. LocalStack (AWS emulation):
- ✅ We support **all cloud providers**, not just AWS
- ✅ Cheaper pricing ($0.33/hr vs LocalStack ~$50/mo)
- ✅ No local setup - cloud-hosted
- ✅ Team collaboration

### vs. Real Cloud Providers:
- ✅ No account signup needed
- ✅ No credit card for testing
- ✅ Predictable pricing (hourly, not per-request)
- ✅ Auto-shutdown prevents bills
- ✅ Instant teardown - no orphaned resources

### vs. Supabase/Neon (direct):
- ✅ We emulate their APIs for free testing
- ✅ Test Supabase locally before deploying
- ✅ Multi-cloud - test migration paths

---

## Technical Implementation

### Supabase Emulation (PostgREST):

```python
# In environment_provisioner.py

if service_name == "supabase_postgres":
    # 1. Provision PostgreSQL
    pg_info = await self._provision_container(
        environment.id,
        "postgresql",
        service_config
    )

    # 2. Provision PostgREST (auto REST API)
    postgrest_port = await self._get_available_port()
    cmd = [
        "docker", "run", "-d",
        "--name", f"{environment.id}-postgrest",
        "-p", f"{postgrest_port}:3000",
        "-e", f"PGRST_DB_URI={pg_info['endpoint']}",
        "-e", "PGRST_DB_SCHEMA=public",
        "postgrest/postgrest:latest"
    ]
    subprocess.run(cmd)

    endpoints["supabase_rest"] = f"http://localhost:{postgrest_port}"
    endpoints["supabase_postgres"] = pg_info["endpoint"]
```

### Cloudflare R2 (S3-compatible):

```python
# In cloud_emulation.py

@router.put("/cloudflare/r2/{bucket}/{key:path}")
async def cloudflare_r2_put(bucket: str, key: str, request: Request):
    """Cloudflare R2 is S3-compatible - just proxy to our S3 emulation"""
    environment = get_environment_from_subdomain(request, db)

    # Use same OCI bucket as AWS S3
    oci_bucket = environment.oci_resources.get("cloudflare_r2")

    # Upload to OCI (same as S3)
    # ... same implementation as s3_put_object()
```

### Neon Branching:

```python
@router.post("/neon/api/v2/branches")
async def neon_create_branch(request: Request):
    environment = get_environment_from_subdomain(request, db)
    body = await request.json()

    parent_branch = body.get("parent_id", "main")
    new_branch = body.get("name")

    # 1. Dump parent database
    parent_container = f"{environment.id}-postgres-{parent_branch}"
    subprocess.run([
        "docker", "exec", parent_container,
        "pg_dump", "-U", "postgres", "testdb"
    ], stdout=open("/tmp/dump.sql", "w"))

    # 2. Create new container
    new_container = f"{environment.id}-postgres-{new_branch}"
    new_port = await self._get_available_port()
    subprocess.run([
        "docker", "run", "-d",
        "--name", new_container,
        "-p", f"{new_port}:5432",
        "-e", "POSTGRES_PASSWORD=mockfactory",
        "postgres:15"
    ])

    # 3. Restore dump
    subprocess.run([
        "docker", "exec", "-i", new_container,
        "psql", "-U", "postgres", "testdb"
    ], stdin=open("/tmp/dump.sql"))

    return {
        "id": new_branch,
        "name": new_branch,
        "parent_id": parent_branch,
        "connection_string": f"postgresql://postgres:mockfactory@localhost:{new_port}/testdb"
    }
```

---

## Next Steps

1. **Add Supabase** (PostgreSQL + PostgREST + Auth mock)
2. **Add Cloudflare R2** (S3-compatible, trivial)
3. **Add Digital Ocean Spaces** (S3-compatible)
4. **Update pricing** to include provider packages
5. **Create examples** for each provider
6. **Marketing**: "The only platform to test AWS, Azure, GCP, Supabase, Cloudflare, Neon, and Digital Ocean - no accounts needed"

---

## Revenue Projection

**Target Market:**
- 50M developers worldwide
- 10M use cloud services
- 1M actively test/develop with cloud
- **Target: 10,000 paying users**

**Pricing:**
- Average: $0.50/hour
- Usage: 40 hours/month testing
- **$20/user/month**

**Revenue:**
- 10,000 users × $20/month = **$200,000/month**
- **$2.4M/year ARR**

**Costs:**
- OCI infrastructure: ~$5,000/month
- Support: 2 people = $20,000/month
- **Profit: $175,000/month = $2.1M/year**

This is achievable!
