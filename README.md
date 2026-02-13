# 🏭 MockFactory

**Secure Multi-Language Code Execution Sandbox**

MockFactory is a production-ready code execution sandbox that runs user code securely in isolated Docker containers with comprehensive security controls, usage tiers, OAuth2 authentication, and payment processing.

## Features

### 🔒 Security
- **No Root Access**: All code runs as unprivileged `nobody` user
- **No System Access**: Network disabled, read-only filesystem, syscall filtering
- **Container Escape Detection**: Monitors for suspicious activity and escape attempts
- **Resource Limits**: CPU, memory, execution time, and PID limits enforced
- **Seccomp Profiles**: Dangerous syscalls blocked at kernel level

### 💻 Multi-Language Support
- Python
- PHP
- Perl
- JavaScript/Node.js
- Go
- Shell
- HTML

### 👤 Authentication
- **After Dark Systems SSO**: OAuth2 integration with After Dark Systems
- **Manual Authentication**: Email/password signup and signin
- **Dual Support**: Users can use either authentication method

### 📊 Usage Tiers

| Tier | Runs | Price | Features |
|------|------|-------|----------|
| **Anonymous** | 5 | Free | No account required |
| **Free Account** | 10 | Free | Execution history |
| **Pro** | Unlimited | $9.99/mo | Priority support, extended resources |
| **After Dark Employee** | Unlimited | Free | Premium support |

### 💳 Payment Processing
- Stripe integration for subscriptions
- Secure checkout sessions
- Webhook handling for subscription events

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (HTML/JS)                    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  FastAPI Backend                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Auth API   │  │  Execute API │  │ Payments API │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└──────┬──────────────────┬─────────────────┬────────────┘
       │                  │                 │
       ▼                  ▼                 ▼
┌─────────────┐  ┌──────────────────┐  ┌─────────────┐
│ PostgreSQL  │  │ Docker Sandbox   │  │   Stripe    │
│  (Users &   │  │ (Secure Code     │  │  (Payments) │
│ Executions) │  │  Execution)      │  │             │
└─────────────┘  └──────────────────┘  └─────────────┘
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- PostgreSQL 15+
- Redis 7+

### Local Development

1. **Clone and setup**:
```bash
cd /Users/ryan/development/mockfactory.io
cp .env.example .env
```

2. **Configure environment** (edit `.env`):
```env
# Database
DATABASE_URL=postgresql://mockfactory:password@localhost:5432/mockfactory
REDIS_URL=redis://localhost:6379/0

# After Dark Systems OAuth2
AFTERDARK_OAUTH_CLIENT_ID=your_client_id
AFTERDARK_OAUTH_CLIENT_SECRET=your_client_secret
AFTERDARK_OAUTH_AUTHORIZE_URL=https://auth.afterdarksystems.com/oauth/authorize
AFTERDARK_OAUTH_TOKEN_URL=https://auth.afterdarksystems.com/oauth/token
AFTERDARK_OAUTH_USERINFO_URL=https://auth.afterdarksystems.com/oauth/userinfo

# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Security
SECRET_KEY=your-secret-key-change-in-production
```

3. **Start services**:
```bash
docker-compose up -d
```

4. **Access**:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Frontend: Open `frontend/index.html` in browser

### Production Deployment

1. **Build and push Docker image**:
```bash
docker build -t mockfactory:latest .
docker tag mockfactory:latest your-registry/mockfactory:latest
docker push your-registry/mockfactory:latest
```

2. **Deploy to OCI**:
```bash
# Create compute instance with Docker
# Pull and run the container
docker run -d \
  --name mockfactory \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --env-file .env \
  your-registry/mockfactory:latest
```

3. **Configure DNS**:
```bash
# Already configured! mockfactory.io points to:
# ns1.p201.dns.oraclecloud.net.
# ns2.p201.dns.oraclecloud.net.
# ns3.p201.dns.oraclecloud.net.
# ns4.p201.dns.oraclecloud.net.

# Add A record to your server IP
oci dns record domain patch \
  --zone-name-or-id mockfactory.io \
  --domain mockfactory.io \
  --scope GLOBAL \
  --items '[{"domain":"mockfactory.io","rtype":"A","ttl":300,"rdata":"YOUR_SERVER_IP"}]'
```

## API Documentation

### Execute Code
```bash
POST /api/v1/code/execute
Content-Type: application/json
X-Session-Id: optional-session-id
Authorization: Bearer token (optional)

{
  "language": "python",
  "code": "print('Hello MockFactory!')",
  "timeout": 30
}
```

### Sign Up
```bash
POST /api/v1/auth/signup
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword"
}
```

### Sign In
```bash
POST /api/v1/auth/signin
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "securepassword"
}
```

### After Dark SSO
```bash
GET /api/v1/auth/sso/afterdark
# Redirects to After Dark Systems OAuth2 login
```

### Get Usage
```bash
GET /api/v1/code/usage
X-Session-Id: optional-session-id
Authorization: Bearer token (optional)
```

### Create Checkout Session
```bash
POST /api/v1/payments/create-checkout-session
Authorization: Bearer token
Content-Type: application/json

{
  "plan": "paid"
}
```

## Security Features

### Container Isolation
- **No Network**: Network disabled (`network_mode="none"`)
- **Read-Only Root**: Filesystem is read-only except `/tmp`
- **User Isolation**: Runs as `nobody:nogroup`
- **Capability Drop**: All Linux capabilities dropped
- **Resource Limits**: CPU, memory, PIDs constrained

### Syscall Filtering
Blocks dangerous system calls:
- `clone`, `unshare` (namespace manipulation)
- `mount`, `umount` (filesystem operations)
- `pivot_root`, `chroot` (container escape vectors)
- `reboot`, `sethostname` (system control)

### Escape Detection
Monitors for:
- Permission denied errors (privilege escalation attempts)
- Access to `/proc/`, `/sys/` (kernel interfaces)
- Suspicious mount/namespace operations

## Development

### Project Structure
```
mockfactory.io/
├── app/
│   ├── api/          # API routes
│   ├── core/         # Config, database
│   ├── models/       # SQLAlchemy models
│   ├── security/     # Auth, OAuth
│   ├── services/     # Business logic
│   └── sandboxes/    # Docker sandbox
├── frontend/         # HTML/JS frontend
├── docker/           # Dockerfile configs
├── alembic/          # Database migrations
└── tests/            # Tests
```

### Run Tests
```bash
pytest tests/
```

### Database Migrations
```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head
```

## Roadmap

- [ ] WebSocket support for real-time output
- [ ] Execution history API
- [ ] Code sharing/permalink generation
- [ ] Additional language runtimes (Rust, Ruby, etc.)
- [ ] Enhanced monitoring and analytics
- [ ] Rate limiting per IP
- [ ] Custom resource limits per tier

## License

Proprietary - After Dark Systems

## Support

For support, contact: support@afterdarksystems.com
