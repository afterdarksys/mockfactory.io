# MockFactory.io Production Deployment Guide

**Status:** Ready to deploy with SSL and full UI

## Quick Start

Deploy to your OCI server with one command:

```bash
SERVER_IP=your.server.ip ./deploy-production.sh
```

The script will automatically:
- ✅ Install Docker and dependencies
- ✅ Obtain Let's Encrypt SSL certificate
- ✅ Configure nginx with HTTPS
- ✅ Deploy frontend UI
- ✅ Deploy FastAPI backend
- ✅ Setup PostgreSQL and Redis
- ✅ Run database migrations
- ✅ Configure SSL auto-renewal
- ✅ Setup HTTP → HTTPS redirect

## Prerequisites

### 1. OCI Compute Instance
- Ubuntu 20.04+ or Debian 11+
- Minimum: 2 vCPU, 4GB RAM
- Ports open in security list:
  - 22 (SSH)
  - 80 (HTTP)
  - 443 (HTTPS)
  - 8000 (API - optional, for direct access)

### 2. DNS Configuration
Your DNS A record must point to your server:
```
mockfactory.io      A    your.server.ip
www.mockfactory.io  A    your.server.ip
```

Verify DNS:
```bash
dig +short mockfactory.io
# Should return your server IP
```

### 3. SSH Access
Ensure you can SSH to your server without password:
```bash
ssh ubuntu@your.server.ip
```

If this doesn't work, add your SSH key:
```bash
ssh-copy-id ubuntu@your.server.ip
```

### 4. OCI Credentials (Optional)
For S3 emulation features, ensure you have:
```bash
secrets/oci_config
secrets/oci_key.pem
```

If these don't exist, S3 features won't work but the platform will still deploy.

## Deployment Steps

### 1. Get Your Server IP

Find your OCI compute instance IP:

```bash
# Using OCI CLI
oci compute instance list --compartment-id <your-compartment> \
  --query "data[?contains(\"display-name\",'mockfactory')].{Name:\"display-name\", IP:\"public-ip\"}" \
  --output table

# Or check OCI Console
# Compute → Instances → your-instance → Public IP
```

### 2. Run Deployment

```bash
# From your local machine
cd /Users/ryan/development/mockfactory.io

# Deploy with your server IP
SERVER_IP=141.148.79.30 ./deploy-production.sh
```

**Optional environment variables:**
```bash
SERVER_IP=141.148.79.30 \
  SERVER_USER=ubuntu \
  DOMAIN=mockfactory.io \
  SSL_EMAIL=admin@mockfactory.io \
  ./deploy-production.sh
```

### 3. Watch the Deployment

The script will:
1. Verify DNS configuration
2. Test SSH connection
3. Upload application files
4. Install Docker and Certbot
5. Obtain SSL certificate from Let's Encrypt
6. Build and start containers
7. Run database migrations
8. Setup SSL auto-renewal
9. Verify deployment

Total time: ~10-15 minutes

### 4. Test Your Deployment

After deployment completes, test:

```bash
# Test HTTP redirect
curl -I http://mockfactory.io
# Should return: 301 Moved Permanently

# Test HTTPS
curl -I https://mockfactory.io
# Should return: 200 OK

# Test API health
curl https://mockfactory.io/health
# Should return: {"status":"healthy"}

# Test frontend
open https://mockfactory.io
# Should show beautiful UI
```

## What Gets Deployed

### Frontend
- **URL:** https://mockfactory.io
- **Location:** `/usr/share/nginx/html`
- **Files:** HTML, CSS, JavaScript (Tailwind CSS)
- **Features:**
  - Dark/light theme toggle
  - Service plans and pricing
  - Responsive design
  - Direct links to API docs

### Backend API
- **URL:** https://mockfactory.io/api/v1
- **Docs:** https://mockfactory.io/docs
- **Health:** https://mockfactory.io/health
- **Container:** mockfactory-api
- **Features:**
  - FastAPI with automatic OpenAPI docs
  - Environment provisioning
  - Cloud service emulation
  - Authentication (OAuth ready)
  - Stripe integration (ready)

### Infrastructure
- **PostgreSQL 15:** Port 5432 (internal)
- **Redis 7:** Port 6379 (internal)
- **Nginx:** Ports 80 (redirect), 443 (HTTPS)
- **Docker Socket Proxy:** Security layer

### SSL/TLS
- **Provider:** Let's Encrypt (free)
- **Protocols:** TLS 1.2, TLS 1.3
- **Auto-renewal:** Daily cron job
- **HSTS:** Enabled with 1-year max-age
- **Certificate location:** `/etc/letsencrypt/live/mockfactory.io/`

## Post-Deployment Configuration

### 1. Configure OAuth (Authentik)

SSH to your server and update environment:
```bash
ssh ubuntu@your.server.ip
cd ~/mockfactory
nano .env
```

Update these values:
```bash
OAUTH_CLIENT_ID=your_real_client_id
OAUTH_CLIENT_SECRET=your_real_client_secret
OAUTH_AUTHORIZE_URL=https://auth.mockfactory.io/application/o/authorize/
OAUTH_TOKEN_URL=https://auth.mockfactory.io/application/o/token/
OAUTH_USERINFO_URL=https://auth.mockfactory.io/application/o/userinfo/
```

Restart API:
```bash
docker compose -f docker-compose.prod.yml restart api
```

### 2. Configure Stripe

Update Stripe keys in `.env`:
```bash
STRIPE_SECRET_KEY=sk_live_your_real_key
STRIPE_PUBLISHABLE_KEY=pk_live_your_real_key
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret
```

Restart API:
```bash
docker compose -f docker-compose.prod.yml restart api
```

### 3. Monitor Logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Just API
docker compose -f docker-compose.prod.yml logs -f api

# Just nginx
docker compose -f docker-compose.prod.yml logs -f nginx
```

## Management Commands

### SSH to Server
```bash
ssh ubuntu@your.server.ip
cd ~/mockfactory
```

### View Container Status
```bash
docker compose -f docker-compose.prod.yml ps
```

### Restart Services
```bash
# Restart all
docker compose -f docker-compose.prod.yml restart

# Restart specific service
docker compose -f docker-compose.prod.yml restart api
docker compose -f docker-compose.prod.yml restart nginx
```

### Stop Services
```bash
docker compose -f docker-compose.prod.yml down
```

### Start Services
```bash
docker compose -f docker-compose.prod.yml up -d
```

### Rebuild After Code Changes
```bash
# Upload new code
rsync -avz ~/local/path/ ubuntu@your.server.ip:~/mockfactory/

# Rebuild and restart
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml up -d api
```

### View Database
```bash
docker compose -f docker-compose.prod.yml exec postgres psql -U mockfactory
```

### Run Migrations
```bash
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

### Check SSL Certificate
```bash
sudo certbot certificates
```

### Manual SSL Renewal
```bash
~/renew-ssl.sh
```

## Troubleshooting

### SSL Certificate Failed to Obtain
```bash
# Check DNS
dig +short mockfactory.io

# Check if port 80 is accessible
curl -I http://mockfactory.io

# Try manual certbot
sudo certbot certonly --standalone -d mockfactory.io -d www.mockfactory.io
```

### Container Won't Start
```bash
# Check logs
docker compose -f docker-compose.prod.yml logs api

# Check environment variables
docker compose -f docker-compose.prod.yml config

# Restart Docker
sudo systemctl restart docker
```

### Database Connection Issues
```bash
# Check postgres is running
docker compose -f docker-compose.prod.yml ps postgres

# Check database connectivity
docker compose -f docker-compose.prod.yml exec api python -c "from app.core.database import engine; print(engine.connect())"
```

### Nginx 502 Bad Gateway
```bash
# Check API is running
docker compose -f docker-compose.prod.yml ps api

# Check API logs
docker compose -f docker-compose.prod.yml logs api

# Check nginx config
docker compose -f docker-compose.prod.yml exec nginx nginx -t

# Restart nginx
docker compose -f docker-compose.prod.yml restart nginx
```

### High Memory Usage
```bash
# Check container resource usage
docker stats

# Restart specific service
docker compose -f docker-compose.prod.yml restart api
```

## Security Checklist

- [x] SSL/TLS enabled (Let's Encrypt)
- [x] HTTPS enforced (HTTP redirects to HTTPS)
- [x] HSTS header enabled
- [x] Security headers configured (XSS, CSP, etc.)
- [x] Rate limiting enabled (API: 10 req/s, Auth: 5 req/min)
- [x] Docker socket protected via proxy
- [x] Database not exposed publicly
- [x] Redis not exposed publicly
- [x] OCI credentials in Docker secrets
- [ ] Firewall configured (OCI security list)
- [ ] Regular backups configured
- [ ] Monitoring/alerting setup
- [ ] OAuth configured (currently placeholder)
- [ ] Stripe webhook endpoint secured

## Monitoring Setup (Optional)

Add Prometheus + Grafana:

```bash
# Add to docker-compose.prod.yml
prometheus:
  image: prom/prometheus
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana
  ports:
    - "3000:3000"
  volumes:
    - grafana_data:/var/lib/grafana
```

## Backup Strategy

### Database Backups
```bash
# Create backup script
cat > ~/backup-db.sh <<'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker compose -f ~/mockfactory/docker-compose.prod.yml exec -T postgres \
  pg_dump -U mockfactory mockfactory | gzip > ~/backups/db_$DATE.sql.gz
# Keep only last 7 days
find ~/backups/ -name "db_*.sql.gz" -mtime +7 -delete
EOF

chmod +x ~/backup-db.sh

# Add to crontab (daily at 3 AM)
(crontab -l; echo "0 3 * * * ~/backup-db.sh") | crontab -
```

### Upload Backups to OCI Object Storage
```bash
# Install OCI CLI on server
bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)"

# Upload backups
oci os object put --bucket-name mockfactory-backups \
  --file ~/backups/db_$(date +%Y%m%d).sql.gz
```

## Performance Tuning

### Increase Worker Processes
Edit `.env`:
```bash
UVICORN_WORKERS=4  # Set to number of CPU cores
```

### PostgreSQL Tuning
Edit `docker-compose.prod.yml`:
```yaml
postgres:
  command: postgres -c shared_buffers=256MB -c max_connections=100
```

### Redis Memory Limit
```yaml
redis:
  command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
```

## Scaling to Production

When you're ready for more traffic:

1. **Upgrade OCI Instance**
   - 4 vCPU, 8GB RAM minimum
   - Add load balancer for multiple instances

2. **Separate Database**
   - Use OCI Database Cloud Service
   - Or managed PostgreSQL (AWS RDS, etc.)

3. **Add Redis Cluster**
   - Use OCI Cache service
   - Or managed Redis (AWS ElastiCache, etc.)

4. **Use OCI Load Balancer**
   - SSL termination at load balancer
   - Multiple API instances
   - Health checks

5. **Add Monitoring**
   - DataDog, New Relic, or Prometheus
   - Uptime monitoring
   - Error tracking (Sentry)

## Cost Estimate

**Current setup (OCI):**
- Compute Instance (2 OCPU, 8GB RAM): ~$50/month
- Block Storage (100GB): ~$5/month
- Bandwidth (1TB): Included
- SSL Certificate: Free (Let's Encrypt)
- **Total: ~$55/month**

**With OCI Always Free tier:**
- Can run on free tier instance (1/8 OCPU, 1GB RAM)
- **Total: $0/month** (limited resources)

## Support

- **Documentation:** https://mockfactory.io/docs
- **GitHub Issues:** https://github.com/mockfactory/issues
- **Email:** support@mockfactory.io

## Success!

Your MockFactory.io platform is now:
- ✅ Live at https://mockfactory.io
- ✅ Secure with SSL/TLS
- ✅ Serving beautiful frontend UI
- ✅ Running FastAPI backend
- ✅ Auto-renewing SSL certificates
- ✅ Monitoring health
- ✅ Ready for users

**Next:** Configure OAuth and Stripe, then start inviting users!
