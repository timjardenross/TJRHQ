# REVS Content Creation Agents

Transform detailed design briefs into publication-ready assets across 7 formats:
- **Posters** (PNG/SVG)
- **Articles** (HTML/Markdown)
- **Videos** (MP4 + Storyboard)
- **Worksheets** (Fillable PDF)
- **Presentations** (PPTX)
- **Podcasts** (MP3/WAV)
- **Social Media** (multi-platform assets)

## Quick Start

### 1. Installation (30 minutes)

```bash
# Clone and enter project
cd TJRHQ/projects/revs-content-agents

# Run installation script
./scripts/install.sh

# Verify installation
python -c "import ollama; import langchain; print('✓ Ready to go')"
```

### 2. Configuration

```bash
# Copy and edit config
cp config/config.template.yml config/config.yml
nano config/config.yml
```

### 3. Generate Content

```bash
# Activate environment
source venv/bin/activate

# Generate all 7 formats from one design brief
python src/main.py --brief path/to/design_brief.md --output-dir outputs/
```

## Documentation

- **[MISSION_BRIEF.md](MISSION_BRIEF.md)** — Complete project specification
- **[docs/INSTALLATION.md](docs/INSTALLATION.md)** — Detailed setup guide
- **[docs/OPERATIONS.md](docs/OPERATIONS.md)** — Running & monitoring

## Technology Stack (All Open-Source, $0/month)

- **Parsing:** Ollama + Mistral 7B
- **Text:** Markdown/Pandoc/Weasyprint
- **Visuals:** Stable Diffusion + Pillow
- **Video:** FFmpeg + MoviePy
- **Audio:** Coqui TTS + pydub
- **Presentations:** python-pptx

## System Requirements

- Ubuntu 22.04 LTS
- 8+ cores, 16GB RAM, 100GB SSD
- NVIDIA GPU optional (8GB+)

## Status

🚀 = Ready | 🏗️ = In Progress | 📋 = Planned

| Component | Status | Timeline |
|-----------|--------|----------|
| Mission Brief | 🚀 | Complete |
| Parser | 🚀 | Week 1 |
| Article Agent | 🚀 | Week 1 |
| Poster Agent | 🏗️ | Week 2 |
| Worksheet Agent | 📋 | Week 3 |
| Presentation Agent | 📋 | Week 3 |
| Video Agent | 📋 | Week 4 |
| Podcast Agent | 📋 | Week 4 |
| Social Agent | 📋 | Week 4 |

## Next Steps

1. Read [MISSION_BRIEF.md](MISSION_BRIEF.md)
2. Follow [docs/INSTALLATION.md](docs/INSTALLATION.md)
3. Start Week 1 implementation

**Ready to execute in 5 weeks.**
