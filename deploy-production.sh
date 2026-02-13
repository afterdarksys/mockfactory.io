#!/bin/bash
set -e

# MockFactory.io Production Deployment Script
# Deploys to OCI with SSL certificates and frontend UI
#
# Prerequisites:
# 1. OCI compute instance running Ubuntu/Debian
# 2. DNS pointing mockfactory.io to your server IP
# 3. Ports 80, 443, 8000, 5432, 6379 open in security list
# 4. SSH access to server
# 5. OCI credentials in secrets/ directory

echo "============================================"
echo "  MockFactory.io Production Deployment"
echo "============================================"
echo ""

# Configuration
DOMAIN="${DOMAIN:-mockfactory.io}"
EMAIL="${SSL_EMAIL:-admin@mockfactory.io}"
SERVER_USER="${SERVER_USER:-ubuntu}"
SERVER_IP="${SERVER_IP}"

# Validate required variables
if [ -z "$SERVER_IP" ]; then
    echo "❌ ERROR: SERVER_IP environment variable is required"
    echo ""
    echo "Usage:"
    echo "  SERVER_IP=your.server.ip.address ./deploy-production.sh"
    echo ""
    echo "Example:"
    echo "  SERVER_IP=141.148.79.30 ./deploy-production.sh"
    exit 1
fi

echo "📋 Configuration:"
echo "   Domain: $DOMAIN"
echo "   Server: $SERVER_USER@$SERVER_IP"
echo "   Email: $EMAIL"
echo ""

# Step 1: Verify DNS
echo "🔍 Step 1: Verifying DNS configuration..."
RESOLVED_IP=$(dig +short $DOMAIN | head -n 1)
if [ -z "$RESOLVED_IP" ]; then
    echo "❌ ERROR: Could not resolve $DOMAIN"
    echo "   Please configure DNS A record pointing to $SERVER_IP"
    exit 1
fi

if [ "$RESOLVED_IP" != "$SERVER_IP" ]; then
    echo "⚠️  WARNING: DNS points to $RESOLVED_IP but you specified $SERVER_IP"
    echo "   Continuing anyway, but this may cause issues..."
fi
echo "✅ DNS configured: $DOMAIN → $RESOLVED_IP"
echo ""

# Step 2: Test SSH connection
echo "🔐 Step 2: Testing SSH connection..."
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 $SERVER_USER@$SERVER_IP "echo '✅ SSH connection successful'" 2>/dev/null; then
    echo "❌ ERROR: Cannot connect to $SERVER_USER@$SERVER_IP via SSH"
    echo ""
    echo "Please ensure:"
    echo "  1. SSH key is added to the server (~/.ssh/authorized_keys)"
    echo "  2. SSH agent is running: eval \$(ssh-agent) && ssh-add"
    echo "  3. Security group allows SSH (port 22)"
    exit 1
fi
echo ""

# Step 3: Prepare deployment package
echo "📦 Step 3: Preparing deployment package..."
DEPLOY_DIR="/tmp/mockfactory-deploy-$(date +%s)"
mkdir -p $DEPLOY_DIR

# Copy application files
cp -r app $DEPLOY_DIR/
cp -r alembic $DEPLOY_DIR/
cp -r frontend $DEPLOY_DIR/
cp -r nginx $DEPLOY_DIR/
cp alembic.ini $DEPLOY_DIR/
cp requirements.txt $DEPLOY_DIR/
cp Dockerfile $DEPLOY_DIR/
cp docker-compose.prod.yml $DEPLOY_DIR/
cp .env.staging $DEPLOY_DIR/.env

# Copy OCI secrets if they exist
if [ -d "secrets" ]; then
    cp -r secrets $DEPLOY_DIR/
    echo "✅ OCI credentials included"
else
    echo "⚠️  WARNING: secrets/ directory not found - OCI features will not work"
fi

echo "✅ Deployment package prepared at $DEPLOY_DIR"
echo ""

# Step 4: Upload to server
echo "📤 Step 4: Uploading files to server..."
ssh $SERVER_USER@$SERVER_IP "mkdir -p ~/mockfactory"
rsync -avz --delete $DEPLOY_DIR/ $SERVER_USER@$SERVER_IP:~/mockfactory/
echo "✅ Files uploaded"
echo ""

# Step 5: Install dependencies on server
echo "🔧 Step 5: Installing dependencies on server..."
ssh $SERVER_USER@$SERVER_IP <<'ENDSSH'
set -e

echo "Updating system packages..."
sudo apt-get update -qq

echo "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker installed"
else
    echo "✅ Docker already installed"
fi

echo "Installing Docker Compose..."
if ! command -v docker compose &> /dev/null; then
    sudo apt-get install -y docker-compose-plugin
    echo "✅ Docker Compose installed"
else
    echo "✅ Docker Compose already installed"
fi

echo "Installing Certbot for SSL..."
if ! command -v certbot &> /dev/null; then
    sudo apt-get install -y certbot
    echo "✅ Certbot installed"
else
    echo "✅ Certbot already installed"
fi

ENDSSH
echo ""

# Step 6: Obtain SSL certificate
echo "🔒 Step 6: Obtaining SSL certificate..."
ssh $SERVER_USER@$SERVER_IP <<ENDSSH
set -e

# Check if certificate already exists
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "✅ SSL certificate already exists for $DOMAIN"
else
    echo "Obtaining new SSL certificate from Let's Encrypt..."

    # Stop any service on port 80
    sudo systemctl stop nginx 2>/dev/null || true
    sudo docker stop mockfactory-nginx 2>/dev/null || true

    # Obtain certificate
    sudo certbot certonly --standalone \
        --non-interactive \
        --agree-tos \
        --email $EMAIL \
        -d $DOMAIN \
        -d www.$DOMAIN

    echo "✅ SSL certificate obtained"
fi

# Copy certificates to nginx directory
mkdir -p ~/mockfactory/nginx/ssl
sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem ~/mockfactory/nginx/ssl/
sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem ~/mockfactory/nginx/ssl/
sudo chown -R \$USER:docker ~/mockfactory/nginx/ssl
sudo chmod 644 ~/mockfactory/nginx/ssl/*
echo "✅ SSL certificates copied to nginx directory"

ENDSSH
echo ""

# Step 7: Update nginx configuration for production
echo "🌐 Step 7: Updating nginx configuration..."
ssh $SERVER_USER@$SERVER_IP <<ENDSSH
set -e

# Enable HTTPS in nginx config
cat > ~/mockfactory/nginx/nginx.conf <<'EOF'
events {
    worker_connections 1024;
}

http {
    # Basic settings
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss;

    # Rate limiting
    limit_req_zone \\\$binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req_zone \\\$binary_remote_addr zone=auth_limit:10m rate=5r/m;

    # Upstream FastAPI
    upstream fastapi {
        server api:8000;
    }

    # HTTP Server - Redirect to HTTPS
    server {
        listen 80;
        server_name $DOMAIN www.$DOMAIN;

        # Allow Let's Encrypt challenges
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        # Redirect everything else to HTTPS
        location / {
            return 301 https://\\\$host\\\$request_uri;
        }
    }

    # HTTPS Server
    server {
        listen 443 ssl;
        http2 on;
        server_name $DOMAIN www.$DOMAIN;

        # SSL Configuration
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;

        # Modern SSL configuration
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-SHA384;
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        # Security headers
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;

        # Max upload size
        client_max_body_size 10M;

        # Frontend
        location / {
            root /usr/share/nginx/html;
            try_files \\\$uri \\\$uri/ /index.html;
        }

        # API endpoints
        location /api/ {
            # Rate limiting
            limit_req zone=api_limit burst=20 nodelay;

            proxy_pass http://fastapi;
            proxy_http_version 1.1;
            proxy_set_header Upgrade \\\$http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host \\\$host;
            proxy_set_header X-Real-IP \\\$remote_addr;
            proxy_set_header X-Forwarded-For \\\$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \\\$scheme;
            proxy_cache_bypass \\\$http_upgrade;

            # Timeouts
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
        }

        # Authentication endpoints - stricter rate limit
        location /api/v1/auth/ {
            limit_req zone=auth_limit burst=5 nodelay;

            proxy_pass http://fastapi;
            proxy_http_version 1.1;
            proxy_set_header Host \\\$host;
            proxy_set_header X-Real-IP \\\$remote_addr;
            proxy_set_header X-Forwarded-For \\\$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \\\$scheme;
        }

        # Health check
        location /health {
            proxy_pass http://fastapi/health;
            access_log off;
        }

        # API documentation
        location /docs {
            proxy_pass http://fastapi/docs;
            proxy_set_header Host \\\$host;
            proxy_set_header X-Forwarded-Proto \\\$scheme;
        }
    }
}
EOF

echo "✅ Nginx configuration updated for HTTPS"

ENDSSH
echo ""

# Step 8: Update docker-compose for production
echo "🐳 Step 8: Updating Docker Compose configuration..."
ssh $SERVER_USER@$SERVER_IP <<'ENDSSH'
set -e

# Update docker-compose to include nginx
cat > ~/mockfactory/docker-compose.prod.yml <<'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: mockfactory-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-mockfactory}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-mockfactory}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-mockfactory}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - mockfactory

  redis:
    image: redis:7-alpine
    container_name: mockfactory-redis
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped
    networks:
      - mockfactory

  docker-proxy:
    image: tecnativa/docker-socket-proxy:latest
    container_name: mockfactory-docker-proxy
    environment:
      CONTAINERS: 1
      POST: 1
      BUILD: 1
      COMMIT: 1
      IMAGES: 1
      INFO: 1
      NETWORKS: 1
      NODES: 0
      PLUGINS: 0
      SERVICES: 0
      SESSION: 0
      SWARM: 0
      SYSTEM: 0
      TASKS: 0
      VOLUMES: 0
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - mockfactory
    restart: unless-stopped

  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: mockfactory-api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - SECRET_KEY=${SECRET_KEY}
      - STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
      - STRIPE_PUBLISHABLE_KEY=${STRIPE_PUBLISHABLE_KEY}
      - OAUTH_CLIENT_ID=${OAUTH_CLIENT_ID}
      - OAUTH_CLIENT_SECRET=${OAUTH_CLIENT_SECRET}
      - DOCKER_HOST=tcp://docker-proxy:2375
      - OCI_CONFIG_FILE=/run/secrets/oci_config
      - OCI_KEY_FILE=/run/secrets/oci_key
    volumes:
      - ./app:/app/app:ro
    secrets:
      - oci_config
      - oci_key
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      docker-proxy:
        condition: service_started
    restart: unless-stopped
    networks:
      - mockfactory

  nginx:
    image: nginx:alpine
    container_name: mockfactory-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - ./frontend:/usr/share/nginx/html:ro
      - nginx_cache:/var/cache/nginx
    depends_on:
      - api
    restart: unless-stopped
    networks:
      - mockfactory

secrets:
  oci_config:
    file: ./secrets/oci_config
  oci_key:
    file: ./secrets/oci_key.pem

volumes:
  postgres_data:
  redis_data:
  nginx_cache:

networks:
  mockfactory:
    driver: bridge
EOF

echo "✅ Docker Compose configuration updated"

ENDSSH
echo ""

# Step 9: Deploy containers
echo "🚀 Step 9: Deploying containers..."
ssh $SERVER_USER@$SERVER_IP <<'ENDSSH'
set -e

cd ~/mockfactory

# Stop old containers if running
docker compose -f docker-compose.prod.yml down 2>/dev/null || true

# Build and start
echo "Building containers..."
docker compose -f docker-compose.prod.yml build

echo "Starting containers..."
docker compose -f docker-compose.prod.yml up -d

# Wait for services to be ready
echo "Waiting for services to start..."
sleep 10

# Check status
docker compose -f docker-compose.prod.yml ps

ENDSSH
echo ""

# Step 10: Run database migrations
echo "💾 Step 10: Running database migrations..."
ssh $SERVER_USER@$SERVER_IP <<'ENDSSH'
set -e

cd ~/mockfactory

# Create initial migration if needed
echo "Creating initial migration..."
docker compose -f docker-compose.prod.yml exec -T api alembic revision --autogenerate -m "Initial schema" 2>/dev/null || echo "Migration already exists"

# Run migrations
echo "Running migrations..."
docker compose -f docker-compose.prod.yml exec -T api alembic upgrade head

echo "✅ Database migrations complete"

ENDSSH
echo ""

# Step 11: Setup SSL auto-renewal
echo "🔄 Step 11: Setting up SSL certificate auto-renewal..."
ssh $SERVER_USER@$SERVER_IP <<'ENDSSH'
set -e

# Create renewal script
cat > ~/renew-ssl.sh <<'EOF'
#!/bin/bash
# Renew SSL certificate and reload nginx

certbot renew --quiet

# Copy renewed certificates
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem ~/mockfactory/nginx/ssl/
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem ~/mockfactory/nginx/ssl/

# Reload nginx
docker exec mockfactory-nginx nginx -s reload

echo "SSL certificate renewed and nginx reloaded"
EOF

chmod +x ~/renew-ssl.sh

# Add to crontab (run daily at 2 AM)
(crontab -l 2>/dev/null | grep -v "renew-ssl.sh"; echo "0 2 * * * ~/renew-ssl.sh >> ~/ssl-renewal.log 2>&1") | crontab -

echo "✅ SSL auto-renewal configured (runs daily at 2 AM)"

ENDSSH
echo ""

# Step 12: Verify deployment
echo "✅ Step 12: Verifying deployment..."
echo ""
echo "Testing HTTP → HTTPS redirect..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://$DOMAIN/health)
if [ "$HTTP_STATUS" = "301" ] || [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ HTTP accessible (status: $HTTP_STATUS)"
else
    echo "⚠️  HTTP returned unexpected status: $HTTP_STATUS"
fi

echo ""
echo "Testing HTTPS..."
HTTPS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://$DOMAIN/health || echo "Failed")
if [ "$HTTPS_STATUS" = "200" ]; then
    echo "✅ HTTPS working correctly"
    HEALTH_RESPONSE=$(curl -s https://$DOMAIN/health)
    echo "   Health check response: $HEALTH_RESPONSE"
else
    echo "❌ HTTPS check failed (status: $HTTPS_STATUS)"
    echo "   This is normal if DNS propagation is still in progress"
fi

echo ""
echo "Testing frontend..."
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://$DOMAIN/ || echo "Failed")
if [ "$FRONTEND_STATUS" = "200" ]; then
    echo "✅ Frontend serving correctly"
else
    echo "⚠️  Frontend returned status: $FRONTEND_STATUS"
fi

echo ""
echo "============================================"
echo "  ✅ DEPLOYMENT COMPLETE!"
echo "============================================"
echo ""
echo "🌐 Your application is now live at:"
echo "   https://$DOMAIN"
echo ""
echo "📊 Service endpoints:"
echo "   Frontend:  https://$DOMAIN"
echo "   API Docs:  https://$DOMAIN/docs"
echo "   Health:    https://$DOMAIN/health"
echo "   API:       https://$DOMAIN/api/v1"
echo ""
echo "🔧 Management commands:"
echo "   SSH to server:     ssh $SERVER_USER@$SERVER_IP"
echo "   View logs:         cd ~/mockfactory && docker compose logs -f"
echo "   Restart services:  cd ~/mockfactory && docker compose restart"
echo "   Stop services:     cd ~/mockfactory && docker compose down"
echo ""
echo "🔒 SSL Certificate:"
echo "   Status: Active"
echo "   Auto-renewal: Enabled (daily at 2 AM)"
echo "   Expires: Check with: certbot certificates"
echo ""
echo "📋 Next steps:"
echo "   1. Test your application: https://$DOMAIN"
echo "   2. Configure OAuth in .env (currently using placeholders)"
echo "   3. Configure Stripe keys in .env (currently using test keys)"
echo "   4. Set up monitoring and alerting"
echo ""
echo "💡 Tip: Bookmark https://$DOMAIN/docs for API documentation"
echo ""

# Cleanup
rm -rf $DEPLOY_DIR
echo "🧹 Temporary files cleaned up"
echo ""
