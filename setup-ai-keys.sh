#!/bin/bash
set -e

# Setup AI API Keys
# This script helps you add your existing Anthropic, OpenAI, and OpenRouter keys

echo "================================================"
echo "  AI Assistant API Keys Setup"
echo "================================================"
echo ""
echo "You mentioned having keys for:"
echo "  • Anthropic (Claude)"
echo "  • OpenAI (GPT)"
echo "  • OpenRouter (Multi-provider)"
echo ""
echo "Let's add them to your .env file!"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Creating from .env.example or .env.staging..."
    if [ -f .env.example ]; then
        cp .env.example .env
    elif [ -f .env.staging ]; then
        cp .env.staging .env
    else
        echo "No template found. Creating new .env..."
        touch .env
    fi
fi

# Backup existing .env
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
echo "✅ Backed up existing .env"
echo ""

# Add AI section if not exists
if ! grep -q "# AI ASSISTANT CONFIGURATION" .env; then
    echo "" >> .env
    echo "# ============================================================================" >> .env
    echo "# AI ASSISTANT CONFIGURATION" >> .env
    echo "# ============================================================================" >> .env
fi

# Anthropic
echo "📝 Anthropic API Key (Claude)"
echo "   Current: $(grep ANTHROPIC_API_KEY .env 2>/dev/null | cut -d'=' -f2 | sed 's/\(.\{10\}\).*/\1.../' || echo 'Not set')"
read -p "   Enter new key (or press Enter to skip): " ANTHROPIC_KEY
if [ -n "$ANTHROPIC_KEY" ]; then
    # Remove old key if exists
    sed -i.bak '/^ANTHROPIC_API_KEY=/d' .env
    echo "ANTHROPIC_API_KEY=$ANTHROPIC_KEY" >> .env
    echo "   ✅ Anthropic key added"
fi
echo ""

# OpenAI
echo "📝 OpenAI API Key (GPT-4, etc.)"
echo "   Current: $(grep OPENAI_API_KEY .env 2>/dev/null | cut -d'=' -f2 | sed 's/\(.\{10\}\).*/\1.../' || echo 'Not set')"
read -p "   Enter new key (or press Enter to skip): " OPENAI_KEY
if [ -n "$OPENAI_KEY" ]; then
    sed -i.bak '/^OPENAI_API_KEY=/d' .env
    echo "OPENAI_API_KEY=$OPENAI_KEY" >> .env
    echo "   ✅ OpenAI key added"
fi
echo ""

# OpenRouter
echo "📝 OpenRouter API Key (Multi-provider access)"
echo "   Current: $(grep OPENROUTER_API_KEY .env 2>/dev/null | cut -d'=' -f2 | sed 's/\(.\{10\}\).*/\1.../' || echo 'Not set')"
read -p "   Enter new key (or press Enter to skip): " OPENROUTER_KEY
if [ -n "$OPENROUTER_KEY" ]; then
    sed -i.bak '/^OPENROUTER_API_KEY=/d' .env
    echo "OPENROUTER_API_KEY=$OPENROUTER_KEY" >> .env
    echo "   ✅ OpenRouter key added"
fi
echo ""

# Set default provider
echo "📝 Default AI Provider"
echo "   Options: anthropic, openai, openrouter"
read -p "   Choose default (or press Enter for 'anthropic'): " DEFAULT_PROVIDER
DEFAULT_PROVIDER=${DEFAULT_PROVIDER:-anthropic}
sed -i.bak '/^AI_PROVIDER=/d' .env
echo "AI_PROVIDER=$DEFAULT_PROVIDER" >> .env
echo "   ✅ Default provider: $DEFAULT_PROVIDER"
echo ""

# Set fallback order
echo "📝 Fallback Strategy"
read -p "   Enable automatic fallback? (y/n, default: y): " ENABLE_FALLBACK
ENABLE_FALLBACK=${ENABLE_FALLBACK:-y}
sed -i.bak '/^AI_ENABLE_FALLBACK=/d' .env
if [[ $ENABLE_FALLBACK =~ ^[Yy]$ ]]; then
    echo "AI_ENABLE_FALLBACK=true" >> .env
    echo "   ✅ Fallback enabled: anthropic → openrouter → openai"
else
    echo "AI_ENABLE_FALLBACK=false" >> .env
    echo "   ℹ️  Fallback disabled"
fi
echo ""

# Clean up backup files
rm -f .env.bak

echo "================================================"
echo "  ✅ API Keys Configured!"
echo "================================================"
echo ""
echo "📋 Summary:"
echo ""
grep -E "(ANTHROPIC|OPENAI|OPENROUTER|AI_PROVIDER)" .env | while read line; do
    key=$(echo $line | cut -d'=' -f1)
    value=$(echo $line | cut -d'=' -f2)
    if [[ $key == *"KEY"* ]]; then
        # Mask the key
        masked=$(echo $value | sed 's/\(.\{10\}\).*/\1.../')
        echo "  $key=$masked"
    else
        echo "  $line"
    fi
done
echo ""
echo "🔒 Full keys saved in .env (do NOT commit!)"
echo "📦 Backup saved as .env.backup.*"
echo ""
echo "Next steps:"
echo "  1. Test locally: python -c 'from app.api.ai_assistant import anthropic_client; print(anthropic_client)'"
echo "  2. Deploy: ./deploy-with-ai.sh"
echo ""
