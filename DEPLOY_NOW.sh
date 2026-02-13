#!/bin/bash
set -e

# MockFactory AI Deployment - Complete Setup
# Just run this script after adding your API keys to .env

echo "🚀 MockFactory AI Assistant - Final Deployment"
echo ""

# Check keys are set
if grep -q "your_anthropic_key_here" .env; then
    echo "⚠️  Please add your API keys to .env first:"
    echo ""
    echo "   Edit .env lines 27-29:"
    echo "   ANTHROPIC_API_KEY=sk-ant-..."
    echo "   OPENAI_API_KEY=sk-..."
    echo "   OPENROUTER_API_KEY=sk-or-..."
    echo ""
    read -p "Press Enter after adding keys, or Ctrl+C to cancel..."
fi

# Set server IP (from your docs: 141.148.79.30)
export SERVER_IP=141.148.79.30

echo "✅ Server: $SERVER_IP (mockfactory.io)"
echo "✅ Keys configured"
echo ""
echo "🚀 Deploying..."
echo ""

# Deploy
./deploy-with-ai.sh

echo ""
echo "✅ DEPLOYMENT COMPLETE!"
echo ""
echo "Access at:"
echo "  • https://mockfactory.io/app.html"
echo "  • Sign in: rjc@afterdarksys.com"
echo "  • Click chat icon to test AI"
echo ""
