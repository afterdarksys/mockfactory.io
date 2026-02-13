#!/bin/bash

echo "🏭 MockFactory Startup Script"
echo "=============================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env with your configuration before starting!"
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

echo "✅ Docker is running"

# Start services
echo "🚀 Starting MockFactory services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check if services are up
if docker-compose ps | grep -q "Up"; then
    echo ""
    echo "✅ MockFactory is running!"
    echo ""
    echo "📍 Access points:"
    echo "   - API: http://localhost:8000"
    echo "   - API Docs: http://localhost:8000/docs"
    echo "   - Frontend: Open frontend/index.html in your browser"
    echo ""
    echo "📊 View logs:"
    echo "   docker-compose logs -f api"
    echo ""
    echo "🛑 Stop services:"
    echo "   docker-compose down"
else
    echo "❌ Failed to start services. Check logs:"
    echo "   docker-compose logs"
fi
