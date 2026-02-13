#!/bin/bash
###############################################################################
# MockFactory.io - Staging Deployment Script
# Version: 1.0.0
# Date: February 11, 2026
#
# This script automates the staging deployment of MockFactory.io
# Usage: ./deploy-staging.sh
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENV_FILE=".env.staging"
COMPOSE_FILE="docker-compose.prod.yml"
PROJECT_DIR="/Users/ryan/development/mockfactory.io"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_command() {
    if ! command -v $1 &> /dev/null; then
        log_error "$1 is not installed or not in PATH"
        exit 1
    fi
}

###############################################################################
# PRE-FLIGHT CHECKS
###############################################################################

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        MockFactory.io - Staging Deployment Script             ║"
echo "║                    Version 1.0.0                               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

log_info "Running pre-flight checks..."

# Check working directory
if [ ! -d "$PROJECT_DIR" ]; then
    log_error "Project directory not found: $PROJECT_DIR"
    exit 1
fi

cd "$PROJECT_DIR" || exit 1
log_success "Working directory: $PROJECT_DIR"

# Check required commands
log_info "Checking required commands..."
check_command docker
check_command alembic
check_command openssl
log_success "All required commands are available"

# Check Docker is running
log_info "Checking Docker daemon..."
if ! docker ps &> /dev/null; then
    log_error "Docker daemon is not running. Please start Docker Desktop and try again."
    log_info "On macOS: open -a Docker"
    exit 1
fi
log_success "Docker daemon is running"

# Check required files
log_info "Checking required files..."
if [ ! -f "$ENV_FILE" ]; then
    log_error "Environment file not found: $ENV_FILE"
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    log_error "Docker Compose file not found: $COMPOSE_FILE"
    exit 1
fi

if [ ! -d "secrets" ] || [ ! -f "secrets/oci_config" ] || [ ! -f "secrets/oci_key.pem" ]; then
    log_error "OCI secrets not configured. Please run setup first."
    log_info "Required files:"
    log_info "  - secrets/oci_config"
    log_info "  - secrets/oci_key.pem"
    exit 1
fi
log_success "All required files present"

###############################################################################
# DEPLOYMENT STEPS
###############################################################################

echo ""
log_info "Starting deployment..."
echo ""

# Step 1: Pull latest images
log_info "Step 1/8: Pulling Docker images..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull postgres redis 2>&1 | grep -v "Warning"
log_success "Images pulled successfully"

# Step 2: Start database and Redis
log_info "Step 2/8: Starting PostgreSQL and Redis..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d postgres redis

# Wait for PostgreSQL to be healthy
log_info "Waiting for PostgreSQL to be healthy..."
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if docker compose -f "$COMPOSE_FILE" ps postgres | grep -q "healthy"; then
        break
    fi
    sleep 1
    attempt=$((attempt + 1))
    echo -n "."
done
echo ""

if [ $attempt -eq $max_attempts ]; then
    log_error "PostgreSQL failed to become healthy"
    docker compose -f "$COMPOSE_FILE" logs postgres
    exit 1
fi
log_success "PostgreSQL is healthy"

# Wait for Redis to be healthy
log_info "Waiting for Redis to be healthy..."
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if docker compose -f "$COMPOSE_FILE" ps redis | grep -q "healthy"; then
        break
    fi
    sleep 1
    attempt=$((attempt + 1))
    echo -n "."
done
echo ""

if [ $attempt -eq $max_attempts ]; then
    log_error "Redis failed to become healthy"
    docker compose -f "$COMPOSE_FILE" logs redis
    exit 1
fi
log_success "Redis is healthy"

# Step 3: Create initial migration (if not exists)
log_info "Step 3/8: Checking Alembic migrations..."
if [ -z "$(ls -A alembic/versions/)" ]; then
    log_info "Creating initial migration..."
    export DATABASE_URL="postgresql://mockfactory:2f41d7917bc278bdab73f8b08a138870@localhost:5432/mockfactory"
    alembic revision --autogenerate -m "Initial schema: User, Environment, EnvironmentUsageLog, Execution, APIKey, PortAllocation, DNSRecord"
    log_success "Initial migration created"
else
    log_info "Migrations already exist"
fi

# Step 4: Apply migrations
log_info "Step 4/8: Applying database migrations..."
export DATABASE_URL="postgresql://mockfactory:2f41d7917bc278bdab73f8b08a138870@localhost:5432/mockfactory"
alembic upgrade head
log_success "Migrations applied successfully"

# Step 5: Verify database schema
log_info "Step 5/8: Verifying database schema..."
table_count=$(docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U mockfactory -d mockfactory -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" | tr -d ' ')
if [ "$table_count" -ge 7 ]; then
    log_success "Database schema verified ($table_count tables created)"
else
    log_error "Expected at least 7 tables, found $table_count"
    exit 1
fi

# Step 6: Start Docker socket proxy
log_info "Step 6/8: Starting Docker socket proxy..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d docker-proxy
sleep 2
log_success "Docker socket proxy started"

# Step 7: Build and start API
log_info "Step 7/8: Building and starting API container..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build api 2>&1 | grep -v "Warning"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d api

# Wait for API to start
log_info "Waiting for API to start..."
attempt=0
while [ $attempt -lt 30 ]; do
    if curl -s http://localhost:8000/health &> /dev/null; then
        break
    fi
    sleep 1
    attempt=$((attempt + 1))
    echo -n "."
done
echo ""

if [ $attempt -eq 30 ]; then
    log_error "API failed to start"
    docker compose -f "$COMPOSE_FILE" logs api
    exit 1
fi
log_success "API started successfully"

# Step 8: Verify deployment
log_info "Step 8/8: Verifying deployment..."

# Health check
health_status=$(curl -s http://localhost:8000/health | grep -o '"status":"healthy"')
if [ -n "$health_status" ]; then
    log_success "Health check: PASS"
else
    log_error "Health check: FAIL"
    exit 1
fi

# API root
api_root=$(curl -s http://localhost:8000/ | grep -o '"name":"MockFactory API"')
if [ -n "$api_root" ]; then
    log_success "API root: PASS"
else
    log_error "API root: FAIL"
    exit 1
fi

# Container count
container_count=$(docker compose -f "$COMPOSE_FILE" ps | grep -c "Up")
if [ "$container_count" -ge 4 ]; then
    log_success "Containers running: $container_count"
else
    log_error "Expected at least 4 containers, found $container_count"
    exit 1
fi

###############################################################################
# DEPLOYMENT SUMMARY
###############################################################################

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           DEPLOYMENT SUCCESSFUL                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

log_success "MockFactory.io staging environment is now running!"
echo ""
echo "Service URLs:"
echo "  - API:               http://localhost:8000"
echo "  - API Documentation: http://localhost:8000/docs"
echo "  - Health Check:      http://localhost:8000/health"
echo ""
echo "Database:"
echo "  - PostgreSQL:        localhost:5432"
echo "  - Database:          mockfactory"
echo "  - User:              mockfactory"
echo ""
echo "Next steps:"
echo "  1. Open API docs:    open http://localhost:8000/docs"
echo "  2. Run smoke tests:  See STAGING_DEPLOYMENT_RUNBOOK.md"
echo "  3. Create test user: curl -X POST http://localhost:8000/api/v1/auth/register ..."
echo "  4. View logs:        docker compose -f $COMPOSE_FILE logs -f api"
echo ""
echo "Troubleshooting:"
echo "  - View all logs:     docker compose -f $COMPOSE_FILE logs -f"
echo "  - Stop services:     docker compose -f $COMPOSE_FILE down"
echo "  - Restart API:       docker compose -f $COMPOSE_FILE restart api"
echo ""

log_info "Deployment completed at $(date)"
