# Voice Assistant Python Hub Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python Hub service — a流式语音助手中枢 with KWS/VAD/ASR/LLM/TTS pipeline and WebSocket interface for ESP32.

**Architecture:** Four-state machine (SLEEPING/LISTENING/PROCESSING/SPEAKING) driving异步流式流水线. LLM调用和TTS生成并行 through asyncio.Queue. 全栈纯CPU，GPU only for LLM.

**Tech Stack:** Python 3.10, websockets, sherpa-onnx, silero-vad, openai, pyyaml, aiofiles

---

## Chunk 1: Project Scaffolding

### Task 1: Create project directory structure

**Files:**
- Create: `src/__init__.py`
- Create: `src/pipeline/__init__.py`
- Create: `src/memory/__init__.py`
- Create: `src/protocol/__init__.py`
- Create: `src/utils/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/pipeline/__init__.py`
- Create: `tests/memory/__init__.py`
- Create: `tests/protocol/__init__.py`
- Create: `tests/utils/__init__.py`
- Create: `config.yaml`
- Create: `requirements.txt`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `models/.gitkeep`
- Create: `memory/sessions/.gitkeep`
- Create: `memory/summaries/.gitkeep`

- [ ] **Step 1: Create all directories and placeholder files**

Run:
```bash
mkdir -p src/pipeline src/memory src/protocol src/utils tests/pipeline tests/memory tests/protocol tests/utils models memory/sessions memory/summaries
touch src/__init__.py src/pipeline/__init__.py src/memory/__init__.py src/protocol/__init__.py src/utils/__init__.py tests/__init__.py tests/pipeline/__init__.py tests/memory/__init__.py tests/protocol/__init__.py tests/utils/__init__.py models/.gitkeep memory/sessions/.gitkeep memory/summaries/.gitkeep
```

- [ ] **Step 2: Write config.yaml**

```yaml
# config.yaml
server:
  host: "0.0.0.0"
  port: 8765
  keepalive_timeout: 30

llm:
  base_url: "http://llama-server:8080/v1"
  model: "unsloth/gemma-4-E4B-it-GGUF:Q8_0"
  max_tokens: 512
  temperature: 0.7

asr:
  model_dir: "/app/models/asr"

tts:
  mode: "streaming"
  model_dir: "/app/models/tts"
  sentence_delimiters: ["。", "！", "？", "\n", "."]
  max_buffer_chars: 200
  first_chunk_timeout: 2.0

kws:
  model_dir: "/app/models/kws"
  threshold: 0.5

vad:
  model_dir: "/app/models/vad"
  silence_threshold: 0.8

memory:
  session_dir: "/app/memory/sessions"
  summary_dir: "/app/memory/summaries"
  max_rounds: 5
  idle_timeout: 120
  max_recent_summaries: 3

backpressure:
  asr_queue_max: 100
  tts_queue_max: 50
  llm_queue_max: 20
```

- [ ] **Step 3: Write requirements.txt**

```
websockets>=12.0
sherpa-onnx>=1.0
silero-vad
openai>=1.0
pyyaml
aiofiles
pytest>=7.0
pytest-asyncio>=0.21
```

- [ ] **Step 4: Write Dockerfile**

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config.yaml .

RUN mkdir -p /app/models /app/memory/sessions /app/memory/summaries

CMD ["python", "-m", "src.main"]
```

- [ ] **Step 5: Write docker-compose.yml**

```yaml
services:
  llama-server:
    image: llama-cpp-sycl-server:latest
    container_name: llama-server
    ports:
      - "8080:8080"
    environment:
      - DEVICE=SYCL
      - ONEAPI_DEVICE_SELECTOR=level_zero:0
    deploy:
      resources:
        reservations:
          devices:
            - driver: level-zero
              device: 0
              capabilities: [gpu]
    restart: unless-stopped

  python-hub:
    build: .
    container_name: python-hub
    ports:
      - "8765:8765"
    volumes:
      - /path/to/models:/app/models
      - ./memory:/app/memory
    environment:
      - LLM_BASE_URL=http://llama-server:8080/v1
      - LLM_MODEL=unsloth/gemma-4-E4B-it-GGUF:Q8_0
    depends_on:
      - llama-server
    deploy:
      resources:
        limits:
          memory: "2g"
        reservations:
          memory: "512m"
    restart: unless-stopped
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "chore: project scaffolding with config, docker, requirements"
```

---

## Chunk 2: State Machine

### Task 2: State machine core

**Files:**
- Create: `src/state_machine.py`
- Create: `tests/test_state_machine.py`

- [ ] **Step 1: Write failing test for StateMachine**

```python
# tests/test_state_machine.py
import pytest
from enum import Enum
from src.state_machine import State, StateMachine, StateEvent

def test_initial_state_is_sleeping():
    sm = StateMachine()
    assert sm.state == State.SLEEPING

def test_kws_trigger_transitions_to_listening():
    sm = StateMachine()
    sm.handle_event(StateEvent.KWS_TRIGGER)
    assert sm.state == State.LISTENING

def test_vad_silence_transitions_to_processing():
    sm = StateMachine()
    sm.handle_event(StateEvent.KWS_TRIGGER)
    sm.handle_event(StateEvent.VAD_SILENCE)
    assert sm.state == State.PROCESSING

def test_tts_ready_transitions_to_speaking():
    sm = StateMachine()
    sm.handle_event(StateEvent.KWS_TRIGGER)
    sm.handle_event(StateEvent.VAD_SILENCE)
    sm.handle_event(StateEvent.TTS_READY)
    assert sm.state == State.SPEAKING

def test_playback_done_returns_to_sleeping():
    sm = StateMachine()
    sm.handle_event(StateEvent.KWS_TRIGGER)
    sm.handle_event(StateEvent.VAD_SILENCE)
    sm.handle_event(StateEvent.TTS_READY)
    sm.handle_event(StateEvent.PLAYBACK_DONE)
    assert sm.state == State.SLEEPING

def test_kws_from_processing_interrupts():
    sm = StateMachine()
    sm.handle_event(StateEvent.KWS_TRIGGER)
    sm.handle_event(StateEvent.VAD_SILENCE)
    sm.handle_event(StateEvent.KWS_TRIGGER)  # interrupt mid-processing
    assert sm.state == State.LISTENING

def test_kws_from_speaking_interrupts():
    sm = StateMachine()
    sm.handle_event(StateEvent.KWS_TRIGGER)
    sm.handle_event(StateEvent.VAD_SILENCE)
    sm.handle_event(StateEvent.TTS_READY)
    sm.handle_event(StateEvent.KWS_TRIGGER)  # interrupt mid-speaking
    assert sm.state == State.LISTENING
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_state_machine.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: Write minimal StateMachine**

```python
# src/state_machine.py
from enum import Enum, auto

class State(Enum):
    SLEEPING = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()

class StateEvent(Enum):
    KWS_TRIGGER = auto()
    VAD_SILENCE = auto()
    TTS_READY = auto()
    PLAYBACK_DONE = auto()

class StateMachine:
    def __init__(self):
        self.state = State.SLEEPING

    def handle_event(self, event: StateEvent):
        if self.state == State.SLEEPING:
            if event == StateEvent.KWS_TRIGGER:
                self.state = State.LISTENING
        elif self.state == State.LISTENING:
            if event == StateEvent.VAD_SILENCE:
                self.state = State.PROCESSING
            elif event == StateEvent.KWS_TRIGGER:
                self.state = State.LISTENING  # already here
        elif self.state == State.PROCESSING:
            if event == StateEvent.TTS_READY:
                self.state = State.SPEAKING
            elif event == StateEvent.KWS_TRIGGER:
                self.state = State.LISTENING  # interrupt
        elif self.state == State.SPEAKING:
            if event == StateEvent.PLAYBACK_DONE:
                self.state = State.SLEEPING
            elif event == StateEvent.KWS_TRIGGER:
                self.state = State.LISTENING  # interrupt
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_state_machine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_state_machine.py src/state_machine.py
git commit -m "feat: add StateMachine with 4 states and KWS interrupt"
```

---

## Chunk 3: Pipeline Modules

### Task 3: Config loader

**Files:**
- Create: `src/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
import pytest
from src.config import Config

def test_config_loads_defaults(tmp_path):
    cfg = Config()
    assert cfg.server["port"] == 8765
    assert cfg.llm["model"] == "unsloth/gemma-4-E4B-it-GGUF:Q8_0"
    assert cfg.tts["mode"] == "streaming"
    assert cfg.tts["max_buffer_chars"] == 200
    assert cfg.vad["silence_threshold"] == 0.8
    assert cfg.memory["max_rounds"] == 5
    assert cfg.backpressure["asr_queue_max"] == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: Write minimal config loader**

```python
# src/config.py
import yaml
from pathlib import Path

class Config:
    _instance = None

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path) as f:
            self._data = yaml.safe_load(f)

    @classmethod
    def get_instance(cls, config_path: str = None):
        if cls._instance is None:
            cls._instance = cls(config_path)
        return cls._instance

    @property
    def server(self): return self._data.get("server", {})
    @property
    def llm(self): return self._data.get("llm", {})
    @property
    def asr(self): return self._data.get("asr", {})
    @property
    def tts(self): return self._data.get("tts", {})
    @property
    def kws(self): return self._data.get("kws", {})
    @property
    def vad(self): return self._data.get("vad", {})
    @property
    def memory(self): return self._data.get("memory", {})
    @property
    def backpressure(self): return self._data.get("backpressure", {})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_config.py src/config.py
git commit -m "feat: add Config singleton with yaml loading"
```

### Task 4: KWS module (stub)

**Files:**
- Create: `src/pipeline/kws.py`
- Create: `tests/pipeline/test_kws.py`

- [ ] **Step 1: Write failing test**

```python
# tests/pipeline/test_kws.py
import pytest
from src.pipeline.kws import KWSDetector

def test_kws_detector_initializes():
    detector = KWSDetector(model_dir="/fake/path")
    assert detector.threshold == 0.5

def test_kws_detector_process_returns_float():
    detector = KWSDetector(model_dir="/fake/path")
    # 16kHz, 16-bit, 480 samples (~30ms frame)
    fake_pcm = b"\x00" * 480 * 2
    score = detector.detect(fake_pcm)
    assert isinstance(score, float)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_kws.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: Write KWS stub**

```python
# src/pipeline/kws.py
import numpy as np

class KWSDetector:
    def __init__(self, model_dir: str, threshold: float = 0.5):
        self.model_dir = model_dir
        self.threshold = threshold

    def detect(self, pcm_bytes: bytes) -> float:
        """Return wake word confidence score 0.0-1.0"""
        # Stub: return 0.0 (no wake detected)
        return 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_kws.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/pipeline/test_kws.py src/pipeline/kws.py
git commit -m "feat: add KWS stub detector"
```

### Task 5: VAD module (stub)

**Files:**
- Create: `src/pipeline/vad.py`
- Create: `tests/pipeline/test_vad.py`

- [ ] **Step 1: Write failing test**

```python
# tests/pipeline/test_vad.py
from src.pipeline.vad import VADDetector

def test_vad_detector_initializes():
    detector = VADDetector(model_dir="/fake/path")
    assert detector.silence_threshold == 0.8

def test_vad_detect_returns_speech():
    detector = VADDetector(model_dir="/fake/path")
    fake_pcm = b"\x00" * 480 * 2
    result = detector.detect(fake_pcm)
    assert result in [True, False]  # is_speech
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_vad.py -v`
Expected: FAIL

- [ ] **Step 3: Write VAD stub**

```python
# src/pipeline/vad.py

class VADDetector:
    def __init__(self, model_dir: str, silence_threshold: float = 0.8):
        self.model_dir = model_dir
        self.silence_threshold = silence_threshold

    def detect(self, pcm_bytes: bytes) -> bool:
        """Return True if speech detected, False if silence"""
        # Stub: return True (assume speech)
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_vad.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/pipeline/test_vad.py src/pipeline/vad.py
git commit -m "feat: add VAD stub detector"
```

### Task 6: ASR module (stub)

**Files:**
- Create: `src/pipeline/asr.py`
- Create: `tests/pipeline/test_asr.py`

- [ ] **Step 1: Write failing test**

```python
# tests/pipeline/test_asr.py
import asyncio
from src.pipeline.asr import ASRRecognizer

def test_asr_recognizer_initializes():
    recognizer = ASRRecognizer(model_dir="/fake/path")
    assert recognizer.streaming == True

def test_asr_recognize_from_pcm():
    recognizer = ASRRecognizer(model_dir="/fake/path")
    fake_pcm = b"\x00" * 4800 * 2  # 300ms
    text = recognizer.recognize(fake_pcm)
    assert isinstance(text, str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_asr.py -v`
Expected: FAIL

- [ ] **Step 3: Write ASR stub**

```python
# src/pipeline/asr.py

class ASRRecognizer:
    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self.streaming = True

    def recognize(self, pcm_bytes: bytes) -> str:
        """Recognize speech from PCM bytes, return text"""
        # Stub: return empty string
        return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_asr.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/pipeline/test_asr.py src/pipeline/asr.py
git commit -m "feat: add ASR stub recognizer"
```

### Task 7: LLM module (stub)

**Files:**
- Create: `src/pipeline/llm.py`
- Create: `tests/pipeline/test_llm.py`

- [ ] **Step 1: Write failing test**

```python
# tests/pipeline/test_llm.py
import asyncio
from src.pipeline.llm import LLMClient

def test_llm_client_initializes():
    client = LLMClient(base_url="http://localhost:8080/v1", model="test")
    assert client.base_url == "http://localhost:8080/v1"

def test_llm_stream_generator():
    client = LLMClient(base_url="http://localhost:8080/v1", model="test")
    async def consume():
        tokens = []
        async for token in client.stream_chat(["hello"]):
            tokens.append(token)
        return tokens
    tokens = asyncio.run(consume())
    assert isinstance(tokens, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_llm.py -v`
Expected: FAIL

- [ ] **Step 3: Write LLM stub**

```python
# src/pipeline/llm.py
import asyncio

class LLMClient:
    def __init__(self, base_url: str, model: str, api_key: str = None):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key

    async def stream_chat(self, messages: list, system: str = None) -> async generator:
        """Yield LLM tokens one by one"""
        # Stub: yield nothing
        return
        yield  # make it an async generator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/pipeline/test_llm.py src/pipeline/llm.py
git commit -m "feat: add LLM client stub"
```

### Task 8: TTS module (stub)

**Files:**
- Create: `src/pipeline/tts.py`
- Create: `tests/pipeline/test_tts.py`

- [ ] **Step 1: Write failing test**

```python
# tests/pipeline/test_tts.py
import asyncio
from src.pipeline.tts import TTSGenerator

def test_tts_generator_initializes():
    gen = TTSGenerator(model_dir="/fake/path")
    assert gen.mode == "streaming"

async def consume_audio():
    gen = TTSGenerator(model_dir="/fake/path")
    chunks = []
    async for chunk in gen.generate("hello"):
        chunks.append(chunk)
    return chunks

def test_tts_generate_returns_chunks():
    chunks = asyncio.run(consume_audio())
    assert isinstance(chunks, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_tts.py -v`
Expected: FAIL

- [ ] **Step 3: Write TTS stub**

```python
# src/pipeline/tts.py
import asyncio

class TTSGenerator:
    def __init__(self, model_dir: str, mode: str = "streaming"):
        self.model_dir = model_dir
        self.mode = mode

    async def generate(self, text: str):
        """Yield PCM audio chunks for given text"""
        return
        yield  # make it an async generator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_tts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/pipeline/test_tts.py src/pipeline/tts.py
git commit -m "feat: add TTS stub generator"
```

---

## Chunk 4: Memory Module

### Task 9: Session manager

**Files:**
- Create: `src/memory/session.py`
- Create: `tests/memory/test_session.py`

- [ ] **Step 1: Write failing test**

```python
# tests/memory/test_session.py
from src.memory.session import Session, Message

def test_session_starts_empty():
    session = Session()
    assert len(session.messages) == 0

def test_session_add_user_message():
    session = Session()
    session.add_user("hello")
    assert len(session.messages) == 1
    assert session.messages[0].role == "user"

def test_session_add_assistant_message():
    session = Session()
    session.add_assistant("hi there")
    assert session.messages[0].role == "assistant"

def test_session_round_count():
    session = Session()
    session.add_user("hello")
    session.add_assistant("hi")
    assert session.round_count == 1  # one user+assistant pair
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/memory/test_session.py -v`
Expected: FAIL

- [ ] **Step 3: Write Session**

```python
# src/memory/session.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import uuid

@dataclass
class Message:
    role: str
    content: str

class Session:
    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.messages: list[Message] = []
        self.created_at = datetime.now()

    @property
    def round_count(self) -> int:
        return len([m for m in self.messages if m.role == "user"])

    def add_user(self, content: str):
        self.messages.append(Message(role="user", content=content))

    def add_assistant(self, content: str):
        self.messages.append(Message(role="assistant", content=content))

    def clear(self):
        self.messages.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/memory/test_session.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/memory/test_session.py src/memory/session.py
git commit -m "feat: add Session model with messages"
```

### Task 10: Summarizer

**Files:**
- Create: `src/memory/summarizer.py`
- Create: `tests/memory/test_summarizer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/memory/test_summarizer.py
import pytest
from src.memory.summarizer import Summarizer, SUMMARY_TEMPLATE
from src.memory.session import Session, Message

def test_summarizer_builds_prompt():
    session = Session()
    session.add_user("今天天气怎么样？")
    session.add_assistant("今天是晴天，气温25度。")
    session.add_user("谢谢")
    session.add_assistant("不客气！")
    summarizer = Summarizer(llm_client=None)
    prompt = summarizer._build_summary_prompt(session.messages)
    assert "今天天气怎么样？" in prompt
    assert "谢谢" in prompt

def test_summarizer_format_md():
    content = "- 用户询问天气，已告知晴天"
    md = Summarizer.format_summary_md("2026-04-21", content)
    assert "2026-04-21" in md
    assert "用户询问天气" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/memory/test_summarizer.py -v`
Expected: FAIL

- [ ] **Step 3: Write Summarizer**

```python
# src/memory/summarizer.py
from datetime import datetime
from pathlib import Path
import aiofiles

SUMMARY_TEMPLATE = """请将以下对话精简为3句话的摘要，保留关键信息（人名、偏好、承诺的事项）：
---
{conversation}
---"""

class Summarizer:
    def __init__(self, llm_client, summary_dir: str = "/app/memory/summaries"):
        self.llm_client = llm_client
        self.summary_dir = Path(summary_dir)

    def _build_summary_prompt(self, messages: list) -> str:
        conversation = "\n".join(f"{m.role}: {m.content}" for m in messages)
        return SUMMARY_TEMPLATE.format(conversation=conversation)

    @staticmethod
    def format_summary_md(date: str, content: str) -> str:
        return f"""=== {date} 会话摘要 ===
{content}
=================="""

    async def save_summary(self, date: str, content: str):
        self.summary_dir.mkdir(parents=True, exist_ok=True)
        path = self.summary_dir / f"{date}.md"
        md = self.format_summary_md(date, content)
        async with aiofiles.open(path, "a") as f:
            await f.write(md + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/memory/test_summarizer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/memory/test_summarizer.py src/memory/summarizer.py
git commit -m "feat: add Summarizer with prompt building and MD formatting"
```

---

## Chunk 5: WebSocket Protocol

### Task 11: WS Protocol

**Files:**
- Create: `src/protocol/ws_protocol.py`
- Create: `tests/protocol/test_ws_protocol.py`

- [ ] **Step 1: Write failing test**

```python
# tests/protocol/test_ws_protocol.py
import json
from src.protocol.ws_protocol import StateDirective, parse_directive, build_directive

def test_parse_listening_directive():
    msg = json.dumps({"state": "listening"})
    directive = parse_directive(msg)
    assert directive == StateDirective.LISTENING

def test_parse_thinking_directive():
    directive = parse_directive('{"state": "thinking"}')
    assert directive == StateDirective.THINKING

def test_parse_idle_directive():
    directive = parse_directive('{"state": "idle"}')
    assert directive == StateDirective.IDLE

def test_build_directive_speaking():
    msg = build_directive(StateDirective.SPEAKING)
    assert '"state": "speaking"' in msg

def test_build_directive_error():
    msg = build_directive(StateDirective.ERROR, message="test error")
    assert "error" in msg
    assert "test error" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/protocol/test_ws_protocol.py -v`
Expected: FAIL

- [ ] **Step 3: Write WS Protocol**

```python
# src/protocol/ws_protocol.py
import json
from enum import Enum

class StateDirective(Enum):
    LISTENING = "listening"
    THINKING = "thinking"
    IDLE = "idle"
    SPEAKING = "speaking"
    ERROR = "error"

def parse_directive(raw: str) -> StateDirective:
    try:
        obj = json.loads(raw)
        state = obj.get("state", "")
        return StateDirective(state)
    except (json.JSONDecodeError, ValueError):
        return StateDirective.ERROR

def build_directive(directive: StateDirective, message: str = None) -> str:
    if directive == StateDirective.ERROR:
        obj = {"state": "error"}
        if message:
            obj["message"] = message
    else:
        obj = {"state": directive.value}
    return json.dumps(obj)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/protocol/test_ws_protocol.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/protocol/test_ws_protocol.py src/protocol/ws_protocol.py
git commit -m "feat: add WS protocol with state directives"
```

---

## Chunk 6: Audio Utils

### Task 12: Audio utils

**Files:**
- Create: `src/utils/audio.py`
- Create: `tests/utils/test_audio.py`

- [ ] **Step 1: Write failing test**

```python
# tests/utils/test_audio.py
from src.utils.audio import validate_pcm_chunk, generate_silence_chunk

def test_validate_pcm_chunk_correct_size():
    # 1024 bytes = 512 samples = 16ms at 16kHz
    chunk = b"\x00" * 1024
    assert validate_pcm_chunk(chunk, expected_samples=512) == True

def test_validate_pcm_chunk_wrong_size():
    chunk = b"\x00" * 100  # wrong size
    assert validate_pcm_chunk(chunk, expected_samples=512) == False

def test_generate_silence_chunk():
    chunk = generate_silence_chunk(sample_count=512)
    assert len(chunk) == 1024  # 512 samples * 2 bytes
    assert all(b == 0 for b in chunk)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/utils/test_audio.py -v`
Expected: FAIL

- [ ] **Step 3: Write Audio utils**

```python
# src/utils/audio.py

def validate_pcm_chunk(chunk: bytes, expected_samples: int) -> bool:
    """Validate chunk is the expected size for 16-bit mono PCM"""
    expected_bytes = expected_samples * 2  # 16-bit = 2 bytes per sample
    return len(chunk) == expected_bytes

def generate_silence_chunk(sample_count: int) -> bytes:
    """Generate silence PCM chunk (all zeros)"""
    return b"\x00" * (sample_count * 2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/utils/test_audio.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/utils/test_audio.py src/utils/audio.py
git commit -m "feat: add audio utils for PCM validation and silence generation"
```

---

## Chunk 7: Integration — Main WebSocket Server

### Task 13: Main WebSocket server

**Files:**
- Create: `src/main.py`
- Create: `tests/test_main.py` (integration)

- [ ] **Step 1: Write failing test**

```python
# tests/test_main.py
import asyncio
import websockets
import json

async def test_ws_connection_established():
    uri = "ws://localhost:8765"
    try:
        async with websockets.connect(uri, ping_interval=None) as ws:
            await ws.send(json.dumps({"type": "ping"}))
            # If we get here, server is running
            assert True
    except Exception as e:
        pytest.fail(f"Cannot connect to server: {e}")

def test_main_module_imports():
    from src.main import app
    assert app is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: Write WebSocket server main.py**

```python
# src/main.py
import asyncio
import logging
import websockets
from websockets.server import WebSocketServerProtocol

from src.config import Config
from src.state_machine import StateMachine, StateEvent, State
from src.pipeline.kws import KWSDetector
from src.pipeline.vad import VADDetector
from src.pipeline.asr import ASRRecognizer
from src.pipeline.llm import LLMClient
from src.pipeline.tts import TTSGenerator
from src.memory.session import Session
from src.memory.summarizer import Summarizer
from src.protocol.ws_protocol import StateDirective, parse_directive, build_directive
from src.utils.audio import generate_silence_chunk

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global queues for pipeline stages
asr_queue: asyncio.Queue = None
llm_token_queue: asyncio.Queue = None
tts_audio_queue: asyncio.Queue = None

# Interrupt flag
interrupt_event: asyncio.Event = None

async def handle_esp32(websocket: WebSocketServerProtocol, path: str):
    global asr_queue, llm_token_queue, tts_audio_queue, interrupt_event

    cfg = Config.get_instance()
    sm = StateMachine()
    session = Session()
    interrupt_event = asyncio.Event()

    await websocket.send(build_directive(StateDirective.IDLE))
    logger.info(f"ESP32 connected: {websocket.remote_address}")

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Binary: PCM audio chunk
                await asr_queue.put(message)
            elif isinstance(message, str):
                # Text: JSON directive from ESP32 (future use)
                pass
    except websockets.exceptions.ConnectionClosed:
        logger.info("ESP32 disconnected")
    finally:
        interrupt_event.set()  # signal all pipelines to stop
        asr_queue = None
        llm_token_queue = None
        tts_audio_queue = None

async def main():
    cfg = Config.get_instance()
    host = cfg.server.get("host", "0.0.0.0")
    port = cfg.server.get("port", 8765)

    logger.info(f"Starting WebSocket server on {host}:{port}")
    async with websockets.serve(handle_esp32, host, port, ping_interval=None):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run import test**

Run: `pytest tests/test_main.py::test_main_module_imports -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_main.py src/main.py
git commit -m "feat: add main WebSocket server entry point"
```

---

## Chunk 8: Pipeline Integration — KWS/VAD/ASR/LLM/TTS wiring

### Task 14: Wire pipeline stages

This is the core integration chunk — connecting all pipeline stubs into a working streaming pipeline.

**Files:**
- Modify: `src/main.py`
- Create: `tests/test_pipeline_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_pipeline_integration.py
import asyncio
from src.pipeline.kws import KWSDetector
from src.pipeline.vad import VADDetector
from src.pipeline.asr import ASRRecognizer

def test_full_pipeline_stages_initialized():
    kws = KWSDetector(model_dir="/fake")
    vad = VADDetector(model_dir="/fake")
    asr = ASRRecognizer(model_dir="/fake")
    assert kws.threshold > 0
    assert vad.silence_threshold > 0
    assert asr.streaming == True
```

- [ ] **Step 2: Run to verify pipeline is wired (test passes with stubs)**

Run: `pytest tests/test_pipeline_integration.py -v`

- [ ] **Step 3: Implement full pipeline runner in main.py**

Replace the stub main.py with actual pipeline wiring (expand the handle_esp32 function to wire all stages). This is the big integration step — connect KWS → VAD → ASR → LLM → TTS with proper asyncio queues and interrupt handling.

- [ ] **Step 4: Run integration tests**

Run: `pytest tests/ -v`

- [ ] **Step 5: Commit with detailed message**

---

## Chunk 9: Real model integration (when models are available)

### Task 15: Replace stubs with real sherpa-onnx / silero-vad

**Files:**
- Modify: `src/pipeline/kws.py`, `src/pipeline/vad.py`, `src/pipeline/asr.py`, `src/pipeline/tts.py`
- Add: `tests/` for each real model

Real model integration — when models are downloaded, swap stubs for actual sherpa-onnx/silero-vad calls.

---

## Chunk 10: End-to-end test with ESP32 simulator

### Task 16: ESP32 simulator for testing

**Files:**
- Create: `tests/test_esp32_simulator.py`

Simulates an ESP32 client connecting via WebSocket, sending PCM chunks, and receiving TTS audio — used for manual/automated testing without real hardware.

---

**Total tasks: 16 tasks across 10 chunks**
**Execution order:** Chunk 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10
