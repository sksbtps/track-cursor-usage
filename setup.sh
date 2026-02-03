#!/bin/bash
# Setup script for Cursor Usage Menu Bar App

set -e

echo "🚀 Setting up Cursor Usage Menu Bar App..."

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    echo "   Install via: brew install python3"
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "📥 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright browsers
echo "🌐 Installing Playwright browsers (this may take a minute)..."
python -m playwright install chromium

# Create browser data directory
echo "📁 Creating data directory..."
mkdir -p ~/.cursor-usage-app/browser-data

echo ""
echo "✅ Setup complete!"
echo ""
echo "To run the app:"
echo "  ./run.sh"
echo ""
echo "To start on login, run:"
echo "  ./install-launch-agent.sh"
