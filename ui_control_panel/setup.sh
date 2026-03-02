#!/bin/bash
# Quick setup script for Streamlit UI

set -e

echo "🚀 Setting up Streamlit UI for Cineca Agentic Platform"
echo ""

# Check Python version
echo "📌 Checking Python version..."
python3 --version

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create secrets file if it doesn't exist
if [ ! -f ".streamlit/secrets.toml" ]; then
    echo "🔐 Creating secrets file from template..."
    cp .streamlit/secrets.toml.template .streamlit/secrets.toml
    echo ""
    echo "⚠️  IMPORTANT: Edit .streamlit/secrets.toml with your Auth0 credentials!"
    echo ""
fi

# Create logs directory
mkdir -p logs

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .streamlit/secrets.toml with your Auth0 credentials"
echo "  2. Ensure the API is running at http://localhost:8000"
echo "  3. Run: streamlit run app.py"
echo ""
echo "Or use Docker:"
echo "  docker-compose up --build"
echo ""
