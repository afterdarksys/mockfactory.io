# MockFactory.io - Quick Start Guide

**Throw-away mock environments for testing**

Get instant access to Redis, MySQL, AWS S3, and more - without the setup hassle.

## What You Get

- **Real Services**: Redis, MySQL, PostgreSQL running in Docker
- **Cloud Emulation**: AWS S3, GCP Storage, Azure Blob backed by OCI
- **Pay Per Hour**: Only pay when testing (~$0.35-$0.75/hour)
- **Auto-Shutdown**: Environments auto-destroy after 4 hours of inactivity
- **Rich APIs**: Full protocol compatibility with existing SDKs

## Getting Started

### 1. Sign Up & Get API Key

```bash
curl -X POST https://mockfactory.io/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-password"}'

# Login to get access token
curl -X POST https://mockfactory.io/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-password"}'
```

### 2. Create an Environment

```bash
curl -X POST https://mockfactory.io/api/v1/environments \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-test-env",
    "services": [
      {"type": "redis", "version": "latest"},
      {"type": "mysql", "version": "8.0"},
      {"type": "aws_s3"}
    ],
    "auto_shutdown_hours": 4
  }'
```

**Response:**
```json
{
  "id": "env-abc123",
  "name": "my-test-env",
  "status": "running",
  "endpoints": {
    "redis": "redis://localhost:30145",
    "mysql": "mysql://root:mockfactory@localhost:30146/testdb",
    "aws_s3": "https://s3.env-abc123.mockfactory.io"
  },
  "hourly_rate": 0.30,
  "total_cost": 0.0
}
```

### 3. Use Your Services

#### Redis Example (Python)

```python
import redis

r = redis.Redis(host='localhost', port=30145)
r.set('foo', 'bar')
print(r.get('foo'))  # b'bar'
```

#### MySQL Example (Python)

```python
import mysql.connector

conn = mysql.connector.connect(
    host='localhost',
    port=30146,
    user='root',
    password='mockfactory',
    database='testdb'
)

cursor = conn.cursor()
cursor.execute("CREATE TABLE users (id INT, name VARCHAR(255))")
cursor.execute("INSERT INTO users VALUES (1, 'Alice')")
conn.commit()
```

#### AWS S3 Example (Python)

See `examples/python_s3_example.py` for full example.

```python
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='https://s3.env-abc123.mockfactory.io',
    aws_access_key_id='mockfactory',
    aws_secret_access_key='mockfactory'
)

# Upload
s3.put_object(Bucket='my-bucket', Key='test.txt', Body=b'Hello!')

# Download
obj = s3.get_object(Bucket='my-bucket', Key='test.txt')
print(obj['Body'].read())  # b'Hello!'
```

### 4. Monitor & Manage

```bash
# List your environments
curl -X GET https://mockfactory.io/api/v1/environments \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get specific environment
curl -X GET https://mockfactory.io/api/v1/environments/env-abc123 \
  -H "Authorization: Bearer YOUR_TOKEN"

# Stop environment (pause billing)
curl -X POST https://mockfactory.io/api/v1/environments/env-abc123/stop \
  -H "Authorization: Bearer YOUR_TOKEN"

# Destroy environment (delete all data)
curl -X DELETE https://mockfactory.io/api/v1/environments/env-abc123 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Pricing

| Service | Cost per Hour |
|---------|---------------|
| Redis | $0.10 |
| MySQL | $0.15 |
| PostgreSQL | $0.15 |
| MongoDB | $0.12 |
| AWS S3 | $0.05 |
| GCP Storage | $0.05 |
| Azure Blob | $0.05 |

**Example Costs:**
- Redis + MySQL + S3 = **$0.30/hour** (~$7.20 if left on for 24 hours)
- Full stack (Redis, MySQL, MongoDB, S3) = **$0.42/hour**

**Free Tier:** $5 in free credits (~14 hours of testing)

## Auto-Shutdown

Environments automatically shut down after **4 hours of inactivity** (configurable).

This prevents:
- ❌ Forgetting to turn off test environments
- ❌ Unexpected bills
- ❌ Wasted resources

## Language Support

- ✅ **Python** (boto3, redis-py, mysql-connector, etc.)
- ✅ **Go** (AWS SDK, go-redis, etc.)
- ✅ **Node.js** (aws-sdk, ioredis, mysql2)
- ✅ **Java** (AWS SDK, Jedis, JDBC)
- ✅ **PHP** (AWS SDK, predis, PDO)
- ✅ **Any language** with AWS/Redis/MySQL client libraries

## Advanced

### Custom Service Config

```json
{
  "services": [
    {
      "type": "mysql",
      "version": "8.0",
      "config": {
        "character_set": "utf8mb4",
        "max_connections": 100
      }
    }
  ]
}
```

### Longer Auto-Shutdown

```json
{
  "auto_shutdown_hours": 24
}
```

### Multiple Environments

You can have multiple environments running simultaneously. Each is isolated and billed separately.

## Need Help?

- 📧 Email: support@mockfactory.io
- 📚 Full Docs: https://docs.mockfactory.io
- 💬 Discord: https://discord.gg/mockfactory

## What's Next?

- ✅ More services (Kafka, RabbitMQ, Elasticsearch)
- ✅ More cloud APIs (Lambda, SQS, SNS)
- ✅ Persistent environments (keep data between sessions)
- ✅ Team collaboration
- ✅ CI/CD integration
