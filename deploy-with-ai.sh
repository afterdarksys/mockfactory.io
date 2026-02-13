#!/bin/bash
set -e

# MockFactory.io Deployment with AI Assistant Feature
# This script deploys the full stack including the new AI assistant

echo "================================================"
echo "  MockFactory.io Deployment (with AI Assistant)"
echo "================================================"
echo ""

# Configuration
DOMAIN="${DOMAIN:-mockfactory.io}"
EMAIL="${SSL_EMAIL:-admin@mockfactory.io}"
SERVER_USER="${SERVER_USER:-ubuntu}"
SERVER_IP="${SERVER_IP}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}$1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Validate required variables
if [ -z "$SERVER_IP" ]; then
    print_error "SERVER_IP environment variable is required"
    echo ""
    echo "Usage:"
    echo "  SERVER_IP=your.server.ip ./deploy-with-ai.sh"
    echo ""
    echo "Example:"
    echo "  SERVER_IP=141.148.79.30 ./deploy-with-ai.sh"
    exit 1
fi

# Check for Anthropic API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    print_warning "ANTHROPIC_API_KEY not set - AI assistant will not work"
    echo "To enable AI features, get a key from https://console.anthropic.com/"
    read -p "Continue without AI? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

print_step "📋 Configuration:"
echo "   Domain: $DOMAIN"
echo "   Server: $SERVER_USER@$SERVER_IP"
echo "   Email: $EMAIL"
echo "   AI Enabled: $([ -n "$ANTHROPIC_API_KEY" ] && echo "Yes" || echo "No")"
echo ""

# Step 1: Create deployment package
print_step "📦 Creating deployment package..."
DEPLOY_DIR="/tmp/mockfactory-ai-deploy-$(date +%s)"
mkdir -p $DEPLOY_DIR

# Copy all files
cp -r app $DEPLOY_DIR/
cp -r alembic $DEPLOY_DIR/
cp -r frontend $DEPLOY_DIR/
cp -r nginx $DEPLOY_DIR/
cp -r scripts $DEPLOY_DIR/
cp alembic.ini $DEPLOY_DIR/
cp requirements.txt $DEPLOY_DIR/
cp Dockerfile $DEPLOY_DIR/
cp docker-compose.prod.yml $DEPLOY_DIR/
cp .env.staging $DEPLOY_DIR/.env

# Add AI-specific env vars if key exists
if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "" >> $DEPLOY_DIR/.env
    echo "# AI Assistant" >> $DEPLOY_DIR/.env
    echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" >> $DEPLOY_DIR/.env
    print_success "AI Assistant credentials added"
fi

# Create migration SQL
cat > $DEPLOY_DIR/migration_ai_usage.sql << 'EOF'
-- Add AI usage tracking table
CREATE TABLE IF NOT EXISTS ai_usage (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    prompt TEXT NOT NULL,
    response TEXT NOT NULL,
    model VARCHAR NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    api_cost FLOAT NOT NULL,
    user_cost FLOAT NOT NULL,
    profit FLOAT NOT NULL,
    session_id VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_ai_usage_id ON ai_usage(id);
CREATE INDEX IF NOT EXISTS ix_ai_usage_user_id ON ai_usage(user_id);
CREATE INDEX IF NOT EXISTS ix_ai_usage_created_at ON ai_usage(created_at);
EOF

print_success "Deployment package created at $DEPLOY_DIR"
echo ""

# Step 2: Upload to server
print_step "📤 Uploading to server..."
ssh $SERVER_USER@$SERVER_IP "mkdir -p /opt/mockfactory"
rsync -avz --progress $DEPLOY_DIR/ $SERVER_USER@$SERVER_IP:/opt/mockfactory/

print_success "Files uploaded"
echo ""

# Step 3: Deploy on server
print_step "🚀 Deploying on server..."

ssh $SERVER_USER@$SERVER_IP << 'ENDSSH'
set -e

cd /opt/mockfactory

# Install dependencies
sudo apt-get update
sudo apt-get install -y docker.io docker-compose python3-pip postgresql-client

# Stop existing containers
sudo docker-compose -f docker-compose.prod.yml down || true

# Run database migration
echo "Running database migration..."
if [ -f migration_ai_usage.sql ]; then
    export PGPASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2)
    POSTGRES_HOST=$(grep POSTGRES_HOST .env | cut -d '=' -f2 || echo "localhost")
    POSTGRES_USER=$(grep POSTGRES_USER .env | cut -d '=' -f2)
    POSTGRES_DB=$(grep POSTGRES_DB .env | cut -d '=' -f2)

    # Wait for postgres to be ready (if starting fresh)
    for i in {1..30}; do
        if psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 1" > /dev/null 2>&1; then
            break
        fi
        echo "Waiting for database..."
        sleep 2
    done

    # Run migration
    psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -f migration_ai_usage.sql
    echo "✅ Database migration complete"
fi

# Build and start containers
sudo docker-compose -f docker-compose.prod.yml build
sudo docker-compose -f docker-compose.prod.yml up -d

echo "✅ Containers started"

# Grant admin access
if [ -f scripts/grant_admin.sql ]; then
    echo "Granting admin access to rjc@afterdarksys.com..."
    export PGPASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2)
    POSTGRES_HOST=$(grep POSTGRES_HOST .env | cut -d '=' -f2 || echo "localhost")
    POSTGRES_USER=$(grep POSTGRES_USER .env | cut -d '=' -f2)
    POSTGRES_DB=$(grep POSTGRES_DB .env | cut -d '=' -f2)

    psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -f scripts/grant_admin.sql
    echo "✅ Admin access granted"
fi

# Show container status
sudo docker-compose -f docker-compose.prod.yml ps

ENDSSH

print_success "Deployment complete!"
echo ""

# Step 4: Verify deployment
print_step "🔍 Verifying deployment..."
echo ""
echo "Testing endpoints:"
echo "  https://$DOMAIN/ - Landing page"
echo "  https://$DOMAIN/app.html - Dashboard"
echo "  https://$DOMAIN/api/v1/ai/usage - AI Assistant API"
echo "  https://$DOMAIN/docs - API Documentation"
echo ""

# Test if server is responding
if curl -s -o /dev/null -w "%{http_code}" https://$DOMAIN/ | grep -q "200\|301\|302"; then
    print_success "Server is responding!"
else
    print_warning "Server might not be ready yet. Give it a minute..."
fi

echo ""
print_success "================================================"
print_success "  Deployment Complete! 🎉"
print_success "================================================"
echo ""
echo "🔗 Access your application:"
echo "   Landing: https://$DOMAIN/"
echo "   Dashboard: https://$DOMAIN/app.html"
echo "   API Docs: https://$DOMAIN/docs"
echo ""
echo "👤 Admin Account:"
echo "   Email: rjc@afterdarksys.com"
echo "   Tier: Employee (Unlimited AI access)"
echo ""
echo "💬 AI Assistant:"
if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "   Status: ✅ Enabled"
    echo "   Model: Claude 3.5 Haiku"
    echo "   Your Access: Unlimited messages"
else
    echo "   Status: ❌ Disabled (no API key)"
    echo "   To enable: Set ANTHROPIC_API_KEY and re-deploy"
fi
echo ""
echo "📊 Monitor logs:"
echo "   ssh $SERVER_USER@$SERVER_IP"
echo "   cd /opt/mockfactory"
echo "   sudo docker-compose -f docker-compose.prod.yml logs -f"
echo ""

# Cleanup
rm -rf $DEPLOY_DIR
print_success "Temporary files cleaned up"
