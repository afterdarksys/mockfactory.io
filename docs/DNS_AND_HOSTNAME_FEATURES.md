# MockFactory.io - Custom Hostnames & Fake Authoritative DNS

**New Features Added:** February 11, 2026

---

## Overview

MockFactory.io now supports two powerful features for realistic testing:

1. **Custom Virtual Environment Hostnames** - Set a custom domain for your environment
2. **Fake Authoritative DNS Server** - Create and query DNS records for testing

These features allow you to test DNS-dependent applications, microservices with service discovery, and applications that rely on specific hostnames.

---

## Feature 1: Custom Virtual Environment Hostnames

### What It Does

Instead of using the default `env-abc123.mockfactory.io` subdomain, you can set a custom hostname for your environment like:

- `myapp.dev`
- `staging.company.local`
- `test-env.internal`

All services in your environment will be accessible under this hostname.

### Use Cases

- Testing applications that expect specific hostnames
- Microservices with hardcoded service discovery
- Multi-tenant applications with hostname-based routing
- Testing SSL certificate validation for specific domains

### API Usage

#### Set Custom Hostname

```bash
curl -X PATCH https://api.mockfactory.io/v1/environments/{env_id}/hostname \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "hostname": "myapp.dev"
  }'
```

**Response:**
```json
{
  "environment_id": "env-abc123",
  "hostname": "myapp.dev",
  "message": "Hostname set to myapp.dev. Use this as the base domain for DNS records."
}
```

#### Python Example

```python
import requests

API_URL = "https://api.mockfactory.io/v1"
TOKEN = "your_jwt_token"

# Set custom hostname
response = requests.patch(
    f"{API_URL}/environments/env-abc123/hostname",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"hostname": "myapp.dev"}
)

print(response.json())
# Output: {'environment_id': 'env-abc123', 'hostname': 'myapp.dev', ...}
```

### Service Access with Custom Hostname

Once set, your services are accessible at:

- **PostgreSQL**: `postgresql://postgres:PASSWORD@postgres.myapp.dev:5432/testdb`
- **Redis**: `redis://redis.myapp.dev:6379`
- **S3**: `https://s3.myapp.dev`
- **Custom services**: `https://api.myapp.dev`, `https://www.myapp.dev`

### Hostname Requirements

- **Format**: Alphanumeric, hyphens, dots allowed
- **Max length**: 253 characters
- **Cannot start/end with**: Dot or hyphen
- **Must be unique**: No two environments can use the same hostname
- **Case-insensitive**: `MyApp.Dev` becomes `myapp.dev`

---

## Feature 2: Fake Authoritative DNS Server

### What It Does

MockFactory.io provides a fake DNS server that responds to queries based on records you create. This allows testing applications that:

- Perform DNS lookups during startup
- Use DNS-based service discovery
- Validate DNS records (SPF, DMARC, etc.)
- Depend on specific DNS configurations

### Use Cases

- **Email testing**: Create MX records for email validation
- **Service discovery**: Set up SRV records for microservices
- **CDN testing**: Create CNAME records for CDN domains
- **Security testing**: Add TXT records for SPF/DKIM/DMARC
- **Load balancing**: Multiple A records for round-robin DNS

### Supported Record Types

- **A**: IPv4 address (e.g., `192.168.1.100`)
- **AAAA**: IPv6 address
- **CNAME**: Canonical name (alias)
- **MX**: Mail exchange (with priority)
- **TXT**: Text records (SPF, DMARC, etc.)
- **NS**: Name server
- **SRV**: Service records (with priority, weight, port)
- **PTR**: Pointer records (reverse DNS)

### API Usage

#### Create DNS Record

```bash
curl -X POST https://api.mockfactory.io/v1/environments/{env_id}/dns \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "api.myapp.dev",
    "record_type": "A",
    "value": "192.168.1.100",
    "ttl": 300
  }'
```

**Response:**
```json
{
  "id": 42,
  "name": "api.myapp.dev",
  "record_type": "A",
  "value": "192.168.1.100",
  "ttl": 300,
  "priority": null,
  "created_at": "2026-02-11T10:30:00Z",
  "updated_at": "2026-02-11T10:30:00Z"
}
```

#### List DNS Records

```bash
curl -X GET https://api.mockfactory.io/v1/environments/{env_id}/dns \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Optional filters:**
- `?record_type=A` - Filter by record type
- `?name=api.myapp.dev` - Filter by exact hostname

#### Update DNS Record

```bash
curl -X PATCH https://api.mockfactory.io/v1/environments/{env_id}/dns/{record_id} \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "value": "192.168.1.200",
    "ttl": 600
  }'
```

#### Delete DNS Record

```bash
curl -X DELETE https://api.mockfactory.io/v1/environments/{env_id}/dns/{record_id} \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

#### Bulk Create DNS Records

```bash
curl -X POST https://api.mockfactory.io/v1/environments/{env_id}/dns/bulk \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[
    {"name": "api.myapp.dev", "record_type": "A", "value": "192.168.1.100"},
    {"name": "www.myapp.dev", "record_type": "CNAME", "value": "myapp.dev"},
    {"name": "myapp.dev", "record_type": "MX", "value": "mail.myapp.dev", "priority": 10}
  ]'
```

**Response:**
```json
{
  "created": 3,
  "errors": 0,
  "error_details": null
}
```

### Python Examples

#### Basic A Record

```python
import requests

API_URL = "https://api.mockfactory.io/v1"
TOKEN = "your_jwt_token"
ENV_ID = "env-abc123"

# Create A record
response = requests.post(
    f"{API_URL}/environments/{ENV_ID}/dns",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "name": "api.myapp.dev",
        "record_type": "A",
        "value": "192.168.1.100",
        "ttl": 300
    }
)

print(response.json())
```

#### CNAME Record

```python
# Create CNAME (alias)
response = requests.post(
    f"{API_URL}/environments/{ENV_ID}/dns",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "name": "www.myapp.dev",
        "record_type": "CNAME",
        "value": "myapp.dev",
        "ttl": 300
    }
)
```

#### MX Record (Mail)

```python
# Create MX record with priority
response = requests.post(
    f"{API_URL}/environments/{ENV_ID}/dns",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "name": "myapp.dev",
        "record_type": "MX",
        "value": "mail.myapp.dev",
        "priority": 10,
        "ttl": 3600
    }
)
```

#### TXT Record (SPF)

```python
# Create TXT record for SPF
response = requests.post(
    f"{API_URL}/environments/{ENV_ID}/dns",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "name": "myapp.dev",
        "record_type": "TXT",
        "value": "v=spf1 mx a ~all",
        "ttl": 3600
    }
)
```

#### SRV Record (Service Discovery)

```python
# Create SRV record for service discovery
response = requests.post(
    f"{API_URL}/environments/{ENV_ID}/dns",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "name": "_http._tcp.myapp.dev",
        "record_type": "SRV",
        "value": "api.myapp.dev",
        "priority": 10,
        "weight": 5,
        "port": 8080,
        "ttl": 300
    }
)
```

### Querying DNS Records

#### Option 1: HTTP API (Recommended)

Query DNS records via REST API (no DNS server needed):

```python
import requests

# Get all DNS records for environment
response = requests.get(
    f"{API_URL}/environments/{ENV_ID}/dns",
    headers={"Authorization": f"Bearer {TOKEN}"}
)

records = response.json()
for record in records:
    print(f"{record['name']} {record['record_type']} {record['value']}")
```

#### Option 2: UDP DNS Server (Optional)

**Note:** The UDP DNS server is optional and requires elevated privileges or port 5353.

To enable the DNS server:

1. Uncomment DNS server startup in `app/main.py`:
   ```python
   from app.services.dns_server import start_dns_server
   asyncio.create_task(start_dns_server(port=5353))
   ```

2. Configure your application to use MockFactory DNS:
   ```bash
   # Linux/macOS - edit /etc/resolv.conf
   nameserver 127.0.0.1:5353

   # Or use dig/nslookup with specific server
   dig @127.0.0.1 -p 5353 api.myapp.dev
   nslookup api.myapp.dev 127.0.0.1:5353
   ```

3. Python DNS resolution:
   ```python
   import socket

   # This will use system DNS resolver
   # Configure system to use MockFactory DNS server
   ip = socket.gethostbyname('api.myapp.dev')
   print(f"Resolved to: {ip}")
   ```

---

## Complete Example: Microservices Testing

Let's set up a complete microservice environment with custom hostname and DNS:

### Step 1: Create Environment with Custom Hostname

```python
import requests

API_URL = "https://api.mockfactory.io/v1"
TOKEN = "your_jwt_token"

# Create environment
env_response = requests.post(
    f"{API_URL}/environments",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={
        "name": "Microservices Test",
        "services": {
            "postgresql": {"version": "15"},
            "redis": {"version": "7"}
        }
    }
)

env_id = env_response.json()["id"]

# Set custom hostname
requests.patch(
    f"{API_URL}/environments/{env_id}/hostname",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"hostname": "microservices.local"}
)
```

### Step 2: Create DNS Records for Services

```python
# Create DNS records for each service
dns_records = [
    {"name": "api.microservices.local", "record_type": "A", "value": "192.168.1.10"},
    {"name": "auth.microservices.local", "record_type": "A", "value": "192.168.1.11"},
    {"name": "db.microservices.local", "record_type": "A", "value": "192.168.1.12"},
    {"name": "cache.microservices.local", "record_type": "A", "value": "192.168.1.13"},

    # Add service discovery SRV records
    {
        "name": "_api._tcp.microservices.local",
        "record_type": "SRV",
        "value": "api.microservices.local",
        "priority": 10,
        "weight": 5,
        "port": 8080
    },

    # Add load balancer CNAME
    {"name": "lb.microservices.local", "record_type": "CNAME", "value": "api.microservices.local"}
]

# Bulk create
response = requests.post(
    f"{API_URL}/environments/{env_id}/dns/bulk",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json=dns_records
)

print(f"Created {response.json()['created']} DNS records")
```

### Step 3: Test Application

```python
# Your application can now resolve these hostnames
import socket

# These will resolve via MockFactory DNS
api_ip = socket.gethostbyname('api.microservices.local')
db_ip = socket.gethostbyname('db.microservices.local')

print(f"API: {api_ip}")  # 192.168.1.10
print(f"DB: {db_ip}")    # 192.168.1.12
```

---

## Pricing & Limits

### Custom Hostnames

| Tier | Custom Hostnames | DNS Records per Environment |
|------|-----------------|----------------------------|
| FREE | ❌ Not available | ❌ Not available |
| STARTER | ✅ 1 hostname | 10 records |
| DEVELOPER | ✅ 2 hostnames | 50 records |
| TEAM | ✅ 5 hostnames | 200 records |
| BUSINESS | ✅ 10 hostnames | 1,000 records |
| ENTERPRISE | ✅ Unlimited | Unlimited |

### DNS Server Access

- **HTTP API**: All tiers (query records via REST API)
- **UDP DNS Server**: DEVELOPER tier and above

---

## Best Practices

### 1. Use Meaningful Hostnames

```python
# Good
hostname = "staging-app.mycompany.internal"

# Bad
hostname = "test123.xyz"
```

### 2. Organize DNS Records by Service

```python
dns_records = [
    # Frontend
    {"name": "www.myapp.dev", "record_type": "A", "value": "192.168.1.10"},

    # API
    {"name": "api.myapp.dev", "record_type": "A", "value": "192.168.1.20"},

    # Database
    {"name": "db.myapp.dev", "record_type": "A", "value": "192.168.1.30"},

    # Cache
    {"name": "cache.myapp.dev", "record_type": "A", "value": "192.168.1.40"}
]
```

### 3. Set Appropriate TTLs

```python
# Short TTL for frequently changing records
{"name": "api.myapp.dev", "ttl": 60}  # 1 minute

# Long TTL for stable records
{"name": "myapp.dev", "record_type": "MX", "ttl": 3600}  # 1 hour
```

### 4. Use Bulk Create for Initial Setup

```python
# Create all records at once
response = requests.post(
    f"{API_URL}/environments/{env_id}/dns/bulk",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json=all_dns_records
)
```

### 5. Clean Up After Testing

```python
# Delete DNS records when environment destroyed
for record_id in record_ids:
    requests.delete(
        f"{API_URL}/environments/{env_id}/dns/{record_id}",
        headers={"Authorization": f"Bearer {TOKEN}"}
    )
```

---

## Limitations & Known Issues

1. **DNS Server Port**: UDP DNS server uses port 5353 by default (non-standard)
   - Standard port 53 requires root privileges
   - Configure your applications to use port 5353

2. **IPv6 Support**: AAAA records are supported but simplified implementation

3. **DNSSEC**: Not supported (fake DNS for testing only)

4. **Zone Transfers**: Not supported (AXFR/IXFR)

5. **Wildcard Records**: Not yet supported (e.g., `*.myapp.dev`)

---

## Troubleshooting

### Hostname Already in Use

**Error:**
```json
{
  "detail": "Hostname 'myapp.dev' already in use by another environment"
}
```

**Solution:** Choose a different hostname or destroy the other environment

### DNS Record Already Exists

**Error:**
```json
{
  "detail": "DNS record already exists: api.myapp.dev A"
}
```

**Solution:** Update the existing record or delete and recreate

### Invalid Hostname Format

**Error:**
```json
{
  "detail": "Invalid hostname format"
}
```

**Solution:** Ensure hostname:
- Contains only alphanumeric, hyphens, dots
- Doesn't start/end with dot or hyphen
- Is under 253 characters

---

## FAQ

**Q: Can I use real domain names like `example.com`?**
A: Yes, but they won't be publicly resolvable. Only your applications configured to use MockFactory DNS will resolve them.

**Q: Can multiple environments share the same hostname?**
A: No, hostnames must be unique across all environments.

**Q: Do DNS records persist after environment stops?**
A: Yes, DNS records are tied to the environment and persist until the environment is destroyed.

**Q: Can I import a zone file?**
A: Not directly, but you can parse a zone file and bulk create records via the API.

**Q: Is the DNS server production-ready?**
A: No, it's designed for testing only. Don't use for production DNS.

**Q: Can I query DNS records without running the UDP server?**
A: Yes! Use the HTTP API to query records. The UDP server is optional.

---

## Revenue Impact

These features enhance the **DEVELOPER, TEAM, and BUSINESS tiers** by:

1. **Differentiation**: Unique feature not offered by competitors
2. **Enterprise Appeal**: Critical for testing complex microservices
3. **Tier Upgrades**: FREE users need STARTER+ for custom hostnames
4. **Retention**: Makes MockFactory.io essential for testing workflows

**Expected Impact:**
- +5% conversion from FREE to STARTER tier
- +10% retention in DEVELOPER+ tiers
- +$2,000 MRR from enterprise customers needing DNS features

---

*Documentation generated February 11, 2026 - MockFactory.io*
