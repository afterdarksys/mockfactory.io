# 🚀 Deploy MockFactory.io Staging - Quick Start

**Status:** ✅ READY TO DEPLOY
**Time Required:** 5 minutes
**Difficulty:** Easy (one command)

---

## Deploy in 3 Steps

### Step 1: Start Docker
```bash
open -a Docker
```
**Wait:** Docker icon appears in menu bar (30 seconds)

### Step 2: Verify Docker is Running
```bash
docker ps
```
**Expected:** Empty list or running containers (no errors)

### Step 3: Deploy
```bash
cd /Users/ryan/development/mockfactory.io
./deploy-staging.sh
```
**Duration:** 2-5 minutes (automated)

---

## What Happens During Deployment

The script will:
1. ✅ Check prerequisites (Docker, files, secrets)
2. ✅ Start PostgreSQL and Redis
3. ✅ Create database migration (if needed)
4. ✅ Apply migrations (create tables)
5. ✅ Start Docker socket proxy
6. ✅ Build and start API container
7. ✅ Verify deployment health
8. ✅ Display success message

**You don't need to do anything - it's fully automated.**

---

## Verify Deployment

### Quick Health Check
```bash
curl http://localhost:8000/health
```
**Expected:** `{"status":"healthy"}`

### View API Documentation
```bash
open http://localhost:8000/docs
```
**Expected:** FastAPI Swagger UI opens in browser

---

## Test Basic Functionality

### 1. Register a User
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@mockfactory.io",
    "password": "TestPass123!",
    "full_name": "Test User"
  }'
```
**Save the `access_token` from the response**

### 2. Create a Test Environment
```bash
# Replace <YOUR_TOKEN> with the access_token from step 1
curl -X POST http://localhost:8000/api/v1/environments \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My First Redis",
    "services": {
      "redis": {
        "version": "7"
      }
    }
  }'
```

**Verify:**
- ✅ Status is "running"
- ✅ Password is masked (shows `:*****@` not actual password)
- ✅ Container created: `docker ps | grep "env_"`

---

## If Something Goes Wrong

### Problem: Docker won't start
```bash
# Restart Docker Desktop
killall Docker && open -a Docker
# Wait 30 seconds
docker ps
```

### Problem: API container exits
```bash
# View logs
docker compose -f docker-compose.prod.yml logs api

# Restart API
docker compose -f docker-compose.prod.yml restart api
```

### Problem: Can't connect to database
```bash
# Restart database
docker compose -f docker-compose.prod.yml restart postgres
# Wait 10 seconds
docker compose -f docker-compose.prod.yml restart api
```

**Need more help?** See `STAGING_DEPLOYMENT_RUNBOOK.md` (comprehensive troubleshooting)

---

## What You Get After Deployment

### Running Services
- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health
- **PostgreSQL:** localhost:5432
- **Redis:** localhost:6379

### Features Ready to Use
- ✅ User authentication (email/password + OAuth)
- ✅ Environment provisioning (Redis, PostgreSQL, S3)
- ✅ OCI integration (S3 emulation with OCI backend)
- ✅ Auto-shutdown (prevents runaway costs)
- ✅ Rate limiting (prevents abuse)
- ✅ Background tasks (billing, cleanup)

---

## Next Steps After Deployment

### Immediate (Today)
1. ✅ Run smoke tests (see above)
2. 🔧 Setup uptime monitoring
   - UptimeRobot.com (free tier)
   - Monitor: http://your-server:8000/health
3. 🔧 Create user onboarding docs

### This Week
1. 🔧 Invite 10-50 alpha testers
2. 🔧 Monitor logs: `docker compose logs -f api`
3. 🔧 Collect feedback (Google Form/Typeform)

### Week 2-3
1. 🔧 Fix bugs reported by testers
2. 🔧 Add Prometheus + Grafana monitoring
3. 🔧 Performance optimization

---

## Important Notes

### Security
- ✅ All critical bugs fixed (see `docs/CRITICAL_BUGS_FIXED.md`)
- ✅ Docker socket protected via security proxy
- ✅ Passwords masked in API responses
- ✅ Secrets in `/run/secrets/` not environment variables

### Cost
- **Staging:** $4-66/month (very cost-effective)
- **Compute:** $0-50 (existing host)
- **OCI Storage:** ~$4 (100 GB)

### Capacity
- **Current:** 10-50 users (perfect for staging)
- **With PgBouncer:** 100-500 users
- **With Kubernetes:** 1,000+ users

---

## Documentation

Comprehensive guides available:

| File | Purpose | Words |
|------|---------|-------|
| `STAGING_DEPLOYMENT_RUNBOOK.md` | Complete guide | 10,000+ |
| `docs/ARCHITECTURE_ASSESSMENT.md` | Architecture analysis | 8,000+ |
| `docs/CRITICAL_BUGS_FIXED.md` | Security fixes | Complete |

**Quick reference:** This file
**Full details:** Runbook
**Architecture:** Assessment

---

## Success Checklist

After deployment, verify:
- [ ] `curl http://localhost:8000/health` returns `{"status":"healthy"}`
- [ ] API docs open in browser
- [ ] Can register a user
- [ ] Can create an environment
- [ ] Docker container created for environment
- [ ] Password masked in API response
- [ ] No errors in logs

**All green?** You're ready for alpha testers! 🎉

---

## Stop/Start/Restart

### Stop All Services
```bash
docker compose -f docker-compose.prod.yml down
```
**Note:** Data is preserved in Docker volumes

### Start Services
```bash
docker compose -f docker-compose.prod.yml up -d
```

### Restart API Only
```bash
docker compose -f docker-compose.prod.yml restart api
```

### View Logs
```bash
docker compose -f docker-compose.prod.yml logs -f api
```

---

## Ready? Let's Deploy!

```bash
# 1. Start Docker
open -a Docker

# 2. Deploy
cd /Users/ryan/development/mockfactory.io
./deploy-staging.sh

# 3. Verify
curl http://localhost:8000/health
```

**That's it!** Your staging environment will be live in 5 minutes.

---

**Questions?** See `STAGING_DEPLOYMENT_RUNBOOK.md` for detailed guidance.

**Issues?** Check troubleshooting section above or runbook.

**Ready for production?** See `docs/ARCHITECTURE_ASSESSMENT.md` for roadmap.

---

*Generated February 11, 2026 - MockFactory.io Enterprise Deployment*
