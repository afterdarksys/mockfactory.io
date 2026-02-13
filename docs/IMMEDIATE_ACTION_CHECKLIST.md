# MockFactory.io - Immediate Action Checklist
**Priority tasks for the next 48 hours**

**Date:** February 11, 2026
**Status:** CRITICAL BUGS - STAGING ONLY

---

## STOP: Do NOT deploy to production until these are fixed

MockFactory.io has **12 critical bugs** that will cause production failures. This checklist prioritizes the most urgent fixes for the next 48 hours.

---

## Tuesday, February 11 (TODAY) - 8 hours

### Morning (4 hours)

**1. BUG-001: Database Migrations (CRITICAL - BLOCKER)**
```bash
# Current code will FAIL on existing database
# Fix: Implement Alembic migrations

cd /Users/ryan/development/mockfactory.io

# Initialize Alembic
alembic init alembic

# Edit alembic.ini - set sqlalchemy.url
# Edit alembic/env.py - import Base from app.core.database

# Create initial migration
alembic revision --autogenerate -m "initial schema"

# Test on empty database
docker exec -it mockfactory-postgres psql -U mockfactory -c "DROP DATABASE IF EXISTS mockfactory_test; CREATE DATABASE mockfactory_test;"

# Run migration
DATABASE_URL=postgresql://mockfactory:password@localhost:5432/mockfactory_test alembic upgrade head

# Verify tables created
docker exec -it mockfactory-postgres psql -U mockfactory mockfactory_test -c "\dt"
```

**Expected Result:** Clean migration from empty database
**Time:** 2 hours

**2. BUG-007: Cloud Emulation Missing DB Dependency (HIGH - EASY FIX)**
```python
# File: app/api/cloud_emulation.py

# Fix these functions by adding db parameter:
# Line 136: s3_put_object
# Line 186: s3_get_object
# Line 229: s3_delete_object
# Line 318: gcs_upload_object
# Line 421: azure_put_blob

# BEFORE:
async def s3_put_object(
    bucket_name: str,
    object_key: str,
    file: bytes = File(...),
    environment: Environment = Depends(verify_environment_access)
):

# AFTER:
async def s3_put_object(
    bucket_name: str,
    object_key: str,
    file: bytes = File(...),
    environment: Environment = Depends(verify_environment_access),
    db: Session = Depends(get_db)  # ADD THIS LINE
):
```

**Expected Result:** No more undefined 'db' errors in cloud emulation
**Time:** 30 minutes

**3. Remove Base.metadata.create_all() from main.py**
```python
# File: app/main.py
# Line 21 - DELETE THIS LINE:
Base.metadata.create_all(bind=engine)

# Migrations will handle schema creation now
```

**Time:** 5 minutes

### Afternoon (4 hours)

**4. BUG-003: Docker Socket Proxy Integration (CRITICAL)**
```bash
# Install docker-py library
pip install docker
pip freeze > requirements.txt
```

```python
# File: app/services/environment_provisioner.py
# Replace subprocess calls with docker-py

import os
import docker

class EnvironmentProvisioner:
    def __init__(self, db: Session):
        self.db = db
        # Use DOCKER_HOST from environment or default
        docker_host = os.getenv('DOCKER_HOST', 'unix:///var/run/docker.sock')
        self.docker_client = docker.DockerClient(base_url=docker_host)

    async def _provision_container(self, ...):
        # REPLACE subprocess.run() with docker_client.containers.run()

        container = self.docker_client.containers.run(
            image=service_config["image"],
            name=container_name,
            detach=True,
            ports={f"{service_config['port']}/tcp": host_port},
            environment=service_config["env"],
            command=service_config.get("command", "").split() if service_config.get("command") else None
        )

        return {
            "container_id": container.id,
            "endpoint": endpoint,
            "host_port": host_port
        }
```

**Expected Result:** Containers created through docker-proxy, not direct socket
**Time:** 3 hours

---

## Wednesday, February 12 - 8 hours

### Morning (4 hours)

**5. BUG-004: OCI Credentials Mounting (CRITICAL)**
```yaml
# File: docker-compose.prod.yml
# Lines 90-91 - FIX PATHS:

environment:
  # BEFORE (WRONG):
  - OCI_CONFIG_FILE=/app/config/oci_config
  - OCI_KEY_FILE=/app/config/oci_key.pem

  # AFTER (CORRECT):
  - OCI_CONFIG_FILE=/run/secrets/oci_config
  - OCI_KEY_FILE=/run/secrets/oci_key
```

```bash
# Create setup script
cat > scripts/setup-oci-secrets.sh << 'EOF'
#!/bin/bash
mkdir -p secrets
cp ~/.oci/config secrets/oci_config
cp ~/.oci/oci_api_key.pem secrets/oci_key.pem
chmod 600 secrets/*
echo "OCI secrets ready"
EOF

chmod +x scripts/setup-oci-secrets.sh
./scripts/setup-oci-secrets.sh
```

**Expected Result:** OCI commands work in production container
**Time:** 1 hour

**6. BUG-009: Container Health Checks (HIGH)**
```python
# File: app/services/environment_provisioner.py
# Add after container.run():

async def _provision_container(self, ...):
    container = self.docker_client.containers.run(...)

    # Wait for service to be healthy
    max_wait = 60  # seconds
    for attempt in range(max_wait):
        try:
            if service_type == "redis":
                import redis
                r = redis.Redis(
                    host='localhost',
                    port=host_port,
                    password=redis_password,
                    socket_connect_timeout=1
                )
                r.ping()
                logger.info(f"Redis container {container_name} is healthy")
                break

            elif service_type.startswith("postgresql"):
                import psycopg2
                conn = psycopg2.connect(
                    host='localhost',
                    port=host_port,
                    user='postgres',
                    password=db_password,
                    database='testdb',
                    connect_timeout=1
                )
                conn.close()
                logger.info(f"PostgreSQL container {container_name} is healthy")
                break

        except Exception as e:
            if attempt == max_wait - 1:
                # Timeout - kill container
                container.stop()
                container.remove()
                raise RuntimeError(
                    f"{service_type} container started but service failed health check after {max_wait}s: {e}"
                )
            await asyncio.sleep(1)

    return {...}
```

**Expected Result:** Failed database containers caught before returning "running" status
**Time:** 3 hours

### Afternoon (4 hours)

**7. BUG-005: Stripe Webhook Enhanced Validation (CRITICAL)**
```python
# File: app/api/payments.py
# Replace webhook handler (line 172):

import logging
logger = logging.getLogger(__name__)

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle Stripe webhook events with signature verification"""

    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    # Validate signature header exists
    if not sig_header:
        logger.warning(f"Stripe webhook received without signature from {request.client.host}")
        raise HTTPException(status_code=400, detail="Missing signature header")

    # Validate webhook secret is configured
    if not settings.STRIPE_WEBHOOK_SECRET or settings.STRIPE_WEBHOOK_SECRET == "":
        logger.error("STRIPE_WEBHOOK_SECRET not configured in environment!")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        logger.info(f"Webhook verified successfully: {event['type']} from {request.client.host}")

    except ValueError as e:
        logger.warning(f"Invalid webhook payload from {request.client.host}: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Webhook signature verification FAILED from {request.client.host}: {e}")
        logger.error(f"Signature header: {sig_header[:50]}...")
        # TODO: Alert security team
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Rest of handler...
```

**Expected Result:** Webhook attacks logged and blocked
**Time:** 1 hour

**8. Add .env.example with required variables**
```bash
# File: .env.example
cat > .env.example << 'EOF'
# Database
DATABASE_URL=postgresql://mockfactory:YOUR_PASSWORD@localhost:5432/mockfactory
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=generate-with-openssl-rand-hex-32
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# OAuth (Authentik)
OAUTH_CLIENT_ID=your-client-id
OAUTH_CLIENT_SECRET=your-client-secret
OAUTH_AUTHORIZE_URL=https://auth.mockfactory.io/application/o/authorize/
OAUTH_TOKEN_URL=https://auth.mockfactory.io/application/o/token/
OAUTH_USERINFO_URL=https://auth.mockfactory.io/application/o/userinfo/

# Stripe Product IDs (run stripe_setup.py first)
STRIPE_PRICE_PROFESSIONAL=
STRIPE_PRICE_GOVERNMENT=
STRIPE_PRICE_ENTERPRISE=

# Docker
DOCKER_HOST=tcp://docker-proxy:2375

# OCI (Oracle Cloud)
OCI_CONFIG_FILE=/run/secrets/oci_config
OCI_KEY_FILE=/run/secrets/oci_key
EOF
```

**Time:** 30 minutes

**9. Test All Fixes**
```bash
# Start stack
docker-compose -f docker-compose.prod.yml up -d

# Test environment creation
curl -X POST http://localhost:8000/api/v1/environments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "services": [
      {"type": "redis", "version": "latest"},
      {"type": "postgresql", "version": "15"}
    ],
    "auto_shutdown_hours": 4
  }'

# Verify containers healthy
docker ps

# Test S3 operations
curl http://localhost:8000/s3/test-bucket

# Check logs for errors
docker logs mockfactory-api
```

**Time:** 2.5 hours

---

## Thursday, February 13 - 8 hours

### Morning (4 hours)

**10. Setup Basic Monitoring**
```bash
# Create docker-compose.monitoring.yml
cat > docker-compose.monitoring.yml << 'EOF'
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: mockfactory-prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    networks:
      - mockfactory

  grafana:
    image: grafana/grafana:latest
    container_name: mockfactory-grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    networks:
      - mockfactory

volumes:
  prometheus_data:
  grafana_data:

networks:
  mockfactory:
    external: true
EOF

# Create prometheus config
mkdir -p monitoring
cat > monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'mockfactory-api'
    static_configs:
      - targets: ['mockfactory-api:8000']
EOF

# Start monitoring
docker-compose -f docker-compose.monitoring.yml up -d
```

**Expected Result:** Prometheus at localhost:9090, Grafana at localhost:3000
**Time:** 2 hours

**11. Add Health Check Improvements**
```python
# File: app/main.py
# Enhance health check endpoint:

from sqlalchemy import text

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Comprehensive health check"""
    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Check database
    try:
        db.execute(text("SELECT 1"))
        health["checks"]["database"] = "healthy"
    except Exception as e:
        health["checks"]["database"] = f"unhealthy: {e}"
        health["status"] = "unhealthy"

    # Check Redis
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        r.ping()
        health["checks"]["redis"] = "healthy"
    except Exception as e:
        health["checks"]["redis"] = f"unhealthy: {e}"
        health["status"] = "unhealthy"

    # Check Docker
    try:
        docker_host = os.getenv('DOCKER_HOST', 'unix:///var/run/docker.sock')
        client = docker.DockerClient(base_url=docker_host)
        client.ping()
        health["checks"]["docker"] = "healthy"
    except Exception as e:
        health["checks"]["docker"] = f"unhealthy: {e}"
        health["status"] = "unhealthy"

    status_code = 200 if health["status"] == "healthy" else 503
    return JSONResponse(content=health, status_code=status_code)
```

**Expected Result:** /health endpoint detects infrastructure issues
**Time:** 1 hour

**12. Documentation Updates**
```bash
# Update README with new setup instructions
# Document the critical bugs fixed
# Add troubleshooting section
```

**Time:** 1 hour

### Afternoon (4 hours)

**13. Integration Testing**
```bash
# Test complete user workflow:
# 1. Create account
# 2. Create environment with PostgreSQL + Redis
# 3. Verify health checks pass
# 4. Seed data
# 5. Query data
# 6. Stop environment
# 7. Start environment
# 8. Destroy environment
# 9. Verify cleanup

# Document any issues found
```

**Time:** 3 hours

**14. Staging Deployment**
```bash
# Deploy to staging server
# Run smoke tests
# Monitor for 1 hour
# Document any production-specific issues
```

**Time:** 1 hour

---

## Success Criteria (End of 48 Hours)

### Must Have (Blockers Fixed)
- [x] Alembic migrations working
- [x] Docker socket proxy integrated
- [x] OCI credentials properly mounted
- [x] Container health checks operational
- [x] S3/cloud emulation endpoints work
- [x] Stripe webhook validation enhanced
- [x] Basic monitoring running

### Should Have
- [x] Comprehensive health check
- [x] Documentation updated
- [x] Staging deployment successful
- [x] Integration tests passing

### Could Have (Nice to Have)
- [ ] Grafana dashboards configured
- [ ] Alert rules defined
- [ ] Load testing script created

---

## Red Flags - Stop and Escalate If:

1. **Database migration fails on existing data**
   - Action: Do NOT proceed, restore backup, debug

2. **Docker socket proxy blocks legitimate container operations**
   - Action: Verify proxy configuration, check CONTAINERS=1 POST=1

3. **Health checks take longer than 60 seconds**
   - Action: Optimize or increase timeout

4. **Any data loss during testing**
   - Action: Full stop, investigate root cause

5. **Monitoring shows memory leaks or resource exhaustion**
   - Action: Profile application, fix leaks before proceeding

---

## Next Steps After 48 Hours

**If all green:**
- Continue with Week 1 remaining tasks (background tasks, security)
- Invite alpha testers
- Begin revenue feature development

**If any red flags:**
- Extend critical fix period by 2-3 days
- Delay alpha testing until stable
- Focus on stability over features

---

## Quick Reference

**Start everything:**
```bash
docker-compose -f docker-compose.prod.yml up -d
docker-compose -f docker-compose.monitoring.yml up -d
```

**View logs:**
```bash
docker logs -f mockfactory-api
docker logs -f mockfactory-postgres
docker logs -f mockfactory-redis
docker logs -f mockfactory-docker-proxy
```

**Run migrations:**
```bash
alembic upgrade head
```

**Check health:**
```bash
curl http://localhost:8000/health | jq
```

**Emergency stop:**
```bash
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.monitoring.yml down
```

---

**Last Updated:** February 11, 2026
**Owner:** Ryan (After Dark Systems)
**Priority:** P0 - CRITICAL
**Deadline:** February 13, 2026 EOD
