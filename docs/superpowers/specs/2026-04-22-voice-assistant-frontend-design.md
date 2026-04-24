# Voice Assistant Frontend Design

## Overview

Interactive React frontend for the voice assistant system, enabling browser-based voice interaction alongside the existing ESP32 client support. The frontend connects to python-hub via HTTP for configuration and WebSocket for voice pipeline.

## Architecture

```
Browser (React) ←→ HTTP API ←→ python-hub HTTP Server
     |                |
     |                +→ /api/* REST endpoints
     |
     └── WebSocket ──→ python-hub Voice WS (port 8765)

python-hub ←→ FunASR API / LLM Server / edge-tts
```

### Components

1. **React Frontend** - Vite-based React app (runs separately, can be served by nginx or Vite dev server)
2. **python-hub HTTP API** - FastAPI server on port 8766 for prompt/config management
3. **python-hub WebSocket** - Voice pipeline handler on port 8765 (shared with ESP32)

### Ports

- Frontend dev server: `5173` (Vite) or `8080` (production nginx)
- python-hub HTTP API: `8766` (configurable via `server.http_port`)
- python-hub WebSocket: `8765` (configurable via `server.port`, shared with ESP32)

### Implementation Note

This is a greenfield implementation. The existing `main.py` handles ESP32 WebSocket protocol. New files will be added:
- `http_api.py` - FastAPI HTTP endpoints
- `prompt_store.py` - System prompt file management
- `browser_ws_handler.py` - Browser-specific WebSocket voice handler

## API Design

### HTTP Endpoints (Port 8766)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/prompts` | List all prompt files |
| POST | `/api/prompts` | Create new prompt file |
| GET | `/api/prompts/<name>` | Get prompt content |
| PUT | `/api/prompts/<name>` | Update prompt content |
| DELETE | `/api/prompts/<name>` | Delete prompt file |
| GET | `/api/config` | Get current TTS/voice config |
| PUT | `/api/config` | Update TTS/voice config |
| GET | `/api/status` | Get pipeline status |

### WebSocket Protocol - Browser Client (Port 8765)

The browser WebSocket handler is separate from the ESP32 handler. The server detects browser client by checking for `audio_chunk` messages with base64-encoded data.

**Client → Server:**
```json
{"type": "audio_start", "session_id": "abc123"}
{"type": "audio_chunk", "data": "<base64 PCM>"}
{"type": "audio_end"}
{"type": "cancel"}
```

**Audio Format:** PCM s16le, 16kHz, mono, 16-bit

**Server → Client:**
```json
{"type": "state", "state": "listening|processing|speaking|idle"}
{"type": "text", "text": "recognized speech"}
{"type": "llm_chunk", "text": "partial LLM output"}
{"type": "tts_ready"}
{"type": "tts_audio", "data": "<base64 PCM>"}
{"type": "tts_end"}
{"type": "error", "message": "..."}
```

### Protocol Differences: Browser vs ESP32

| Aspect | ESP32 | Browser |
|--------|-------|---------|
| Audio format | Binary PCM chunks | Base64 encoded PCM in JSON |
| LLM streaming | Not exposed | `llm_chunk` message |
| TTS direction | Server→Client streaming | Server→Client streaming |
| Cancel support | Not needed | `cancel` message |

## Frontend UI Components

### Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Voice Assistant Hub                            [Status: ●Idle] │
├───────────────┬─────────────────────────────────────────────────┤
│               │                                                 │
│  PROMPTS      │   CHAT LOG                                      │
│  ───────────  │   ────────────────────────────────────────────  │
│  [Dropdown ▼] │                                                 │
│               │   User: 你好，我要称王称霸                        │
│  ┌─────────┐  │                                                 │
│  │ Edit    │  │   Assistant: 这是一个非常气势磅礴的宣言！         │
│  │ Prompt  │  │   (TTS audio playing...)                        │
│  │ Content │  │                                                 │
│  │         │  │                                                 │
│  │ [Save]  │  │                                                 │
│  └─────────┘  │                                                 │
│               │                                                 │
├───────────────┼─────────────────────────────────────────────────┤
│  SETTINGS     │   MICROPHONE                                     │
│  ───────────  │   ────────────────────────────────────────────  │
│  Voice: [▼]   │                                                 │
│  Rate: -42%   │            [🎤 Push to Talk]                     │
│  Pitch: +13Hz │                                                 │
│               │   [▶️ Playback Controls]                          │
└───────────────┴─────────────────────────────────────────────────┘
```

### Components

1. **PromptPanel** - Dropdown to select prompt, inline editor with save
2. **ChatLog** - Scrollable conversation display with timestamps
3. **MicrophonePanel** - Push-to-talk button with visual feedback
4. **SettingsPanel** - TTS voice/rate/pitch configuration
5. **StatusIndicator** - Shows current state (Idle/Listening/Processing/Speaking)

## python-hub Backend Changes

### New File Structure

```
src/
├── main.py              # WebSocket server (ESP32 handler - unchanged)
├── http_api.py          # NEW: FastAPI HTTP endpoints
├── prompt_store.py      # NEW: System prompt file management
├── browser_ws_handler.py # NEW: Browser WebSocket voice handler
├── protocol/
│   └── ws_protocol.py   # Modified: Add build_llm_chunk, parse_audio_chunk_base64
├── config.py           # Modified: Add prompt_dir setting
└── state_machine.py     # Modified: Add cancel handler
```

### Prompt Store

- Base directory: configurable via `prompt_dir` (default `/app/prompts`)
- File format: `.txt` or `.md`
- Storage: Plain text files on filesystem

### TTS Text Processing

Before sending to edge-tts:
1. Remove emojis (existing `filter_emojis()`)
2. Remove asterisks (markdown bold/italic markers: `*text*` → `text`)
3. Strip extra whitespace

## Error Handling

1. **No microphone permission** - Show clear error message, guide user to enable
2. **LLM connection failure** - Show error in chat log, allow retry
3. **TTS synthesis failure** - Fallback to showing text if audio fails
4. **Prompt file not found** - Default to empty system prompt
5. **WebSocket disconnect** - Auto-reconnect with exponential backoff
6. **Cancel during processing** - Stop LLM streaming, reset state

## Configuration

### python-hub config.yaml additions

```yaml
prompt_dir: "./prompts"  # Directory for system prompt files

tts:
  voice: "zh-CN-YunxiaNeural"
  rate: "-42%"
  pitch: "+13Hz"
  volume: "+0%"
```

### Default Prompts (created on first run)

- `default.txt` - Default system prompt
- `creative.txt` - Creative conversation mode
- `formal.txt` - Formal/polite mode

## Dependencies

### Frontend (React)

```json
{
  "react": "^18.2.0",
  "react-dom": "^18.2.0",
  "lucide-react": "^0.300.0",
  "tailwindcss": "^3.4.0",
  "@vitejs/plugin-react": "^4.2.0"
}
```

### Backend (python-hub) - Add to pyproject.toml

```toml
dependencies = [
    # existing...
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "python-multipart>=0.0.6",
]
```

## Implementation Tasks

1. Add FastAPI, uvicorn, python-multipart dependencies to pyproject.toml
2. Create `prompt_store.py` for file-based prompt management
3. Create `http_api.py` with FastAPI endpoints
4. Add `build_llm_chunk()` and `build_tts_audio()` to ws_protocol.py
5. Create `browser_ws_handler.py` for browser WebSocket protocol
6. Add cancel handler to state_machine.py
7. Update config.py: add `prompt_dir`, `http_port` settings
8. Update config.py: add TTS config save/load via API
9. Add TTS text filtering: remove asterisks from text before synthesis
10. Create React app with Vite
11. Implement PromptPanel component
12. Implement ChatLog component
13. Implement MicrophonePanel with WebAudio API
14. Implement SettingsPanel
