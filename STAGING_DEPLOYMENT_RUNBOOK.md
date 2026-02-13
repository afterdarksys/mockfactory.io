# MockFactory.io - Staging Deployment Runbook

**Version:** 1.0.0
**Date:** February 11, 2026
**Environment:** Staging (Alpha Testing)
**Expected Load:** 10-50 users
**Estimated Cost:** $4-66/month

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Deployment Steps](#deployment-steps)
3. [Post-Deployment Validation](#post-deployment-validation)
4. [Smoke Tests](#smoke-tests)
5. [Monitoring & Health Checks](#monitoring--health-checks)
6. [Rollback Procedure](#rollback-procedure)
7. [Troubleshooting Guide](#troubleshooting-guide)
8. [Common Issues & Fixes](#common-issues--fixes)

---

## Pre-Deployment Checklist

**Status:** ✅ COMPLETE (Automated Setup)

### 1. OCI Credentials Configuration ✅

```bash
# Secrets directory created
ls -lh secrets/
# Should show:
# - oci_config (600 permissions)
# - oci_key.pem (600 permissions)
```

**Verification:**
```bash
grep "key_file=/run/secrets/oci_key" secrets/oci_config
# Should return the line - confirms Docker secrets path is correct
```

### 2. Environment Variables Configuration ✅

```bash
# Production-ready .env.staging file created with:
# - Cryptographically secure SECRET_KEY (64 chars hex)
# - Secure POSTGRES_PASSWORD (32 chars hex)
# - Staging-appropriate CORS origins
# - OCI compartment ID configured
```

**File location:** `/Users/ryan/development/mockfactory.io/.env.staging`

### 3. Database Schema Ready ⏳

```bash
# Alembic configured and ready
# Initial migration will be created during deployment
```

### 4. Docker Installation ✅

```bash
# Docker version: 29.2.0
# Docker Compose version: v5.0.2
```

---

## Deployment Steps

### Step 1: Start Docker Desktop

**ACTION REQUIRED:** Start Docker Desktop before proceeding.

```bash
# On macOS, start Docker Desktop from Applications
# Or use:
open -a Docker

# Wait for Docker to fully start (check menu bar icon)
# Verify Docker is running:
docker ps

# Should return empty list or running containers (no error)
```

### Step 2: Start Database and Redis

Start the database and cache layer first to run migrations:

```bash
cd /Users/ryan/development/mockfactory.io

# Start PostgreSQL and Redis
docker compose -f docker-compose.prod.yml --env-file .env.staging up -d postgres redis

# Wait for services to be healthy (10-30 seconds)
docker compose -f docker-compose.prod.yml ps

# Should show both containers as "healthy"
```

**Expected output:**
```
NAME                      STATUS          PORTS
mockfactory-postgres      Up (healthy)    0.0.0.0:5432->5432/tcp
mockfactory-redis         Up (healthy)    0.0.0.0:6379->6379/tcp
```

### Step 3: Create Initial Alembic Migration

**CRITICAL:** This creates the database schema migration file.

```bash
# Set DATABASE_URL for migration creation
export DATABASE_URL="postgresql://mockfactory:2f41d7917bc278bdab73f8b08a138870@localhost:5432/mockfactory"

# Create initial migration (autogenerate from models)
alembic revision --autogenerate -m "Initial schema: User, Environment, EnvironmentUsageLog, Execution, APIKey, PortAllocation, DNSRecord"

# Expected output:
# INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
# INFO  [alembic.autogenerate.compare] Detected added table 'users'
# INFO  [alembic.autogenerate.compare] Detected added table 'environments'
# ... (7 tables total)
# Generating /Users/ryan/development/mockfactory.io/alembic/versions/xxxxx_initial_schema.py
```

**Verify migration file created:**
```bash
ls -lh alembic/versions/
# Should show one .py file with timestamp
```

### Step 4: Apply Database Migrations

```bash
# Apply migrations to create all tables
alembic upgrade head

# Expected output:
# INFO  [alembic.runtime.migration] Running upgrade  -> xxxxx, Initial schema
# INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
```

**Verify tables created:**
```bash
# Connect to database and list tables
docker compose -f docker-compose.prod.yml exec postgres psql -U mockfactory -d mockfactory -c "\dt"

# Should show 7 tables:
# - users
# - environments
# - environment_usage_logs
# - executions
# - api_keys
# - port_allocations
# - dns_records
```

### Step 5: Start Docker Socket Proxy

**CRITICAL SECURITY COMPONENT:** This protects the Docker socket from direct access.

```bash
# Start docker-socket-proxy (security layer)
docker compose -f docker-compose.prod.yml --env-file .env.staging up -d docker-proxy

# Verify it's running
docker compose -f docker-compose.prod.yml ps docker-proxy

# Should show "Up" status
```

**Security validation:**
```bash
# Verify read-only socket mount
docker inspect mockfactory-docker-proxy | grep -A5 Binds

# Should show: "/var/run/docker.sock:/var/run/docker.sock:ro"
# The ":ro" is critical - means read-only
```

### Step 6: Build and Start API Container

```bash
# Build the API container
docker compose -f docker-compose.prod.yml --env-file .env.staging build api

# Start API service
docker compose -f docker-compose.prod.yml --env-file .env.staging up -d api

# Watch startup logs (Ctrl+C to exit)
docker compose -f docker-compose.prod.yml logs -f api
```

**Expected startup logs:**
```
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     MockFactory.io starting up...
INFO:     Background tasks started successfully
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Step 7: Start Nginx Reverse Proxy (Optional for local testing)

```bash
# Only start nginx if you need HTTPS/reverse proxy
# For local testing, you can access API directly on port 8000

# If you want nginx:
docker compose -f docker-compose.prod.yml --env-file .env.staging up -d nginx

# Note: SSL certificates must be in nginx/ssl/ directory
# For staging, consider using Let's Encrypt with Certbot
```

### Step 8: Verify All Services Running

```bash
# Check all containers
docker compose -f docker-compose.prod.yml ps

# Should show all services as "Up" or "Up (healthy)"
```

**Expected output:**
```
NAME                        STATUS          PORTS
mockfactory-api             Up              0.0.0.0:8000->8000/tcp
mockfactory-docker-proxy    Up
mockfactory-nginx           Up              0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
mockfactory-postgres        Up (healthy)    0.0.0.0:5432->5432/tcp
mockfactory-redis           Up (healthy)    0.0.0.0:6379->6379/tcp
```

---

## Post-Deployment Validation

### 1. Health Check Endpoint

```bash
# Test basic health endpoint
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy"}
```

### 2. API Root Endpoint

```bash
# Test API root with full feature list
curl http://localhost:8000/ | jq

# Expected response:
# {
#   "name": "MockFactory API",
#   "version": "1.0.0",
#   "description": "PostgreSQL-first testing platform with cloud emulation",
#   "docs": "/docs",
#   "features": [ ... ]
# }
```

### 3. API Documentation

```bash
# Open in browser
open http://localhost:8000/docs

# Should show FastAPI Swagger UI with all endpoints
```

### 4. Database Connectivity

```bash
# Verify API can connect to database
docker compose -f docker-compose.prod.yml logs api | grep -i "database\|postgres"

# Should NOT show connection errors
```

### 5. Redis Connectivity

```bash
# Test Redis connection
docker compose -f docker-compose.prod.yml exec redis redis-cli ping

# Expected response: PONG
```

### 6. Docker Socket Proxy Connectivity

```bash
# Verify API can talk to Docker proxy
docker compose -f docker-compose.prod.yml exec api python3 -c "
import os
import docker
docker_host = os.getenv('DOCKER_HOST', 'unix:///var/run/docker.sock')
print(f'Docker host: {docker_host}')
client = docker.DockerClient(base_url=docker_host)
print(f'Connected to Docker: {client.ping()}')
print(f'Containers: {len(client.containers.list())}')
"

# Expected output:
# Docker host: tcp://docker-proxy:2375
# Connected to Docker: True
# Containers: 5 (or however many are running)
```

---

## Smoke Tests

### Test 1: User Registration (Authentication)

```bash
# Register a new user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "staging-test@example.com",
    "password": "SecurePassword123!",
    "full_name": "Staging Tester"
  }'

# Expected response (201 Created):
# {
#   "id": "usr_xxxxx",
#   "email": "staging-test@example.com",
#   "tier": "beginner",
#   "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
#   "token_type": "bearer"
# }
```

**Save the access token for subsequent tests:**
```bash
export JWT_TOKEN="<access_token_from_response>"
```

### Test 2: Environment Provisioning (Core Feature)

```bash
# Create a Redis environment
curl -X POST http://localhost:8000/api/v1/environments \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Staging Test Redis",
    "services": {
      "redis": {
        "version": "7"
      }
    }
  }'

# Expected response (201 Created):
# {
#   "id": "env_xxxxx",
#   "name": "Staging Test Redis",
#   "status": "running",
#   "endpoints": {
#     "redis": "redis://:*****@localhost:30001"
#   },
#   "services": { ... },
#   "created_at": "2026-02-11T...",
#   "started_at": "2026-02-11T..."
# }
```

**CRITICAL VALIDATION:**
- ✅ Password is masked in endpoints (shows `:*****@` not actual password)
- ✅ Container is actually running (check with `docker ps`)
- ✅ Port is allocated in range 30000-40000
- ✅ Status is "running" not "error"

**Verify container created:**
```bash
docker ps | grep "env_"
# Should show a Redis container with name matching environment ID
```

**Save environment ID for cleanup:**
```bash
export ENV_ID="<environment_id_from_response>"
```

### Test 3: PostgreSQL Environment with pgvector

```bash
# Create a pgvector environment (AI/ML database)
curl -X POST http://localhost:8000/api/v1/environments \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Staging Test pgvector",
    "services": {
      "postgresql_pgvector": {
        "version": "latest"
      }
    }
  }'

# Expected response: Similar to Test 2, with postgresql endpoint
```

**Verify pgvector extension:**
```bash
# Get the port from the response (e.g., 30002)
# Get the password from database (for testing, check container env)

# Connect and test pgvector
docker exec <container_name> psql -U postgres -d testdb -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT * FROM pg_extension WHERE extname='vector';"

# Should show vector extension is available
```

### Test 4: OCI S3 Emulation

```bash
# Create an S3 environment
curl -X POST http://localhost:8000/api/v1/environments \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Staging Test S3",
    "services": {
      "aws_s3": {
        "region": "us-east-1"
      }
    }
  }'

# Expected response:
# {
#   "id": "env_xxxxx",
#   "endpoints": {
#     "aws_s3": "https://s3.env_xxxxx.mockfactory.io"
#   },
#   "oci_resources": {
#     "aws_s3": "mockfactory-env_xxxxx-aws_s3"
#   }
# }
```

**Verify OCI bucket created:**
```bash
# Check OCI CLI can access bucket
docker compose -f docker-compose.prod.yml exec api bash -c "
oci os bucket get --name mockfactory-$ENV_ID-aws_s3
"

# Should return bucket details (name, namespace, etc.)
# OR check in OCI Console: Object Storage > Buckets
```

### Test 5: List User Environments

```bash
# List all environments for the user
curl http://localhost:8000/api/v1/environments \
  -H "Authorization: Bearer $JWT_TOKEN"

# Expected response:
# [
#   { "id": "env_xxx1", "name": "Staging Test Redis", ... },
#   { "id": "env_xxx2", "name": "Staging Test pgvector", ... },
#   { "id": "env_xxx3", "name": "Staging Test S3", ... }
# ]
```

### Test 6: Environment Lifecycle (Stop/Start)

```bash
# Stop environment
curl -X POST http://localhost:8000/api/v1/environments/$ENV_ID/stop \
  -H "Authorization: Bearer $JWT_TOKEN"

# Expected response:
# { "status": "stopped", "message": "Environment stopped successfully" }

# Verify container stopped
docker ps | grep $ENV_ID
# Should not show container (or show as "Exited")

# Start environment again
curl -X POST http://localhost:8000/api/v1/environments/$ENV_ID/start \
  -H "Authorization: Bearer $JWT_TOKEN"

# Expected response:
# { "status": "running", "message": "Environment started successfully" }
```

### Test 7: Environment Cleanup (Destroy)

```bash
# Destroy environment (cleanup)
curl -X DELETE http://localhost:8000/api/v1/environments/$ENV_ID \
  -H "Authorization: Bearer $JWT_TOKEN"

# Expected response:
# { "message": "Environment destroyed successfully" }

# Verify container removed
docker ps -a | grep $ENV_ID
# Should not show container

# Verify port deallocated (check database)
docker compose -f docker-compose.prod.yml exec postgres psql -U mockfactory -d mockfactory -c "
SELECT port, service_name, is_active
FROM port_allocations
WHERE environment_id='$ENV_ID';
"

# Should show is_active=false
```

### Test 8: Rate Limiting

```bash
# Test rate limiting by making rapid requests
for i in {1..15}; do
  curl -w "\nStatus: %{http_code}\n" http://localhost:8000/health
done

# First ~10 should return 200
# Later requests may return 429 (Too Many Requests) if rate limit hit
```

### Test 9: Password Masking Verification

```bash
# Get environment details and verify password masking
curl http://localhost:8000/api/v1/environments \
  -H "Authorization: Bearer $JWT_TOKEN" | jq '.[] | .endpoints'

# CRITICAL: Should see masked passwords
# ✅ "redis://:*****@localhost:30001"
# ✅ "postgresql://postgres:*****@localhost:30002/testdb"
#
# ❌ Should NEVER see actual passwords
# ❌ "redis://:actualpassword123@localhost:30001"
```

---

## Monitoring & Health Checks

### Container Health Monitoring

```bash
# Check health status of all containers
docker compose -f docker-compose.prod.yml ps

# Watch container logs in real-time
docker compose -f docker-compose.prod.yml logs -f

# Check specific service logs
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f postgres
```

### Database Health

```bash
# Check PostgreSQL connections
docker compose -f docker-compose.prod.yml exec postgres psql -U mockfactory -d mockfactory -c "
SELECT count(*) as active_connections
FROM pg_stat_activity
WHERE datname='mockfactory';
"

# Check table row counts
docker compose -f docker-compose.prod.yml exec postgres psql -U mockfactory -d mockfactory -c "
SELECT
  'users' as table_name, COUNT(*) as rows FROM users
UNION ALL
SELECT 'environments', COUNT(*) FROM environments
UNION ALL
SELECT 'port_allocations', COUNT(*) FROM port_allocations;
"
```

### Resource Usage

```bash
# Check Docker container resource usage
docker stats

# Shows real-time CPU, memory, network I/O
# Watch for:
# - API container memory usage (should be < 512 MB)
# - PostgreSQL memory usage (should be < 256 MB for staging)
# - High CPU usage (investigate if > 50% sustained)
```

### Port Allocation Status

```bash
# Check how many ports are allocated
docker compose -f docker-compose.prod.yml exec postgres psql -U mockfactory -d mockfactory -c "
SELECT
  COUNT(*) FILTER (WHERE is_active=true) as active_ports,
  COUNT(*) FILTER (WHERE is_active=false) as released_ports,
  COUNT(*) as total_allocations
FROM port_allocations;
"
```

### OCI Resource Monitoring

```bash
# List all OCI buckets created by MockFactory
docker compose -f docker-compose.prod.yml exec api bash -c "
oci os bucket list --compartment-id ocid1.compartment.oc1..aaaaaaaaqzzabys3xbxcbektqibdhzm6vtfmudya2fcuhmtzkhkow4sub3na | jq '.data[] | select(.name | startswith(\"mockfactory-\")) | .name'
"

# Check OCI storage usage
# Go to OCI Console > Object Storage > Buckets
# Look for buckets named "mockfactory-env_*"
```

### Background Tasks Monitoring

```bash
# Check if auto-shutdown task is running
docker compose -f docker-compose.prod.yml logs api | grep -i "background\|auto-shutdown\|cleanup"

# Should see:
# "Background tasks started successfully"
# "Starting auto-shutdown checker..."
```

---

## Rollback Procedure

### Emergency Rollback (Complete Shutdown)

```bash
# Stop all services immediately
docker compose -f docker-compose.prod.yml down

# This stops but preserves data volumes
# Data is NOT lost
```

### Rollback with Data Preservation

```bash
# Stop services
docker compose -f docker-compose.prod.yml down

# Restore previous .env file (if you made changes)
cp .env.staging.backup .env.staging

# Restart services
docker compose -f docker-compose.prod.yml --env-file .env.staging up -d
```

### Rollback Database Migration

```bash
# Check current migration version
alembic current

# Rollback one migration
alembic downgrade -1

# Rollback to specific version
alembic downgrade <revision_id>

# Rollback to beginning (DESTRUCTIVE - deletes all tables)
alembic downgrade base
```

### Complete Environment Reset (DESTRUCTIVE)

**WARNING:** This deletes ALL data including database contents.

```bash
# Stop all services and remove volumes
docker compose -f docker-compose.prod.yml down -v

# Remove all user-created containers (environments)
docker ps -a | grep "env_" | awk '{print $1}' | xargs docker rm -f

# Clear port allocations in database (after restart)
docker compose -f docker-compose.prod.yml up -d postgres
sleep 5
docker compose -f docker-compose.prod.yml exec postgres psql -U mockfactory -d mockfactory -c "TRUNCATE port_allocations CASCADE;"

# Restart fresh
docker compose -f docker-compose.prod.yml --env-file .env.staging up -d
```

---

## Troubleshooting Guide

### Issue: API Container Won't Start

**Symptoms:**
- Container exits immediately after starting
- Logs show database connection errors

**Diagnosis:**
```bash
# Check API logs
docker compose -f docker-compose.prod.yml logs api

# Common errors:
# - "could not connect to database"
# - "connection refused"
# - "authentication failed"
```

**Solutions:**

1. **Database not ready:**
   ```bash
   # Wait for PostgreSQL to be fully started
   docker compose -f docker-compose.prod.yml ps postgres
   # Should show "healthy" status

   # If not healthy, restart postgres
   docker compose -f docker-compose.prod.yml restart postgres
   ```

2. **Wrong credentials:**
   ```bash
   # Verify POSTGRES_PASSWORD in .env.staging matches DATABASE_URL
   grep POSTGRES_PASSWORD .env.staging
   grep DATABASE_URL .env.staging
   # Passwords must match
   ```

3. **Missing migrations:**
   ```bash
   # Apply migrations
   alembic upgrade head
   ```

### Issue: OCI Bucket Creation Fails

**Symptoms:**
- Environment creation succeeds but OCI resource is empty
- Logs show "Failed to create OCI bucket"

**Diagnosis:**
```bash
# Check API logs for OCI errors
docker compose -f docker-compose.prod.yml logs api | grep -i oci

# Test OCI CLI manually
docker compose -f docker-compose.prod.yml exec api bash
oci os ns get
```

**Solutions:**

1. **OCI credentials incorrect:**
   ```bash
   # Verify secrets are mounted
   docker compose -f docker-compose.prod.yml exec api ls -lh /run/secrets/

   # Should show oci_config and oci_key

   # Verify config content
   docker compose -f docker-compose.prod.yml exec api cat /run/secrets/oci_config
   # Should show valid OCI config with key_file=/run/secrets/oci_key
   ```

2. **OCI key file path wrong:**
   ```bash
   # Fix in secrets/oci_config
   vim secrets/oci_config
   # Change key_file to: /run/secrets/oci_key

   # Restart API
   docker compose -f docker-compose.prod.yml restart api
   ```

3. **IAM permissions insufficient:**
   ```bash
   # Verify user has bucket creation permissions in OCI Console
   # Required policies:
   # - objectstorage.buckets.create
   # - objectstorage.objects.create
   ```

### Issue: Docker Socket Proxy Connection Failed

**Symptoms:**
- Environment provisioning fails
- Error: "Cannot connect to Docker API"

**Diagnosis:**
```bash
# Check if docker-proxy is running
docker compose -f docker-compose.prod.yml ps docker-proxy

# Check API can reach proxy
docker compose -f docker-compose.prod.yml exec api ping docker-proxy -c 3
```

**Solutions:**

1. **Docker proxy not started:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d docker-proxy
   ```

2. **Wrong DOCKER_HOST:**
   ```bash
   # Verify environment variable in API container
   docker compose -f docker-compose.prod.yml exec api env | grep DOCKER_HOST
   # Should be: tcp://docker-proxy:2375
   ```

3. **Network connectivity issue:**
   ```bash
   # Restart all services
   docker compose -f docker-compose.prod.yml restart
   ```

### Issue: Port Allocation Exhaustion

**Symptoms:**
- Error: "No available ports in range 30000-40000"
- Cannot create new environments

**Diagnosis:**
```bash
# Check port allocation status
docker compose -f docker-compose.prod.yml exec postgres psql -U mockfactory -d mockfactory -c "
SELECT
  COUNT(*) FILTER (WHERE is_active=true) as active,
  COUNT(*) FILTER (WHERE is_active=false) as released
FROM port_allocations;
"
```

**Solutions:**

1. **Orphaned allocations (environments deleted but ports not released):**
   ```bash
   # Find orphaned ports
   docker compose -f docker-compose.prod.yml exec postgres psql -U mockfactory -d mockfactory -c "
   SELECT pa.port, pa.environment_id, pa.is_active
   FROM port_allocations pa
   LEFT JOIN environments e ON pa.environment_id = e.id
   WHERE pa.is_active=true AND e.id IS NULL;
   "

   # Release orphaned ports
   docker compose -f docker-compose.prod.yml exec postgres psql -U mockfactory -d mockfactory -c "
   UPDATE port_allocations
   SET is_active=false
   WHERE environment_id NOT IN (SELECT id FROM environments);
   "
   ```

2. **Legitimate exhaustion (10,000 active environments):**
   ```bash
   # Delete old/unused environments
   # Or expand port range (requires code change)
   ```

### Issue: Password Visible in API Response

**Symptoms:**
- Connection strings show actual passwords in JSON response

**This should NOT happen - Bug #5 was fixed!**

**Diagnosis:**
```bash
# Test endpoint
curl http://localhost:8000/api/v1/environments \
  -H "Authorization: Bearer $JWT_TOKEN" | jq '.[] | .endpoints'

# Should see *****
# If you see actual passwords, something is wrong
```

**Solutions:**

1. **Code not updated:**
   ```bash
   # Verify field serializer is in code
   grep -A5 "field_serializer.*endpoints" app/api/environments.py

   # Should show sanitize_endpoints function
   ```

2. **Old container image:**
   ```bash
   # Rebuild API container
   docker compose -f docker-compose.prod.yml build --no-cache api
   docker compose -f docker-compose.prod.yml up -d api
   ```

### Issue: Database Migration Conflicts

**Symptoms:**
- `alembic upgrade head` fails
- Error: "relation already exists"

**Solutions:**

1. **Manual table creation vs migrations:**
   ```bash
   # Check if tables were created by Base.metadata.create_all() (BAD)
   # vs Alembic migrations (GOOD)

   # If tables exist but no migration history:
   alembic stamp head
   # This marks current state as migrated without running migrations
   ```

2. **Migration version conflict:**
   ```bash
   # Check current version
   alembic current

   # Check available versions
   alembic history

   # Resolve by stamping to correct version
   alembic stamp <revision_id>
   ```

---

## Common Issues & Fixes

### 1. "Container name already exists"

```bash
# Remove old containers
docker rm -f mockfactory-api mockfactory-postgres mockfactory-redis mockfactory-docker-proxy mockfactory-nginx

# Restart
docker compose -f docker-compose.prod.yml --env-file .env.staging up -d
```

### 2. "Port already in use" (5432, 6379, 8000)

```bash
# Find what's using the port
lsof -i :5432  # or :6379, :8000

# Option 1: Stop the conflicting service
# Option 2: Change port in docker-compose.prod.yml
```

### 3. "Out of disk space"

```bash
# Clean up Docker images and volumes
docker system prune -a --volumes

# WARNING: This removes ALL unused Docker resources
```

### 4. API responds slowly or times out

```bash
# Check database connection pool
# Check resource usage
docker stats

# Increase container resources if needed
# (Requires docker-compose.prod.yml changes)
```

### 5. Background tasks not running

```bash
# Check logs for background task errors
docker compose -f docker-compose.prod.yml logs api | grep background

# Restart API to reinitialize
docker compose -f docker-compose.prod.yml restart api
```

---

## Quick Reference Commands

### Start staging environment
```bash
docker compose -f docker-compose.prod.yml --env-file .env.staging up -d
```

### View logs
```bash
docker compose -f docker-compose.prod.yml logs -f api
```

### Stop staging environment
```bash
docker compose -f docker-compose.prod.yml down
```

### Restart specific service
```bash
docker compose -f docker-compose.prod.yml restart api
```

### Access API container shell
```bash
docker compose -f docker-compose.prod.yml exec api bash
```

### Access PostgreSQL shell
```bash
docker compose -f docker-compose.prod.yml exec postgres psql -U mockfactory -d mockfactory
```

### Check service health
```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost:8000/health
```

### Rebuild API after code changes
```bash
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml up -d api
```

---

## Success Criteria

**Staging deployment is successful when:**

- ✅ All 5 containers are running and healthy
- ✅ Health endpoint returns `{"status":"healthy"}`
- ✅ API documentation is accessible at http://localhost:8000/docs
- ✅ User registration works
- ✅ Environment provisioning works (Redis, PostgreSQL, S3)
- ✅ Docker containers are created for environments
- ✅ OCI buckets are created for S3 emulation
- ✅ Passwords are masked in API responses (`:*****@`)
- ✅ Port allocation works (30000-40000 range)
- ✅ Environment lifecycle works (stop/start/destroy)
- ✅ No errors in container logs
- ✅ Database migrations applied successfully

**Ready for alpha testers when:**

- ✅ All smoke tests pass
- ✅ Basic monitoring is in place
- ✅ Deployment documentation is complete
- ✅ Rollback procedure is tested
- ✅ Common issues have known fixes
- ✅ At least 1 alpha tester has successfully used the platform

---

## Next Steps After Deployment

1. **Configure Authentik OAuth** (optional for staging - can use direct registration)
2. **Setup DNS** for staging.mockfactory.io
3. **Configure SSL** with Let's Encrypt
4. **Add monitoring** (uptime, basic metrics)
5. **Invite alpha testers** (10-50 users)
6. **Collect feedback** and iterate
7. **Load testing** to validate scalability assumptions
8. **Security audit** before production

---

**Questions or issues?** Contact: Ryan (Deployment Lead)

**Last updated:** February 11, 2026
**Version:** 1.0.0
**Status:** READY FOR DEPLOYMENT
