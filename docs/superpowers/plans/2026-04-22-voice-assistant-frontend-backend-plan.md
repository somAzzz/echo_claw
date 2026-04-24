# Voice Assistant Frontend - Backend Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add HTTP API and browser WebSocket handler to python-hub for React frontend integration

**Architecture:** FastAPI HTTP server on port 8766 for prompt/config management; browser WebSocket handler on port 8765 for voice pipeline; file-based prompt storage

**Tech Stack:** Python 3.12, FastAPI, uvicorn, python-multipart, websockets (existing), edge-tts (existing)

---

## File Structure

### New Files
- `src/http_api.py` - FastAPI HTTP endpoints for prompts and config
- `src/prompt_store.py` - System prompt file management
- `src/browser_ws_handler.py` - Browser WebSocket voice handler

### Modified Files
- `src/protocol/ws_protocol.py` - Add `build_llm_chunk()`, `build_tts_audio()`
- `src/state_machine.py` - Add cancel handler
- `src/config.py` - Add `prompt_dir`, `http_port` settings
- `src/main.py` - Add asterisk filtering to TTS text processing
- `pyproject.toml` - Add FastAPI, uvicorn, python-multipart dependencies
- `config.yaml` - Add prompt_dir setting

---

## Chunk 1: Dependencies and Configuration

### Task 1: Add Dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add FastAPI and related dependencies**

```toml
dependencies = [
    "websockets>=12.0",
    "pyyaml>=6.0",
    "aiohttp>=3.9.0",
    "edge-tts>=0.2.0",
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "python-multipart>=0.0.6",
    "httpx>=0.26.0",
]
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add FastAPI, uvicorn, python-multipart dependencies"
```

---

### Task 2: Update config.py with New Settings

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: Read current config.py**

```bash
cat src/config.py
```

- [ ] **Step 2: Add http_port to ServerConfig**

```python
@dataclass
class ServerConfig:
    """Server configuration."""
    host: str = "0.0.0.0"
    port: int = 8765
    http_port: int = 8766  # NEW: HTTP API port
    keepalive_timeout: int = 30
```

- [ ] **Step 3: Add prompt_dir to Config**

In the `_load` method, add:
```python
# Load prompt directory
prompt_dir = os.environ.get("PROMPT_DIR", yaml_data.get("prompt_dir", "./prompts"))
```

- [ ] **Step 4: Add PROMPT_DIR to Config dataclass**

```python
@dataclass
class Config:
    """Main configuration class with dataclasses."""
    asr: ASRConfig = field(default_factory=ASRConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    backpressure: BackpressureConfig = field(default_factory=BackpressureConfig)
    prompt_dir: str = "./prompts"  # NEW
```

- [ ] **Step 5: Commit**

```bash
git add src/config.py
git commit -m "feat: add http_port and prompt_dir config settings"
```

---

### Task 3: Update config.yaml

**Files:**
- Modify: `config.yaml`

- [ ] **Step 1: Add prompt_dir to config.yaml**

```yaml
server:
  host: "0.0.0.0"
  port: 8765
  http_port: 8766
  keepalive_timeout: 30

prompt_dir: "./prompts"
```

- [ ] **Step 2: Commit**

```bash
git add config.yaml
git commit -m "feat: add http_port and prompt_dir to config.yaml"
```

---

## Chunk 2: Protocol and State Machine Updates

### Task 4: Add Protocol Message Builders

**Files:**
- Modify: `src/protocol/ws_protocol.py`

- [ ] **Step 1: Read current ws_protocol.py**

```bash
cat src/protocol/ws_protocol.py
```

- [ ] **Step 2: Add build_llm_chunk function**

```python
def build_llm_chunk(text: str, session_id: str, turn_id: int) -> dict:
    """Build an LLM chunk message for browser client.

    Args:
        text: Partial LLM output text
        session_id: Session identifier
        turn_id: Turn identifier

    Returns:
        dict with type='llm_chunk'
    """
    return {
        "type": "llm_chunk",
        "text": text,
        "session_id": session_id,
        "turn_id": turn_id,
    }
```

- [ ] **Step 3: Add build_tts_audio function**

```python
def build_tts_audio(data: str, session_id: str, turn_id: int) -> dict:
    """Build a TTS audio chunk message for browser client.

    Args:
        data: Base64 encoded PCM audio
        session_id: Session identifier
        turn_id: Turn identifier

    Returns:
        dict with type='tts_audio'
    """
    return {
        "type": "tts_audio",
        "data": data,
        "session_id": session_id,
        "turn_id": turn_id,
    }
```

- [ ] **Step 4: Commit**

```bash
git add src/protocol/ws_protocol.py
git commit -m "feat: add build_llm_chunk and build_tts_audio to ws_protocol"
```

---

### Task 5: Add Cancel Handler to State Machine

**Files:**
- Modify: `src/state_machine.py`

- [ ] **Step 1: Read current state_machine.py**

```bash
cat src/state_machine.py
```

- [ ] **Step 2: Add cancel handling method**

Note: Cancel only works between processing turns, not during active ASR/LLM/TTS operations.

```python
def handle_cancel(self) -> None:
    """Handle client cancel request during processing.

    Note: This only cancels between turns, not during active operations.
    """
    if self.state == State.PROCESSING or self.state == State.SPEAKING:
        self.state = State.IDLE
        self.current_turn = None
```

- [ ] **Step 3: Commit**

```bash
git add src/state_machine.py
git commit -m "feat: add cancel handler to state machine"
```

---

## Chunk 3: Prompt Store

### Task 6: Create Prompt Store

**Files:**
- Create: `src/prompt_store.py`

- [ ] **Step 1: Write prompt_store.py with name validation**

```python
"""System prompt file management."""

import os
import re
from pathlib import Path
from typing import List, Optional


class PromptStore:
    """Manages system prompt files on disk."""

    # Valid name pattern: alphanumeric, dash, underscore only
    _VALID_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

    def __init__(self, prompt_dir: str = "./prompts"):
        self.prompt_dir = Path(prompt_dir)
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Create prompt directory if it doesn't exist."""
        self.prompt_dir.mkdir(parents=True, exist_ok=True)

    def _validate_name(self, name: str) -> bool:
        """Validate prompt name to prevent path traversal."""
        return bool(self._VALID_NAME_PATTERN.match(name))

    def list_prompts(self) -> List[str]:
        """List all prompt file names (without extension).

        Returns:
            List of prompt names
        """
        if not self.prompt_dir.exists():
            return []
        return [f.stem for f in self.prompt_dir.iterdir() if f.suffix in (".txt", ".md")]

    def get_prompt(self, name: str) -> Optional[str]:
        """Get prompt content by name.

        Args:
            name: Prompt name (without extension)

        Returns:
            Prompt content or None if not found
        """
        if not self._validate_name(name):
            return None
        for suffix in (".txt", ".md"):
            path = self.prompt_dir / f"{name}{suffix}"
            if path.exists():
                return path.read_text(encoding="utf-8")
        return None

    def save_prompt(self, name: str, content: str) -> None:
        """Save or update a prompt file.

        Args:
            name: Prompt name
            content: Prompt content

        Raises:
            ValueError: If name contains invalid characters
        """
        if not self._validate_name(name):
            raise ValueError(f"Invalid prompt name: {name}")
        self._ensure_dir()
        path = self.prompt_dir / f"{name}.txt"
        path.write_text(content, encoding="utf-8")

    def delete_prompt(self, name: str) -> bool:
        """Delete a prompt file.

        Args:
            name: Prompt name

        Returns:
            True if deleted, False if not found
        """
        if not self._validate_name(name):
            return False
        for suffix in (".txt", ".md"):
            path = self.prompt_dir / f"{name}{suffix}"
            if path.exists():
                path.unlink()
                return True
        return False

    def create_default_prompts(self) -> None:
        """Create default prompt files if none exist."""
        if self.list_prompts():
            return

        defaults = {
            "default": "你是一个友好的语音助手，用简洁的语言回答用户的问题。",
            "creative": "你是一个充满创意的对话伙伴，用生动有趣的方式与用户交流。",
            "formal": "你是一个专业而有礼貌的助手，用正式而清晰的语言回答问题。",
        }

        for name, content in defaults.items():
            self.save_prompt(name, content)
```

- [ ] **Step 2: Commit**

```bash
git add src/prompt_store.py
git commit -m "feat: add prompt_store for system prompt file management"
```

---

## Chunk 4: HTTP API

### Task 7: Create HTTP API Server

**Files:**
- Create: `src/http_api.py`

- [ ] **Step 1: Write http_api.py**

```python
"""FastAPI HTTP API for prompts and configuration."""

import os
from typing import List
from pathlib import Path

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import Config
from src.prompt_store import PromptStore


class PromptCreate(BaseModel):
    name: str
    content: str


class PromptUpdate(BaseModel):
    content: str


class ConfigUpdate(BaseModel):
    voice: str = None
    rate: str = None
    pitch: str = None
    volume: str = None


app = FastAPI(title="Voice Assistant Hub API")

# CORS middleware for React frontend (development only - use explicit origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
config = Config.get_config()


def get_prompt_store() -> PromptStore:
    return PromptStore(prompt_dir=config.prompt_dir)


@app.get("/api/prompts")
def list_prompts() -> List[str]:
    """List all prompt names."""
    store = get_prompt_store()
    return store.list_prompts()


@app.post("/api/prompts")
def create_prompt(prompt: PromptCreate) -> dict:
    """Create a new prompt file."""
    store = get_prompt_store()
    store.save_prompt(prompt.name, prompt.content)
    return {"name": prompt.name, "status": "created"}


@app.get("/api/prompts/{name}")
def get_prompt(name: str) -> dict:
    """Get prompt content."""
    store = get_prompt_store()
    content = store.get_prompt(name)
    if content is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"name": name, "content": content}


@app.put("/api/prompts/{name}")
def update_prompt(name: str, prompt: PromptUpdate) -> dict:
    """Update prompt content."""
    store = get_prompt_store()
    if store.get_prompt(name) is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    store.save_prompt(name, prompt.content)
    return {"name": name, "status": "updated"}


@app.delete("/api/prompts/{name}")
def delete_prompt(name: str) -> dict:
    """Delete a prompt file."""
    store = get_prompt_store()
    if not store.delete_prompt(name):
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"name": name, "status": "deleted"}


@app.get("/api/config")
def get_config() -> dict:
    """Get current configuration."""
    return {
        "tts": {
            "voice": config.tts.voice,
            "rate": config.tts.rate,
            "pitch": config.tts.pitch,
            "volume": config.tts.volume,
        }
    }


@app.put("/api/config")
def update_config(cfg: ConfigUpdate) -> dict:
    """Update configuration (runtime only, not persisted)."""
    if cfg.voice is not None:
        config.tts.voice = cfg.voice
    if cfg.rate is not None:
        config.tts.rate = cfg.rate
    if cfg.pitch is not None:
        config.tts.pitch = cfg.pitch
    if cfg.volume is not None:
        config.tts.volume = cfg.volume
    return {"status": "updated"}


@app.get("/api/status")
def get_status() -> dict:
    """Get pipeline status."""
    return {
        "asr_url": config.asr.base_url,
        "llm_url": config.llm.base_url,
        "llm_model": config.llm.model,
    }


if __name__ == "__main__":
    import uvicorn
    cfg = Config.get_config()
    uvicorn.run(app, host="0.0.0.0", port=cfg.server.http_port)
```

- [ ] **Step 2: Commit**

```bash
git add src/http_api.py
git commit -m "feat: add FastAPI HTTP API for prompts and config"
```

---

## Chunk 5: Browser WebSocket Handler

### Task 8: Create Browser WebSocket Handler

**Files:**
- Create: `src/browser_ws_handler.py`

- [ ] **Step 1: Write browser_ws_handler.py**

```python
"""Browser WebSocket handler for voice pipeline."""

import asyncio
import base64
import json
import logging
import re
from typing import AsyncGenerator

import websockets
from websockets.server import WebSocketServerProtocol

from src.config import Config
from src.pipeline.asr import ASRClient
from src.pipeline.llm import LLMClient
from src.pipeline.tts import TTSClient
from src.protocol.ws_protocol import (
    build_error,
    build_llm_chunk,
    build_state_directive,
    build_tts_audio,
    build_tts_end,
    build_tts_start,
    build_text,
)
from src.state_machine import PendingTurn, State, StateMachine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Emoji pattern (matches common emoji ranges)
EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF]+"
)

# Asterisk pattern for markdown bold/italic
ASTERISK_PATTERN = re.compile(r"\*+([^*]+)\*+")


def filter_tts_text(text: str) -> str:
    """Filter text for TTS: remove emojis, asterisks, extra whitespace."""
    text = EMOJI_PATTERN.sub("", text)
    text = ASTERISK_PATTERN.sub(r"\1", text)
    text = " ".join(text.split())
    return text


async def handle_browser(websocket: WebSocketServerProtocol) -> None:
    """Handle browser WebSocket connection.

    Args:
        websocket: WebSocket connection from browser
    """
    cfg = Config.get_config()

    sm = StateMachine()
    asr = ASRClient(base_url=cfg.asr.base_url)
    llm = LLMClient(
        base_url=cfg.llm.base_url,
        model=cfg.llm.model,
        api_key=getattr(cfg.llm, "api_key", None),
    )
    tts = TTSClient(
        voice=cfg.tts.voice,
        rate=cfg.tts.rate,
        pitch=cfg.tts.pitch,
        volume=cfg.tts.volume,
    )

    session_id = ""
    turn_id = 0
    audio_chunks = []

    try:
        async for message in websocket:
            if isinstance(message, str):
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "audio_start":
                    session_id = data.get("session_id", "browser")
                    turn_id = data.get("turn_id", 1)
                    sm.handle_message({"type": "audio_start", "session_id": session_id, "turn_id": turn_id})
                    audio_chunks = []
                    await websocket.send(json.dumps(build_state_directive(session_id, turn_id, "listening")))

                elif msg_type == "audio_chunk":
                    # Decode base64 audio
                    b64_data = data.get("data", "")
                    if b64_data:
                        audio_bytes = base64.b64decode(b64_data)
                        audio_chunks.append(audio_bytes)

                elif msg_type == "audio_end":
                    sm.handle_message({"type": "audio_end"})
                    await run_browser_pipeline(websocket, sm, asr, llm, tts, session_id, turn_id, audio_chunks)

                elif msg_type == "cancel":
                    sm.handle_cancel()
                    await websocket.send(json.dumps(build_state_directive(session_id, turn_id, "idle")))

            else:
                logger.warning("Received binary data on browser WebSocket - ignored")

    except websockets.exceptions.ConnectionClosed:
        logger.info("Browser disconnected")


async def run_browser_pipeline(
    websocket,
    sm: StateMachine,
    asr: ASRClient,
    llm: LLMClient,
    tts: TTSClient,
    session_id: str,
    turn_id: int,
    audio_chunks: list,
) -> None:
    """Run ASR → LLM → TTS pipeline for browser."""
    if not audio_chunks:
        await websocket.send(json.dumps(build_state_directive(session_id, turn_id, "idle")))
        return

    audio_bytes = b"".join(audio_chunks)

    # ASR
    try:
        asr_result = await asr.recognize(audio_bytes)
        user_text = asr_result.text
    except Exception as e:
        logger.error(f"ASR error: {e}")
        await websocket.send(json.dumps(build_error(str(e), session_id, turn_id)))
        return

    if not user_text:
        await websocket.send(json.dumps(build_state_directive(session_id, turn_id, "idle")))
        return

    await websocket.send(json.dumps(build_text(user_text, session_id, turn_id)))

    # LLM streaming with llm_chunk messages
    messages = [{"role": "user", "content": user_text}]

    text_buffer = ""
    full_response = ""

    try:
        async for token in llm.stream_chat(messages):
            text_buffer += token
            full_response += token

            # Send llm_chunk periodically
            if len(text_buffer) >= 20:
                await websocket.send(json.dumps(build_llm_chunk(text_buffer, session_id, turn_id)))
                text_buffer = ""

        if text_buffer:
            await websocket.send(json.dumps(build_llm_chunk(text_buffer, session_id, turn_id)))

    except Exception as e:
        logger.error(f"LLM error: {e}")
        await websocket.send(json.dumps(build_error(str(e), session_id, turn_id)))
        return

    # TTS synthesis
    filtered_text = filter_tts_text(full_response)
    if not filtered_text.strip():
        await websocket.send(json.dumps(build_state_directive(session_id, turn_id, "idle")))
        return

    await websocket.send(json.dumps(build_tts_start(session_id, turn_id, sample_rate=16000, format="pcm_s16le", channels=1)))

    try:
        async for audio_chunk in tts.synthesize(filtered_text):
            b64_audio = base64.b64encode(audio_chunk).decode()
            await websocket.send(json.dumps(build_tts_audio(b64_audio, session_id, turn_id)))

        await websocket.send(json.dumps(build_tts_end(session_id, turn_id)))

    except Exception as e:
        logger.error(f"TTS error: {e}")
        await websocket.send(json.dumps(build_error(str(e), session_id, turn_id)))
```

- [ ] **Step 2: Commit**

```bash
git add src/browser_ws_handler.py
git commit -m "feat: add browser WebSocket handler for voice pipeline"
```

---

## Chunk 6: Update Main.py and Dockerfile

### Task 9: Add HTTP API Server Startup to Main

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Read main.py to find where to add startup**

```bash
head -50 src/main.py
```

- [ ] **Step 2: Add HTTP API startup in main()**

Add to the imports:
```python
import threading
from src.http_api import app as http_app
import uvicorn
```

Modify main():
```python
async def main() -> None:
    """Start the WebSocket server and HTTP API."""
    cfg = Config.get_config()

    # Start HTTP API in background thread
    def run_http():
        uvicorn.run(http_app, host="0.0.0.0", port=cfg.server.http_port, log_level="info")

    http_thread = threading.Thread(target=run_http, daemon=True)
    http_thread.start()

    logger.info(f"Starting WebSocket server on {cfg.server.host}:{cfg.server.port}")
    async with websockets.serve(handle_esp32, cfg.server.host, cfg.server.port, ping_interval=None):
        await asyncio.Future()  # Run forever
```

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: add HTTP API server startup alongside WebSocket"
```

---

### Task 10: Update Dockerfile for FastAPI

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Update Dockerfile to include FastAPI dependencies and expose port 8766**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    edge-tts \
    websockets \
    pyyaml \
    aiohttp \
    pydantic \
    httpx \
    pytest \
    pytest-asyncio \
    fastapi \
    uvicorn[standard] \
    python-multipart

COPY src/ ./src/
COPY config.yaml .

EXPOSE 8765 8766

CMD ["python", "-m", "src.main"]
```

- [ ] **Step 2: Update docker-compose.yml to expose port 8766**

Add to python-hub service:
```yaml
ports:
  - "8765:8765"
  - "8766:8766"
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "chore: update Dockerfile for FastAPI and expose port 8766"
```

---

## Verification

### Task 11: Test HTTP API

- [ ] **Step 1: Start containers and test**

```bash
docker compose up -d
sleep 5
curl http://localhost:8766/api/prompts
curl http://localhost:8766/api/status
curl http://localhost:8766/api/config
```

Expected: JSON responses

### Task 12: Test Browser WebSocket

- [ ] **Step 1: Write and run browser test**

```python
import asyncio
import websockets
import json
import base64

async def test():
    async with websockets.connect("ws://localhost:8765") as ws:
        await ws.send(json.dumps({"type": "audio_start", "session_id": "test", "turn_id": 1}))
        resp = await ws.recv()
        print(resp)

asyncio.run(test())
```

---

## Summary

**Files created:**
- `src/http_api.py` - FastAPI HTTP endpoints
- `src/prompt_store.py` - Prompt file management
- `src/browser_ws_handler.py` - Browser WebSocket handler

**Files modified:**
- `pyproject.toml` - Added dependencies
- `src/config.py` - Added http_port, prompt_dir
- `src/protocol/ws_protocol.py` - Added build_llm_chunk, build_tts_audio
- `src/state_machine.py` - Added cancel handler
- `config.yaml` - Added new settings
- `src/main.py` - Added HTTP API startup
- `Dockerfile` - Updated for FastAPI
