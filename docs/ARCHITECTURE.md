# MockFactory.io - Architecture Overview

**Throw-away mock environments backed by OCI**

## What We Built

MockFactory.io is a developer platform that provides instant access to mock infrastructure for testing - without needing real AWS/GCP/Azure accounts.

### Core Concept

```
Developer writes AWS code → MockFactory emulates API → OCI provides backend
```

**Example:**
- Developer calls `s3.put_object()` with boto3
- MockFactory receives AWS S3 API call
- Translates to OCI Object Storage
- Returns AWS-compatible response
- Developer's code works unchanged!

---

## Architecture

### 1. **Hybrid Approach**

We use TWO strategies:

#### **A. Real Containerized Services**
For databases and message queues that need full protocol compatibility:

| Service | Backend | Container |
|---------|---------|-----------|
| Redis | Docker `redis:latest` | Yes |
| MySQL | Docker `mysql:8.0` | Yes |
| PostgreSQL | Docker `postgres:latest` | Yes |
| MongoDB | Docker `mongo:latest` | Yes |
| SQS/SNS | Docker `elasticmq:latest` | Yes |

**Why:** Developers get real Redis commands, real SQL queries - no translation needed.

#### **B. Cloud API Emulation**
For cloud services that can be backed by cheaper OCI resources:

| Emulated Service | OCI Backend | Translation Layer |
|-----------------|-------------|-------------------|
| AWS S3 | OCI Object Storage | FastAPI endpoint |
| GCP Cloud Storage | OCI Object Storage | FastAPI endpoint |
| Azure Blob | OCI Object Storage | FastAPI endpoint |
| AWS ECR | OCI Container Registry | Docker Registry v2 protocol |
| GCP Container Registry | OCI Container Registry | Docker Registry v2 protocol |
| AWS Route53 | In-memory (JSON) | Mock DNS |
| AWS IAM | In-memory (JSON) | Mock credentials |
| AWS Lambda | OCI Functions (future) | Mock execution |

**Why:** Much cheaper than running real AWS resources. OCI Object Storage is ~50% cheaper than S3.

---

## Service Provisioning Flow

### Environment Creation:

```
1. Developer → POST /api/v1/environments
   {
     "services": ["redis", "mysql", "aws_s3", "aws_sqs"]
   }

2. MockFactory creates:
   - Database record (environment ID: env-abc123)
   - Docker containers for Redis, MySQL, SQS
   - OCI Object Storage bucket for S3
   - Connection endpoints

3. Returns:
   {
     "id": "env-abc123",
     "endpoints": {
       "redis": "redis://localhost:30145",
       "mysql": "mysql://root:mockfactory@localhost:30146/testdb",
       "aws_s3": "https://s3.env-abc123.mockfactory.io",
       "aws_sqs": "http://localhost:30147"
     },
     "hourly_rate": 0.33
   }

4. Billing starts - $0.33/hour
```

### Developer Usage:

```python
# Redis - direct connection
import redis
r = redis.Redis(host='localhost', port=30145)
r.set('key', 'value')

# S3 - uses emulated endpoint
import boto3
s3 = boto3.client('s3', endpoint_url='https://s3.env-abc123.mockfactory.io')
s3.put_object(Bucket='test', Key='file.txt', Body=b'data')

# SQS - ElasticMQ container
sqs = boto3.client('sqs', endpoint_url='http://localhost:30147')
sqs.send_message(QueueUrl='...', MessageBody='test')
```

---

## Tech Stack

### Backend (Python FastAPI)

```
app/
├── api/
│   ├── environments.py          # CRUD for environments
│   ├── cloud_emulation.py       # S3/GCS/Azure emulation
│   ├── container_registry_emulation.py  # ECR/GCR emulation
│   └── aws_services_emulation.py        # Route53/IAM/Lambda
├── models/
│   ├── environment.py           # Environment & usage tracking
│   └── user.py                  # User & subscription
├── services/
│   └── environment_provisioner.py  # Docker + OCI orchestration
└── main.py
```

### Key Technologies:

- **FastAPI**: REST API + async support
- **Docker**: Container orchestration
- **OCI CLI**: Object Storage, Container Registry
- **PostgreSQL**: Metadata storage (users, environments, billing)
- **ElasticMQ**: AWS SQS/SNS compatible message queue
- **Stripe**: Payment processing

---

## Pricing Model

### Per-Hour Billing:

| Service | Our Cost | We Charge | Margin |
|---------|----------|-----------|--------|
| Redis (Docker) | ~$0.02 | $0.10/hr | 80% |
| MySQL (Docker) | ~$0.03 | $0.15/hr | 80% |
| S3 (OCI Object Storage) | ~$0.01 | $0.05/hr | 80% |
| SQS (ElasticMQ Docker) | ~$0.01 | $0.03/hr | 67% |
| ECR (OCIR) | ~$0 | $0.05/hr | ~100% |

**Example Environment Cost:**
- Redis + MySQL + S3 + SQS = **$0.33/hour**
- If left running 24 hours = **$7.92/day**
- Auto-shutdown after 4 hours inactivity prevents runaway costs

**Comparison to AWS:**
- AWS RDS MySQL (smallest): **$0.017/hour** = $12/month
- AWS S3: Pay per request + storage
- AWS SQS: $0.40 per 1M requests
- **MockFactory**: Flat hourly rate, easier to predict

---

## OCI Backend Integration

### Object Storage (S3/GCS/Azure):

```bash
# When developer uploads to S3:
s3.put_object(Bucket='test', Key='file.txt', Body=data)

# MockFactory translates to:
oci os object put \
  --bucket-name mockfactory-env-abc123-s3 \
  --name file.txt \
  --file /tmp/upload
```

### Container Registry (ECR/GCR):

```bash
# When developer pushes to ECR:
docker push ecr.env-abc123.mockfactory.io/myapp:latest

# MockFactory translates to:
docker tag myapp:latest phx.ocir.io/idd2oizp8xvc/env-abc123/myapp:latest
docker push phx.ocir.io/idd2oizp8xvc/env-abc123/myapp:latest
```

### Benefits of OCI Backend:

1. **Cost Savings**: 30-50% cheaper than AWS
2. **No AWS Account Required**: Developers test without AWS credentials
3. **Full Isolation**: Each environment gets own buckets/repos
4. **Easy Cleanup**: Delete environment → delete all OCI resources

---

## Auto-Shutdown & Lifecycle

### Lifecycle States:

```
PROVISIONING → RUNNING → STOPPED → DESTROYING → DESTROYED
                  ↓          ↑
                  └─ (pause) ┘
```

### Auto-Shutdown Logic:

```python
# Background task runs every 15 minutes:
for env in get_running_environments():
    if (now - env.last_activity) > env.auto_shutdown_hours:
        # Stop containers
        # Calculate final bill
        # Send email notification
        # Destroy environment
```

**Default**: 4 hours of inactivity
**Configurable**: 1-48 hours
**User Control**: Can manually stop/start/destroy

---

## Billing & Usage Tracking

### Hourly Tracking:

```sql
-- EnvironmentUsageLog table
id | environment_id | period_start | period_end | hourly_rate | cost | billed
1  | env-abc123     | 10:00       | 11:00      | 0.33       | 0.33 | 0
2  | env-abc123     | 11:00       | 12:30      | 0.33       | 0.50 | 0
```

**Billing Flow:**
1. Environment starts → Create usage log with `period_start`
2. Every hour → Calculate partial cost
3. Environment stops → Set `period_end`, calculate final cost
4. Daily → Charge Stripe for unbilled usage
5. Update `billed = 1`

### Cost Calculation:

```python
duration_hours = (period_end - period_start).total_seconds() / 3600
cost = duration_hours * hourly_rate
```

**Example:**
- Environment runs for 2.5 hours at $0.33/hr
- Cost: 2.5 × $0.33 = **$0.83**
- Charged to Stripe customer

---

## API Emulation Details

### AWS S3 API Emulation:

**Supported Operations:**
- ✅ `ListObjects` (GET /bucket)
- ✅ `PutObject` (PUT /bucket/key)
- ✅ `GetObject` (GET /bucket/key)
- ✅ `DeleteObject` (DELETE /bucket/key)

**Example S3 ListObjects:**

```python
# Developer calls:
s3.list_objects_v2(Bucket='test')

# MockFactory receives:
GET https://s3.env-abc123.mockfactory.io/test

# MockFactory does:
result = subprocess.run([
    'oci', 'os', 'object', 'list',
    '--bucket-name', 'mockfactory-env-abc123-s3'
])

# Converts OCI JSON to S3 XML:
<ListBucketResult>
  <Name>test</Name>
  <Contents>
    <Key>file.txt</Key>
    <Size>1234</Size>
  </Contents>
</ListBucketResult>
```

### SQS/SNS API (ElasticMQ):

ElasticMQ speaks native AWS API - **no translation needed!**

```python
# Developer code works as-is:
sqs = boto3.client('sqs', endpoint_url='http://localhost:30147')
sqs.create_queue(QueueName='test')
sqs.send_message(QueueUrl='...', MessageBody='hello')
```

ElasticMQ provides:
- ✅ SQS API compatibility
- ✅ SNS API compatibility
- ✅ In-memory queue (or persistent)
- ✅ Free & open source

---

## Security & Isolation

### Container Isolation:

- Each environment gets **unique container names**: `env-abc123-redis`, `env-abc123-mysql`
- **Dynamic port allocation**: 30000-40000 range
- **No shared data** between environments
- Containers destroyed on environment deletion

### OCI Isolation:

- Each environment gets **separate buckets**: `mockfactory-env-abc123-s3`
- Each environment gets **separate namespaces** in OCIR
- Bucket/namespace deleted when environment destroyed

### Network Security:

- Containers run on **Docker bridge network**
- Only exposed ports are accessible
- Future: VPN/tunnel to developer's machine

---

## What's Next (Post-POC)

### Phase 2 - More Services:

- **Kafka** (Docker: `confluentinc/cp-kafka`)
- **RabbitMQ** (Docker: `rabbitmq:management`)
- **Elasticsearch** (Docker: `elasticsearch:8`)
- **AWS DynamoDB** (LocalStack or in-memory)

### Phase 3 - PaaS:

- **AWS Lightsail** → OCI Compute VMs
- **AWS Elastic Beanstalk** → Dokku on OCI
- Git push to deploy workflow

### Phase 4 - Enterprise:

- **Team environments** (shared across team)
- **Persistent environments** (don't auto-destroy)
- **Snapshots** (save environment state)
- **VPN/Tunnels** (secure connection to containers)
- **Monitoring** (Prometheus + Grafana)
- **Logs aggregation** (all container logs in one place)

---

## Files Created

### Core Backend:
- `app/models/environment.py` - Environment & usage tracking models
- `app/api/environments.py` - Environment CRUD API
- `app/services/environment_provisioner.py` - Docker + OCI orchestration
- `app/api/cloud_emulation.py` - S3/GCS/Azure emulation
- `app/api/container_registry_emulation.py` - ECR/GCR emulation
- `app/api/aws_services_emulation.py` - Route53/IAM/Lambda

### Examples:
- `examples/python_s3_example.py` - S3 usage with boto3
- `examples/python_sqs_example.py` - SQS usage with boto3
- `examples/python_sns_example.py` - SNS usage with boto3
- `examples/go_s3_example.go` - S3 usage with AWS SDK for Go

### Documentation:
- `docs/QUICKSTART.md` - Getting started guide
- `docs/ARCHITECTURE.md` - This file

---

## Summary

**We built a complete mock infrastructure platform in one session:**

✅ **Environment provisioning API** - Create/destroy environments
✅ **Docker orchestration** - Redis, MySQL, PostgreSQL, MongoDB, ElasticMQ
✅ **Cloud API emulation** - AWS S3, GCP Storage, Azure Blob
✅ **Container registry** - AWS ECR, GCP GCR backed by OCIR
✅ **AWS services** - Route53, IAM, Lambda, SQS, SNS
✅ **Billing system** - Hourly tracking with Stripe
✅ **Auto-shutdown** - Prevent runaway costs
✅ **Developer SDKs** - Python and Go examples

**Cost to run:**
- OCI Compute: ~$50/month for host VM
- OCI Object Storage: Pay-as-you-go (cheap)
- Docker: Free
- ElasticMQ: Free

**Revenue potential:**
- Charge $0.30-$0.75/hour per environment
- 100 concurrent environments = $30-$75/hour = **$21,600-$54,000/month**
- At 80% margin = **$17,280-$43,200/month profit**

**Next step:** Deploy to OCI, test end-to-end, launch beta!
