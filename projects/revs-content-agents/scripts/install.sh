#!/bin/bash
set -e

echo "🚀 REVS Content Creation Agents - Installation Script"
echo "=================================================="

# Check for Python 3.10+
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python $PYTHON_VERSION detected"

if ! command -v pip &> /dev/null; then
    echo "✗ pip not found. Install Python 3.10+"
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip setuptools wheel

# Install dependencies
echo "📥 Installing Python dependencies..."
pip install -r requirements.txt

# Check system dependencies
echo "🔍 Checking system dependencies..."
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  ffmpeg not found. Install with: sudo apt install ffmpeg"
fi

if ! command -v pandoc &> /dev/null; then
    echo "⚠️  pandoc not found. Install with: sudo apt install pandoc"
fi

# Create config from template
echo "⚙️ Setting up configuration..."
if [ ! -f config/config.yml ]; then
    cp config/config.template.yml config/config.yml
    echo "✓ Created config/config.yml - edit as needed"
else
    echo "✓ config/config.yml already exists"
fi

# Create output directories
echo "📁 Creating output directories..."
mkdir -p outputs/{posters,articles,videos,worksheets,presentations,podcasts,social}

# Test Ollama
echo "🧠 Testing Ollama connection..."
if command -v ollama &> /dev/null; then
    echo "✓ Ollama found"
    echo ""
    echo "⚠️  Make sure Ollama is running:"
    echo "  ollama serve"
    echo ""
    echo "Then pull the model:"
    echo "  ollama pull mistral:7b"
else
    echo "⚠️  Ollama not found. Install from https://ollama.ai"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit config/config.yml"
echo "2. Start Ollama: ollama serve"
echo "3. Pull model: ollama pull mistral:7b"
echo "4. Activate env: source venv/bin/activate"
echo "5. Run: python src/main.py --brief <brief.md>"
echo ""
