# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voice Assistant Hub - a dual-client pipeline supporting ESP32 (streaming) and Browser (complete audio) clients via WebSocket. Routes audio through ASR (FunASR) → LLM (llama.cpp/Gemma) → TTS (Edge TTS).

## Development Commands

### Docker (Primary dev environment)
```bash
# Build and start all services
docker compose up --build

# View logs
docker logs python-hub --tail 100 -f
docker logs frontend --tail 50 -f

# Restart a specific service
docker compose restart python-hub

# Execute Python in container (for testing)
docker exec -it python-hub python -c "from src.memory.naming import generate_session_id; print(generate_session_id())"

# Copy files from container (for sync verification)
docker cp python-hub:/app/src/memory/naming.py ./src/memory/
```

### Frontend
```bash
cd frontend
pnpm install          # Install dependencies
pnpm dev              # Start dev server (port 5173)
pnpm build            # Production build
```

### Testing

**Playwright E2E tests:**
```bash
# Install (once)
uv add playwright && ~/.venv/bin/playwright install chromium

# Run tests
uv run python test_script.py

# Example:
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    page = p.chromium.launch(headless=True).new_page()
    page.goto('http://localhost:5173')
    page.wait_for_load_state('networkidle')
    browser.close()
```

### Python Backend (local dev - requires all services running)
```bash
# Install dependencies with uv
uv sync

# Run with uv (auto-loads .env and pyproject.toml)
uv run python -m src.main

# Or activate venv first
source .venv/bin/activate
python -m src.main
```

### Syncing Local Changes to Docker

After updating local code, sync to container:
```bash
# Copy specific file to container
docker cp ./src/memory/naming.py python-hub:/app/src/memory/

# Copy entire src directory
docker cp ./src python-hub:/app/src

# Or rebuild (slow but ensures full sync)
docker compose up --build python-hub
```

**Workflow**: Edit local → `docker cp` to container → test in browser → commit when verified

## Architecture

### Services (docker-compose)
- **python-hub**: Main backend (WebSocket 8765/8767, HTTP 8766)
- **llama-server**: LLM inference (port 8080)
- **funasr-api**: ASR service (port 8001)
- **frontend**: React app (port 5173)

### WebSocket Handlers
1. **ESP32** (`main.py:handle_esp32`, port 8765) - Binary PCM streaming + JSON protocol
2. **Browser** (`browser_ws_handler.py`, port 8767) - Base64 audio/text, returns streaming LLM + TTS

### Pipeline Flow
```
Audio/Text → ASR (FunASR) → LLM (streaming) → TTS (Edge) → Audio
                ↓
         Memory System (dual-track)
```

### Memory System
1. **Rolling Summary** (`rolling_session.py`) - Intra-session compression
   - Sliding window: `window_size=10` turns
   - Trigger: `len(turns) > window` OR `tokens > 8000`
   - Async summarization via `summarize_async()`
2. **Global Memory** (`global_memory.py`) - Cross-session BM25 retrieval
   - Trigger phrases: "还记得", "记得", "上次", "之前"
   - Stored in `memory/global/{timestamp}.md`

### Session Naming
- **File format**: `{YYYYMMDD}_{HHMMSS}_{ts}.json` (e.g., `20260426_142604_1777213564475.json`)
- **Session ID**: `ts-{timestamp}` (e.g., `ts-1777213564475`)
- **Naming service**: `src/memory/naming.py` (generate_filename, generate_session_id, parse_filename)

### SOUL.md Behavioral Rules (`soul.py`)
- Local-first: `prompts/soul.md`
- OpenClaw fallback: `~/.openclaw/workspace/SOUL.md`
- Sections: 核心原则, 行为准则, 老大想要我做什么, 风格

### HTTP API Endpoints (port 8766)
- `GET/POST /api/prompts` - List/create prompts
- `GET/PUT/DELETE /api/prompts/{name}` - CRUD prompts
- `GET/PUT /api/config` - TTS settings (voice, rate, pitch, volume)
- `GET /api/soul` - SOUL.md content

## Key Files

| File | Purpose |
|------|---------|
| `src/main.py` | ESP32 WebSocket handler, pipeline entry point |
| `src/browser_ws_handler.py` | Browser WebSocket handler |
| `src/http_api.py` | FastAPI REST endpoints |
| `src/pipeline/{asr,llm,tts}.py` | Audio processing pipeline |
| `src/memory/rolling_session.py` | Session memory + build_prompt() |
| `src/memory/global_memory.py` | Cross-session BM25 retrieval |
| `src/memory/naming.py` | Unified session/file naming |
| `src/soul.py` | SOUL.md parser (local-first + OpenClaw fallback) |
| `config.yaml` | Configuration (ports, LLM, TTS, memory params) |

## Configuration

All config via `config.yaml`:
```yaml
server:
  port: 8765        # ESP32 WebSocket
  http_port: 8766   # HTTP API
memory:
  window_size: 10   # Recent turns in short-term
  step_size: 5      # Turns to compress per summary
  token_threshold: 8000
```

## Ports Summary

| Port | Service | Protocol |
|------|---------|----------|
| 5173 | Frontend | HTTP |
| 8765 | ESP32 WS | WebSocket (binary+JSON) |
| 8766 | HTTP API | FastAPI REST |
| 8767 | Browser WS | WebSocket (base64) |
| 8001 | FunASR | HTTP (ASR) |
| 8080 | LLM Server | HTTP (OpenAI-compatible) |