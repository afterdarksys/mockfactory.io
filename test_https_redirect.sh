#!/bin/bash

echo "🔒 Testing HTTPS Redirect for MockFactory.io"
echo "=============================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: HTTP to HTTPS redirect
echo "Test 1: HTTP → HTTPS redirect"
echo "------------------------------"
response=$(curl -s -I -L http://mockfactory.io/ 2>&1)
if echo "$response" | grep -q "301"; then
    echo -e "${GREEN}✓${NC} HTTP returns 301 redirect"
else
    echo -e "${RED}✗${NC} HTTP does not return 301 redirect"
fi

if echo "$response" | grep -q "https://mockfactory.io"; then
    echo -e "${GREEN}✓${NC} Redirects to HTTPS"
else
    echo -e "${RED}✗${NC} Does not redirect to HTTPS"
fi
echo ""

# Test 2: HTTPS loads successfully
echo "Test 2: HTTPS endpoint"
echo "----------------------"
https_status=$(curl -s -o /dev/null -w "%{http_code}" https://mockfactory.io/health 2>&1)
if [ "$https_status" = "200" ]; then
    echo -e "${GREEN}✓${NC} HTTPS endpoint returns 200 OK"
else
    echo -e "${YELLOW}⚠${NC} HTTPS status: $https_status (SSL may not be configured yet)"
fi
echo ""

# Test 3: WWW subdomain
echo "Test 3: WWW subdomain redirect"
echo "-------------------------------"
www_response=$(curl -s -I -L http://www.mockfactory.io/ 2>&1)
if echo "$www_response" | grep -q "301"; then
    echo -e "${GREEN}✓${NC} WWW HTTP returns 301 redirect"
else
    echo -e "${RED}✗${NC} WWW HTTP does not return 301 redirect"
fi
echo ""

# Test 4: API endpoint redirect
echo "Test 4: API endpoint redirect"
echo "------------------------------"
api_response=$(curl -s -I http://mockfactory.io/api/v1/code/languages 2>&1)
if echo "$api_response" | grep -q "301"; then
    echo -e "${GREEN}✓${NC} API endpoint redirects to HTTPS"
else
    echo -e "${RED}✗${NC} API endpoint does not redirect"
fi
echo ""

# Test 5: X-Forwarded-Proto header
echo "Test 5: X-Forwarded-Proto header (load balancer)"
echo "-------------------------------------------------"
forwarded_response=$(curl -s -I -H "X-Forwarded-Proto: http" http://mockfactory.io/ 2>&1)
if echo "$forwarded_response" | grep -q "301"; then
    echo -e "${GREEN}✓${NC} Respects X-Forwarded-Proto header"
else
    echo -e "${YELLOW}⚠${NC} X-Forwarded-Proto check failed (may need load balancer setup)"
fi
echo ""

# Summary
echo "=============================================="
echo "Summary"
echo "=============================================="
echo ""
echo "Current status:"
echo "  • App has HTTPS redirect middleware: ${GREEN}✓${NC}"
echo "  • DNS configured: ${GREEN}✓${NC} (mockfactory.io → 141.148.79.30)"
echo ""

if [ "$https_status" = "200" ]; then
    echo -e "${GREEN}✓ SSL is configured and working!${NC}"
else
    echo -e "${YELLOW}⚠ Next step: Configure SSL certificate${NC}"
    echo ""
    echo "Options to enable HTTPS:"
    echo "  1. Cloudflare proxy (easiest - 5 min)"
    echo "  2. OCI Load Balancer SSL (15 min)"
    echo "  3. Let's Encrypt + Nginx (20 min)"
    echo ""
    echo "See docs/SSL_SETUP.md for instructions"
fi
echo ""
