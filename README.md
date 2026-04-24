# Voice Assistant Hub

A dual-client voice assistant pipeline supporting both **ESP32** (embedded/streaming) and **Browser** (web/complete-audio) clients.

## Architecture Overview

```
┌─────────────┐     WebSocket      ┌──────────────────┐
│    ESP32    │◄──────────────────►│                  │
│  (Streaming)│                    │   Python Hub      │
└─────────────┘                    │                  │
                                   │  ┌────────────┐  │
                                   │  │  HTTP API   │  │
                                   │  │   :8766     │  │
                                   │  └────────────┘  │
┌─────────────┐     WebSocket      │                  │
│   Browser   │◄──────────────────►│  ┌────────────┐  │
│   (React)   │                    │  │    WS      │  │
└─────────────┘                    │  │   :8767    │  │
                                   │  └────────────┘  │
                                   └────────┬────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    │                       │                       │
              ┌─────▼─────┐          ┌──────▼──────┐        ┌──────▼──────┐
              │   FunASR   │          │  LLM Server  │        │  Edge TTS   │
              │  (ASR)    │          │  (Gemma/GGUF)│        │  (Speech)   │
              │  :8001    │          │   :8080      │        │  (Cloud)    │
              └───────────┘          └──────────────┘        └─────────────┘
```

## Supported Clients

| Client | Connection | TTS Mode | Port |
|--------|------------|----------|------|
| ESP32 | WebSocket | Streaming (binary PCM chunks) | 8765 |
| Browser | WebSocket + HTTP | Complete audio (base64 WAV) | 8766/8767 |

## Features

- **ASR**: FunASR HTTP API for speech recognition
- **LLM**: OpenAI-compatible API (llama.cpp, Gemma, etc.)
- **TTS**: Microsoft Edge TTS (cloud)
- **Memory**: Rolling summary with dual-track architecture
- **Prompts**: File-based system prompt management
- **CORS**: Enabled for frontend development

## Directory Structure

```
python_hub/
├── src/
│   ├── main.py                 # ESP32 WebSocket handler + pipeline
│   ├── browser_ws_handler.py  # Browser WebSocket handler + pipeline
│   ├── http_api.py             # FastAPI for prompts & config
│   ├── config.py               # YAML config loader
│   ├── state_machine.py        # ESP32 protocol state machine
│   ├── prompt_store.py         # System prompt file management
│   ├── pipeline/
│   │   ├── asr.py              # FunASR client
│   │   ├── llm.py              # OpenAI-compatible LLM client
│   │   └── tts.py              # Edge TTS client
│   ├── memory/
│   │   ├── session.py          # Session/Turn/Summary models
│   │   └── summarizer.py       # Async LLM summarization
│   └── protocol/
│       └── ws_protocol.py      # WebSocket message builders
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Main React component
│   │   └── services/
│   │       ├── api.js          # HTTP API client
│   │       └── websocket.js    # WebSocket client
│   └── package.json
├── config.yaml                 # Configuration file
├── docker-compose.yml           # Docker services
├── models/                     # ONNX models (ASR/KWS/VAD)
├── prompts/                    # System prompt files
└── memory/
    ├── sessions/              # Session data
    └── summaries/             # Conversation summaries
```

## Quick Start

### Development

```bash
# Install dependencies
uv sync

# Activate virtual environment
source .venv/bin/activate

# Start the hub (requires FunASR API and LLM server running)
python -m src.main
```

### Docker

```bash
# Start all services (LLM, FunASR, Hub, Frontend)
docker compose up --build
```

### Frontend Development

```bash
cd frontend
pnpm install
pnpm dev
```

## Configuration

Edit `config.yaml`:

```yaml
server:
  host: "0.0.0.0"
  port: 8765        # ESP32 WebSocket
  http_port: 8766   # HTTP API

llm:
  base_url: "http://llama-server:8080/v1"
  model: "unsloth/gemma-4-E4B-it-GGUF:Q8_0"
  max_tokens: 131072

tts:
  voice: "zh-CN-YunxiaNeural"  # Edge TTS voice
  rate: "-20%"
  pitch: "+13Hz"

memory:
  window_size: 10      # Recent turns to keep
  step_size: 5         # Turns to compress per summary
  token_threshold: 8000
  max_summary_length: 300
```

## WebSocket Protocol

### ESP32 → Hub Messages

| Message | Fields | Description |
|---------|--------|-------------|
| `audio_start` | `session_id`, `turn_id` | Start recording |
| `audio_end` | `session_id` | End recording, trigger pipeline |
| `tts_ready` | - | ESP32 ready for TTS audio |
| `playback_done` | - | Audio playback finished |
| `session_end` | - | End session |

### Hub → ESP32 Messages

| Message | Fields | Description |
|---------|--------|-------------|
| `state` | `state`, `session_id`, `turn_id` | State directive |
| `text` | `text`, `session_id`, `turn_id` | ASR transcription |
| `error` | `message`, `session_id`, `turn_id` | Error message |
| `tts_start` | `sample_rate`, `format`, `channels` | TTS beginning |
| `tts_end` | `session_id`, `turn_id` | TTS complete |

### Browser Messages

| Message | Direction | Description |
|---------|-----------|-------------|
| `audio_start` | → | Start recording |
| `audio_chunk` | → | Base64 encoded audio |
| `audio_end` | → | End recording |
| `text_input` | → | Direct text input (skip ASR) |
| `cancel` | → | Cancel current operation |
| `llm_chunk` | ← | Streaming LLM output |
| `tts_complete` | ← | Complete base64 WAV audio |
| `state` | ← | State directive |

## State Machine

```
       audio_start           audio_end
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
───►│    IDLE    │────►│  LISTENING  │────►│ PROCESSING  │
    └─────────────┘     └─────────────┘     └──────┬──────┘
       ▲                                             │
       │              tts_ready                ┌────▼─────┐
       │                                         │ SPEAKING │
       │            playback_done                └────┬────┘
       └───────────────────────────────────────────┘
```

## HTTP API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/prompts` | List all prompts |
| POST | `/api/prompts` | Create prompt |
| GET | `/api/prompts/{name}` | Get prompt content |
| PUT | `/api/prompts/{name}` | Update prompt |
| DELETE | `/api/prompts/{name}` | Delete prompt |
| GET | `/api/config` | Get TTS config |
| PUT | `/api/config` | Update TTS config |
| GET | `/api/status` | Pipeline status |

## Dependencies

### Python (pyproject.toml)

- `websockets>=12.0` - WebSocket server
- `edge-tts>=0.2.0` - Text-to-speech
- `fastapi>=0.109.0` - HTTP API
- `uvicorn[standard]>=0.27.0` - ASGI server
- `httpx>=0.26.0` - HTTP client
- `pydantic>=2.0` - Data validation
- `pyyaml>=6.0` - YAML config
- `emoji>=2.0` - Emoji handling
- `aiofiles>=0.8` - Async file I/O

### Frontend (package.json)

- `react>=18.2.0` - UI framework
- `lucide-react>=0.300.0` - Icons
- `vite>=5.0.12` - Build tool
- `tailwindcss>=3.4.1` - Styling
- `@playwright/test>=1.59.1` - E2E testing

## Testing

```bash
# Run Python tests
docker exec python-hub python -m pytest tests/ -v

# Run frontend E2E tests
cd frontend
pnpm exec playwright test
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BASE_URL` | `http://llama-server:8080/v1` | LLM API endpoint |
| `LLM_MODEL` | `unsloth/gemma-4-E4B-it-GGUF:Q8_0` | Model name |
| `ASR_BASE_URL` | `http://funasr-api:8001` | FunASR API endpoint |
| `DEBUG_OUTPUT_DIR` | - | Debug output directory |
| `PYTHONPATH` | `/app` | Python path |

## TTS Text Filtering

Both ESP32 and Browser clients filter LLM output before synthesis:

1. **Markdown cleanup**: `**bold**` → `bold`, `*italic*` → `italic`
2. **Emoji removal**: Uses `emoji.replace_emoji()` library
3. **Whitespace normalization**: Multiple spaces/newlines → single space

## Memory System (Dual-Track)

- **Track 1**: Main pipeline uses `build_prompt()` with global summary + recent turns
- **Track 2**: Background async summarization via `asyncio.create_task`
- Summaries saved to `memory/summaries/{session_id}.md`
