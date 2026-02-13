#!/bin/bash
set -e

# Prepare MockFactory for deployment
# Runs checks and prepares files without needing Docker locally

echo "================================================"
echo "  MockFactory.io - Deployment Preparation"
echo "================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

# Check Python dependencies
echo "🔍 Checking dependencies..."
if ! pip list | grep -q "anthropic"; then
    print_warning "anthropic package not installed"
    echo "Installing..."
    pip install anthropic==0.39.0
fi
print_success "Dependencies OK"
echo ""

# Check for Anthropic API key
echo "🔑 Checking API keys..."
if [ -z "$ANTHROPIC_API_KEY" ]; then
    if grep -q "ANTHROPIC_API_KEY" .env 2>/dev/null; then
        print_success "API key found in .env"
    else
        print_warning "ANTHROPIC_API_KEY not set"
        echo ""
        echo "To enable AI Assistant:"
        echo "1. Visit: https://console.anthropic.com/"
        echo "2. Create API key"
        echo "3. Add to .env: ANTHROPIC_API_KEY=sk-ant-xxx"
        echo ""
        read -p "Continue without AI? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
else
    print_success "API key found in environment"
fi
echo ""

# Verify all new files exist
echo "📁 Checking new files..."
REQUIRED_FILES=(
    "app/models/ai_usage.py"
    "app/api/ai_assistant.py"
    "frontend/app.html"
    "frontend/static/js/app.js"
    "frontend/static/js/claude-assistant-real.js"
    "scripts/grant_admin.py"
    "scripts/grant_admin.sql"
    "alembic/versions/add_ai_usage_table.py"
)

ALL_FOUND=true
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        print_error "$file not found"
        ALL_FOUND=false
    fi
done

if [ "$ALL_FOUND" = false ]; then
    print_error "Some files are missing!"
    exit 1
fi
print_success "All files present"
echo ""

# Check migration SQL syntax
echo "🔍 Validating migration SQL..."
if grep -q "CREATE TABLE.*ai_usage" alembic/versions/add_ai_usage_table.py; then
    print_success "Migration SQL looks good"
else
    print_error "Migration SQL might be invalid"
    exit 1
fi
echo ""

# Create standalone migration SQL file
echo "📝 Creating standalone migration..."
cat > migration_ai.sql << 'EOF'
-- MockFactory AI Usage Tracking Table
-- Run this on your production database

BEGIN;

-- Create ai_usage table
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

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_ai_usage_id ON ai_usage(id);
CREATE INDEX IF NOT EXISTS ix_ai_usage_user_id ON ai_usage(user_id);
CREATE INDEX IF NOT EXISTS ix_ai_usage_created_at ON ai_usage(created_at);

-- Grant admin access to rjc@afterdarksys.com
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE email = 'rjc@afterdarksys.com') THEN
        UPDATE users
        SET is_employee = TRUE, tier = 'employee', is_active = TRUE
        WHERE email = 'rjc@afterdarksys.com';
        RAISE NOTICE 'Admin access granted to rjc@afterdarksys.com';
    ELSE
        INSERT INTO users (email, oauth_user_id, is_active, is_employee, tier, created_at, updated_at)
        VALUES ('rjc@afterdarksys.com', 'sso_rjc', TRUE, TRUE, 'employee', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        RAISE NOTICE 'Admin user created: rjc@afterdarksys.com';
    END IF;
END $$;

COMMIT;

-- Verify
SELECT
    'ai_usage table' as object,
    COUNT(*) as row_count
FROM ai_usage
UNION ALL
SELECT
    'admin user' as object,
    CASE WHEN is_employee THEN 1 ELSE 0 END as row_count
FROM users
WHERE email = 'rjc@afterdarksys.com';

EOF

print_success "Standalone migration created: migration_ai.sql"
echo ""

# Create deployment checklist
echo "📋 Creating deployment checklist..."
cat > DEPLOY_CHECKLIST.md << 'EOF'
# Deployment Checklist

## Pre-Deployment

- [ ] All files committed to git
- [ ] `.env` has ANTHROPIC_API_KEY
- [ ] `requirements.txt` includes anthropic package
- [ ] Database migration SQL ready

## Deployment Steps

### Option 1: Automated (Recommended)
```bash
export SERVER_IP=your.server.ip
export ANTHROPIC_API_KEY=sk-ant-xxx
./deploy-with-ai.sh
```

### Option 2: Manual

1. **Upload Files**
   ```bash
   rsync -avz ./ ubuntu@your-server:/opt/mockfactory/
   ```

2. **SSH to Server**
   ```bash
   ssh ubuntu@your-server
   cd /opt/mockfactory
   ```

3. **Run Migration**
   ```bash
   docker exec mockfactory_postgres_1 \
     psql -U mockfactory -d mockfactory \
     -f migration_ai.sql
   ```

4. **Rebuild Containers**
   ```bash
   docker-compose -f docker-compose.prod.yml down
   docker-compose -f docker-compose.prod.yml build
   docker-compose -f docker-compose.prod.yml up -d
   ```

5. **Verify**
   ```bash
   curl https://mockfactory.io/app.html
   docker-compose logs -f
   ```

## Post-Deployment

- [ ] Website loads: https://mockfactory.io/
- [ ] Dashboard works: https://mockfactory.io/app.html
- [ ] Can sign in with SSO
- [ ] Chat icon appears in dashboard
- [ ] AI assistant responds to messages
- [ ] Admin account (rjc@afterdarksys.com) has unlimited access
- [ ] Database has ai_usage table
- [ ] Logs show no errors

## Testing AI

1. Go to https://mockfactory.io/app.html
2. Sign in with rjc@afterdarksys.com
3. Click chat icon (bottom-right)
4. Should see: "Tier: employee · Unlimited"
5. Send: "Hello Claude!"
6. Should get intelligent response
7. Check database:
   ```sql
   SELECT COUNT(*) FROM ai_usage;
   SELECT SUM(profit) FROM ai_usage;
   ```

## Rollback (if needed)

```bash
# SSH to server
ssh ubuntu@your-server
cd /opt/mockfactory

# Revert database
docker exec mockfactory_postgres_1 \
  psql -U mockfactory -d mockfactory \
  -c "DROP TABLE IF EXISTS ai_usage;"

# Deploy previous version
git checkout previous-commit
docker-compose -f docker-compose.prod.yml up -d --build
```

## Monitoring

```bash
# View logs
docker-compose logs -f mockfactory

# Check AI usage
docker exec mockfactory_postgres_1 \
  psql -U mockfactory -d mockfactory \
  -c "SELECT COUNT(*), SUM(profit) FROM ai_usage WHERE created_at > NOW() - INTERVAL '1 day';"

# Monitor Anthropic costs
# Visit: https://console.anthropic.com/settings/usage
```
EOF

print_success "Checklist created: DEPLOY_CHECKLIST.md"
echo ""

# Summary
echo "================================================"
print_success "Preparation Complete! 🎉"
echo "================================================"
echo ""
echo "📂 Files ready for deployment:"
echo "   • All application code"
echo "   • AI assistant features"
echo "   • Database migration (migration_ai.sql)"
echo "   • Admin access script"
echo ""
echo "🚀 Next steps:"
echo ""
echo "1. Set your server IP:"
echo "   export SERVER_IP=your.server.ip.address"
echo ""
echo "2. Deploy everything:"
echo "   ./deploy-with-ai.sh"
echo ""
echo "   OR deploy manually following:"
echo "   cat DEPLOY_CHECKLIST.md"
echo ""
echo "3. Verify deployment:"
echo "   • Visit: https://mockfactory.io/app.html"
echo "   • Sign in with: rjc@afterdarksys.com"
echo "   • Click chat icon and test AI"
echo ""
echo "📚 Documentation:"
echo "   • DEPLOY.md - Full deployment guide"
echo "   • MONETIZE_CLAUDE.md - Revenue model"
echo "   • AI_ASSISTANT_SETUP.md - Technical setup"
echo ""
