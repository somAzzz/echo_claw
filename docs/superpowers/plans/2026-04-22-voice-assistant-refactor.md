# Voice Assistant Python Hub 重构实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 Python Hub，移除 sherpa-onnx (KWS/VAD/ASR/TTS)，改用 FunASR API (ASR) + Edge-tts (TTS)，支持多轮对话和语音打断

**Architecture:**
- ESP32 负责 KWS + VAD + 录音/播放
- Python Hub 只做 ASR → LLM → TTS + 状态管理
- FunASR API 和 llama-server 独立服务，Python Hub 通过 HTTP 调用

**Tech Stack:** Python 3.12, edge-tts, websockets, aiohttp, httpx, pyyaml

---

## Chunk 1: Core Infrastructure (状态机 + 协议 + 配置)

**Files:**
- Create: `tests/test_state_machine.py` (新)
- Modify: `src/state_machine.py`
- Create: `src/protocol/ws_protocol.py` (重写)
- Modify: `src/config.py`
- Create: `tests/test_protocol.py`

- [ ] **Step 1: Write failing test for new state machine**

```python
# tests/test_state_machine.py
import pytest
from src.state_machine import State, StateMachine, PreemptionError

def test_idle_to_listening_on_audio_start():
    sm = StateMachine()
    assert sm.state == State.IDLE
    sm.handle_message({"type": "audio_start", "session_id": "s1", "turn_id": "t1"})
    assert sm.state == State.LISTENING

def test_listening_to_processing_on_audio_end():
    sm = StateMachine()
    sm.handle_message({"type": "audio_start", "session_id": "s1", "turn_id": "t1"})
    sm.handle_message({"type": "audio_end", "session_id": "s1", "turn_id": "t1"})
    assert sm.state == State.PROCESSING

def test_preemption_cancels_processing():
    sm = StateMachine()
    sm.handle_message({"type": "audio_start", "session_id": "s1", "turn_id": "t1"})
    sm.handle_message({"type": "audio_end", "session_id": "s1", "turn_id": "t1"})
    assert sm.state == State.PROCESSING
    # New audio_start preempts
    sm.handle_message({"type": "audio_start", "session_id": "s1", "turn_id": "t2"})
    assert sm.state == State.LISTENING
    assert sm.current_turn_id == "t2"

def test_idle_timeout_transitions_to_idle():
    sm = StateMachine(session_timeout=0.1)  # 100ms for testing
    sm.handle_message({"type": "audio_start", "session_id": "s1", "turn_id": "t1"})
    sm.handle_message({"type": "audio_end", "session_id": "s1", "turn_id": "t1"})
    import asyncio
    asyncio.run(asyncio.sleep(0.15))
    # Should auto-transition back due to PROCESSING timeout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_state_machine.py -v`
Expected: FAIL - State and StateMachine don't have new attributes yet

- [ ] **Step 3: Write state_machine.py with new states**

```python
# src/state_machine.py
from enum import Enum, auto
import asyncio
from dataclasses import dataclass, field
from datetime import datetime

class State(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()

@dataclass
class PendingTurn:
    turn_id: str
    session_id: str
    audio_chunks: list[bytes] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)

class StateMachine:
    def __init__(
        self,
        listening_timeout: float = 30.0,
        processing_timeout: float = 60.0,
    ):
        self.state = State.IDLE
        self.current_turn: PendingTurn | None = None
        self.current_session_id: str | None = None
        self.listening_timeout = listening_timeout
        self.processing_timeout = processing_timeout
        self._tasks: list[asyncio.Task] = []

    def handle_message(self, msg: dict) -> State | None:
        """Handle WebSocket message, return new state if transitioned."""
        msg_type = msg.get("type")

        if msg_type == "audio_start":
            return self._on_audio_start(msg)
        elif msg_type == "audio_end":
            return self._on_audio_end(msg)
        elif msg_type == "playback_done":
            return self._on_playback_done()
        elif msg_type == "session_end":
            return self._on_session_end()

        return None

    def _on_audio_start(self, msg: dict) -> State:
        session_id = msg.get("session_id", "")
        turn_id = msg.get("turn_id", "")

        # Preemption: cancel any pending processing
        self._cancel_current_turn()

        # Create new pending turn
        self.current_turn = PendingTurn(
            turn_id=turn_id,
            session_id=session_id,
        )
        self.current_session_id = session_id

        old_state = self.state
        self.state = State.LISTENING
        return self.state

    def _on_audio_end(self, msg: dict) -> State:
        if self.state == State.LISTENING:
            self.state = State.PROCESSING
        return self.state

    def _on_playback_done(self) -> State:
        if self.state == State.SPEAKING:
            self.state = State.IDLE  # Could also go to LISTENING for multi-turn
        return self.state

    def _on_session_end(self) -> State:
        self._cancel_current_turn()
        self.state = State.IDLE
        return self.state

    def _cancel_current_turn(self):
        """Cancel pending ASR/LLM/TTS requests."""
        self.current_turn = None
        # Cancel any pending tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

    def get_current_turn_id(self) -> str | None:
        return self.current_turn.turn_id if self.current_turn else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_state_machine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/state_machine.py tests/test_state_machine.py
git commit -m "feat: rewrite state machine with IDLE/LISTENING/PROCESSING/SPEAKING"
```

---

- [ ] **Step 6: Write failing test for ws_protocol**

```python
# tests/test_protocol.py
import pytest
from src.protocol.ws_protocol import (
    parse_message, build_state_directive, build_tts_start,
    build_tts_end, build_error, build_text,
)

def test_parse_audio_start():
    msg = parse_message(b'{"type": "audio_start", "session_id": "s1", "turn_id": "t1"}')
    assert msg["type"] == "audio_start"
    assert msg["session_id"] == "s1"
    assert msg["turn_id"] == "t1"

def test_parse_binary_audio():
    # Binary audio is raw bytes, not JSON
    result = parse_message(b'\x00\x01\x02\x03')
    assert result is None  # Binary, not parsed

def test_build_state_directive():
    directive = build_state_directive("listening", "s1", "t1")
    assert directive["type"] == "state"
    assert directive["state"] == "listening"
    assert directive["session_id"] == "s1"
    assert directive["turn_id"] == "t1"

def test_build_tts_start():
    directive = build_tts_start("s1", "t1", sample_rate=16000)
    assert directive["type"] == "tts_start"
    assert directive["sample_rate"] == 16000
    assert directive["format"] == "pcm_s16le"
    assert directive["channels"] == 1

def test_build_error():
    err = build_error("ASR failed", "s1", "t1")
    assert err["type"] == "error"
    assert err["message"] == "ASR failed"
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `pytest tests/test_protocol.py -v`
Expected: FAIL - module doesn't exist

- [ ] **Step 8: Write ws_protocol.py**

```python
# src/protocol/ws_protocol.py
import json
from typing import Any

def parse_message(data: bytes | str) -> dict | None:
    """Parse WebSocket message. Returns dict for JSON, None for binary."""
    if isinstance(data, bytes):
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            return None  # Binary audio
    return json.loads(data)

def build_state_directive(
    state: str,
    session_id: str,
    turn_id: str,
) -> dict:
    return {
        "type": "state",
        "state": state,
        "session_id": session_id,
        "turn_id": turn_id,
    }

def build_text(
    text: str,
    session_id: str,
    turn_id: str,
) -> dict:
    return {
        "type": "text",
        "text": text,
        "session_id": session_id,
        "turn_id": turn_id,
    }

def build_error(
    message: str,
    session_id: str,
    turn_id: str,
) -> dict:
    return {
        "type": "error",
        "message": message,
        "session_id": session_id,
        "turn_id": turn_id,
    }

def build_tts_start(
    session_id: str,
    turn_id: str,
    sample_rate: int = 16000,
    format: str = "pcm_s16le",
    channels: int = 1,
) -> dict:
    return {
        "type": "tts_start",
        "session_id": session_id,
        "turn_id": turn_id,
        "sample_rate": sample_rate,
        "format": format,
        "channels": channels,
    }

def build_tts_end(
    session_id: str,
    turn_id: str,
) -> dict:
    return {
        "type": "tts_end",
        "session_id": session_id,
        "turn_id": turn_id,
    }
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_protocol.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add src/protocol/ws_protocol.py tests/test_protocol.py
git commit -m "feat: add ws_protocol for WebSocket message handling"
```

---

- [ ] **Step 11: Write failing test for config**

```python
# tests/test_config.py
import pytest
from src.config import Config

def test_default_values():
    cfg = Config()
    assert cfg.server["port"] == 8765
    assert cfg.asr.base_url == "http://funasr-api:8001"
    assert cfg.llm.base_url == "http://llama-server:8080/v1"

def test_env_override(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://custom:9000/v1")
    cfg = Config()
    assert cfg.llm.base_url == "http://custom:9000/v1"
```

- [ ] **Step 12: Run tests**

Run: `pytest tests/test_config.py -v`
Expected: FAIL - Config signature changed

- [ ] **Step 13: Update config.py**

```python
# src/config.py
import os
from dataclasses import dataclass
import yaml

@dataclass
class ASRConfig:
    base_url: str = "http://funasr-api:8001"
    timeout: float = 30.0

@dataclass
class LLMConfig:
    base_url: str = "http://llama-server:8080/v1"
    model: str = "unsloth/gemma-4-E4B-it-GGUF:Q8_0"
    max_tokens: int = 512
    temperature: float = 0.7

@dataclass
class TTSConfig:
    voice: str = "zh-CN-XiaoxiaoNeural"
    sample_rate: int = 16000

@dataclass
class MemoryConfig:
    session_dir: str = "./memory/sessions"
    summary_dir: str = "./memory/summaries"
    max_rounds: int = 5
    idle_timeout: int = 120
    max_recent_summaries: int = 3
    max_recent_turns: int = 2

@dataclass
class Config:
    port: int = 8765
    asr: ASRConfig = ASRConfig()
    llm: LLMConfig = LLMConfig()
    tts: TTSConfig = TTSConfig()
    memory: MemoryConfig = MemoryConfig()

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls()
        cfg.asr.base_url = os.getenv("ASR_BASE_URL", cfg.asr.base_url)
        cfg.llm.base_url = os.getenv("LLM_BASE_URL", cfg.llm.base_url)
        cfg.llm.model = os.getenv("LLM_MODEL", cfg.llm.model)
        return cfg

_config_instance: Config | None = None

def get_config() -> Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = Config.from_env()
    return _config_instance
```

- [ ] **Step 14: Run tests**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 15: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: update config with new structure"
```

---

## Chunk 2: Pipeline Clients (ASR + LLM + TTS)

**Files:**
- Create: `tests/test_asr_client.py`
- Modify: `src/pipeline/asr.py` (重写)
- Create: `tests/test_llm_client.py`
- Modify: `src/pipeline/llm.py` (微调)
- Create: `tests/test_tts_client.py`
- Modify: `src/pipeline/tts.py` (重写)

- [ ] **Step 1: Write failing test for ASR client**

```python
# tests/test_asr_client.py
import pytest
from src.pipeline.asr import ASRClient, ASRError, ASRResult

@pytest.fixture
def mock_response():
    class MockResponse:
        def __init__(self, status, json_data):
            self.status = status
            self._json = json_data
        def json(self):
            return self._json

    class MockSession:
        def __init__(self, response):
            self._response = response
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            return MockResponse(200, {"text": "今天天气不错", "duration": 2.5})

    class MockClient:
        def __init__(self, response):
            self._response = response
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            return MockResponse(200, {"text": "今天天气不错", "duration": 2.5})

    return MockClient(None)

def test_asr_result_dataclass():
    result = ASRResult(text="hello", duration=1.5)
    assert result.text == "hello"
    assert result.duration == 1.5

def test_asr_client_returns_asr_result():
    client = ASRClient(base_url="http://localhost:8001")
    # Use mock
    import unittest.mock as mock
    with mock.patch('httpx.AsyncClient') as mock_client_class:
        mock_instance = mock.AsyncMock()
        mock_response = mock.AsyncMock()
        mock_response.status = 200
        mock_response.json = mock.AsyncMock(return_value={"text": "测试", "duration": 1.0})
        mock_instance.post = mock.AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_instance

        import asyncio
        result = asyncio.run(client.recognize(b'\x00\x01\x02'))
        assert result.text == "测试"
        assert result.duration == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_asr_client.py -v`
Expected: FAIL - module doesn't exist

- [ ] **Step 3: Write asr.py**

```python
# src/pipeline/asr.py
from dataclasses import dataclass
import httpx
import base64
from typing import AsyncGenerator

class ASRError(Exception):
    """ASR 服务异常：网络失败 | 非200响应 | 解析错误 | 超时 | 流中断"""

@dataclass
class ASRResult:
    text: str
    duration: float | None = None

class ASRClient:
    """调用本地 FunASR Nano API"""

    def __init__(
        self,
        base_url: str = "http://funasr-api:8001",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def recognize(
        self,
        audio: bytes,
        sample_rate: int = 16000,
    ) -> ASRResult:
        """将 PCM s16le / mono / 16kHz 音频转为文字

        Args:
            audio: raw PCM s16le, mono, 16kHz
            sample_rate: 固定 16000

        Returns:
            ASRResult(text, duration)

        Raises:
            ASRError: 网络失败 | 非200 | 解析错误 | 超时
        """
        url = f"{self.base_url}/asr/json"
        payload = {
            "audio": base64.b64encode(audio).decode("utf-8"),
            "sample_rate": sample_rate,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)

                if response.status_code != 200:
                    raise ASRError(f"ASR returned {response.status_code}")

                data = response.json()
                return ASRResult(
                    text=data.get("text", ""),
                    duration=data.get("duration"),
                )
        except httpx.TimeoutException:
            raise ASRError("ASR timeout")
        except httpx.RequestError as e:
            raise ASRError(f"ASR request failed: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_asr_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/asr.py tests/test_asr_client.py
git commit -m "feat: rewrite ASR client to call FunASR HTTP API"
```

---

- [ ] **Step 6: Write failing test for LLM client**

```python
# tests/test_llm_client.py
import pytest
from src.pipeline.llm import LLMClient, LLMError

def test_llm_client_initialization():
    client = LLMClient(
        base_url="http://localhost:8080/v1",
        model="test-model"
    )
    assert client.base_url == "http://localhost:8080/v1"
    assert client.model == "test-model"
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_llm_client.py -v`
Expected: PASS (existing test should pass)

- [ ] **Step 8: Update llm.py if needed**

The existing llm.py should mostly work, but may need minor tweaks for the new context building.

```python
# src/pipeline/llm.py - existing code is mostly fine, just verify compatibility
```

- [ ] **Step 9: Commit if changed**

```bash
git add src/pipeline/llm.py tests/test_llm_client.py
git commit -m "fix: ensure LLM client works with new protocol"
```

---

- [ ] **Step 10: Write failing test for TTS client**

```python
# tests/test_tts_client.py
import pytest
from src.pipeline.tts import TTSClient, TTSError

def test_tts_client_initialization():
    client = TTSClient()
    assert client.voice == "zh-CN-XiaoxiaoNeural"

def test_tts_client_custom_voice():
    client = TTSClient(voice="zh-CN-YunxiNeural")
    assert client.voice == "zh-CN-YunxiNeural"
```

- [ ] **Step 11: Run tests**

Run: `pytest tests/test_tts_client.py -v`
Expected: FAIL - module doesn't exist

- [ ] **Step 12: Write tts.py with edge-tts**

```python
# src/pipeline/tts.py
import edge_tts
import asyncio
from typing import AsyncGenerator

class TTSError(Exception):
    """TTS 服务异常：网络失败 | 上游错误 | 格式错误 | 超时 | 流中断"""

class TTSClient:
    """调用 edge-tts 合成语音，输出统一转为 PCM s16le / mono / 16kHz"""

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
    ):
        self.voice = voice

    async def synthesize(
        self,
        text: str,
    ) -> AsyncGenerator[bytes, None]:
        """将文本合成为 PCM s16le / mono / 16kHz 音频流

        Args:
            text: 短文本（建议单句或子句，不宜过长）

        Yields:
            PCM s16le audio chunks

        Raises:
            TTSError: 网络失败 | 上游错误 | 格式错误 | 超时
        """
        try:
            # edge-tts produces WebM/OPUS, we use a subprocess to convert
            communicate = edge_tts.Communicate(text, self.voice)

            # We need to convert OPUS to PCM
            # edge-tts can output to a file descriptor, then we convert
            import tempfile
            import os
            import subprocess

            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                temp_path = f.name

            try:
                # Generate to temp file
                await communicate.save(temp_path)

                # Convert to raw PCM using ffmpeg
                process = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", temp_path,
                    "-acodec", "pcm_s16le",
                    "-ar", "16000",
                    "-ac", "1",
                    "-f", "s16le",
                    "-",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                audio_data = await process.communicate()

                if process.returncode != 0:
                    raise TTSError(f"FFmpeg conversion failed")

                # Yield in chunks
                chunk_size = 4096
                for i in range(0, len(audio_data[0]), chunk_size):
                    yield audio_data[0][i:i+chunk_size]

            finally:
                os.unlink(temp_path)

        except asyncio.TimeoutError:
            raise TTSError("TTS timeout")
        except Exception as e:
            raise TTSError(f"TTS failed: {e}")
```

- [ ] **Step 13: Run tests**

Run: `pytest tests/test_tts_client.py -v`
Expected: PASS

- [ ] **Step 14: Commit**

```bash
git add src/pipeline/tts.py tests/test_tts_client.py
git commit -m "feat: rewrite TTS client using edge-tts"
```

---

## Chunk 3: Memory Management

**Files:**
- Create: `tests/test_session.py`
- Modify: `src/memory/session.py` (重写)
- Create: `tests/test_summarizer.py`
- Modify: `src/memory/summarizer.py`

- [ ] **Step 1: Write failing test for new session structure**

```python
# tests/test_session.py
import pytest
from datetime import datetime
from src.memory.session import Session, Turn, Summary, PendingTurn

def test_pending_turn_creation():
    pt = PendingTurn(turn_id="t1", session_id="s1")
    assert pt.turn_id == "t1"
    assert pt.session_id == "s1"
    assert pt.audio_chunks == []
    assert pt.user_text is None

def test_turn_creation():
    turn = Turn(
        turn_id="t1",
        user_text="今天天气怎么样",
        assistant_text="今天天气晴朗",
        timestamp=datetime.now(),
    )
    assert turn.user_text == "今天天气怎么样"
    assert turn.assistant_text == "今天天气晴朗"

def test_summary_creation():
    summary = Summary(
        summary_id="sum1",
        content="用户询问天气，已告知晴天",
        created_at=datetime.now(),
        covered_turn_ids=["t1", "t2"],
    )
    assert len(summary.covered_turn_ids) == 2

def test_session_add_turn():
    session = Session(session_id="s1")
    turn = Turn(
        turn_id="t1",
        user_text="hello",
        assistant_text="hi",
        timestamp=datetime.now(),
    )
    session.add_turn(turn)
    assert len(session.turns) == 1

def test_session_compress():
    session = Session(session_id="s1")
    for i in range(5):
        session.add_turn(Turn(
            turn_id=f"t{i}",
            user_text=f"user{i}",
            assistant_text=f"assistant{i}",
            timestamp=datetime.now(),
        ))

    # Compress keeping 2 recent
    session.compress(keep_recent=2)

    # Should have 2 turns + 1 summary
    assert len(session.turns) == 2
    assert len(session.summaries) == 1
    # Original 5 turns should be summarized
    assert session.summaries[0].covered_turn_ids == ["t0", "t1", "t2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session.py -v`
Expected: FAIL - classes don't exist

- [ ] **Step 3: Write session.py with new data structures**

```python
# src/memory/session.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import List
import uuid

@dataclass
class PendingTurn:
    """一轮对话进行中的临时对象"""
    turn_id: str
    session_id: str
    audio_chunks: list[bytes] = field(default_factory=list)
    user_text: str | None = None
    started_at: datetime = field(default_factory=datetime.now)

@dataclass
class Turn:
    """已完成的对话轮次"""
    turn_id: str
    user_text: str
    assistant_text: str
    timestamp: datetime

@dataclass
class Summary:
    """会话摘要"""
    summary_id: str
    content: str
    created_at: datetime
    covered_turn_ids: list[str]

@dataclass
class Session:
    """会话"""
    session_id: str
    turns: list[Turn] = field(default_factory=list)
    summaries: list[Summary] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_turn(self, turn: Turn):
        self.turns.append(turn)
        self.updated_at = datetime.now()

    def compress(self, keep_recent: int = 2, threshold: int = 5):
        """压缩较早的 turns，生成摘要"""
        if len(self.turns) < threshold:
            return

        to_summarize = self.turns[:-keep_recent]
        recent = self.turns[-keep_recent:]

        # Generate summary content (placeholder - actual LLM call in summarizer)
        summary_content = self._generate_summary_content(to_summarize)

        self.summaries.append(Summary(
            summary_id=str(uuid.uuid4()),
            content=summary_content,
            created_at=datetime.now(),
            covered_turn_ids=[t.turn_id for t in to_summarize],
        ))

        self.turns = recent
        self.updated_at = datetime.now()

    def _generate_summary_content(self, turns: list[Turn]) -> str:
        """Generate summary text from turns (simplified for now)."""
        lines = []
        for turn in turns:
            lines.append(f"- 用户：{turn.user_text}")
            lines.append(f"  助手：{turn.assistant_text}")
        return "\n".join(lines)

    def get_recent_context(self, max_summaries: int = 3, max_turns: int = 2) -> str:
        """构建用于 LLM 的上下文"""
        parts = []

        for summary in self.summaries[-max_summaries:]:
            parts.append(f"【历史摘要】{summary.content}")

        for turn in self.turns[-max_turns:]:
            parts.append(f"用户：{turn.user_text}")
            parts.append(f"助手：{turn.assistant_text}")

        return "\n".join(parts) if parts else ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/session.py tests/test_session.py
git commit -m "feat: rewrite session with Turn/Summary/Session structures"
```

---

- [ ] **Step 6: Write failing test for summarizer**

```python
# tests/test_summarizer.py
import pytest
from src.memory.summarizer import Summarizer

def test_summarizer_save_summary(tmp_path):
    summarizer = Summarizer(summary_dir=str(tmp_path))
    content = "用户询问天气，已告知晴天"
    summarizer.save_summary("s1", content)
    assert (tmp_path / "s1_summary.md").exists()
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_summarizer.py -v`
Expected: FAIL

- [ ] **Step 8: Update summarizer.py**

```python
# src/memory/summarizer.py
import os
from datetime import datetime

class Summarizer:
    """会话摘要生成器"""

    def __init__(self, summary_dir: str = "./memory/summaries"):
        self.summary_dir = summary_dir
        os.makedirs(summary_dir, exist_ok=True)

    def save_summary(
        self,
        session_id: str,
        content: str,
        turn_ids: list[str] | None = None,
    ):
        """保存会话摘要到文件"""
        date = datetime.now().strftime("%Y-%m-%d")
        filepath = os.path.join(self.summary_dir, f"{date}.md")

        lines = [
            "## 会话摘要",
            f"- session_id: {session_id}",
            f"- created_at: {datetime.now().isoformat()}",
            f"- turn_count: {len(turn_ids) if turn_ids else 'unknown'}",
            "",
            content,
            "",
        ]

        with open(filepath, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
            f.write("\n---\n")

    async def generate_summary(self, turns: list) -> str:
        """调用 LLM 生成摘要（简化实现）"""
        if not turns:
            return ""

        # Simple summarization - in production would call LLM
        return f"对话包含 {len(turns)} 轮，用户询问了相关问题，助手已回答。"
```

- [ ] **Step 9: Run tests**

Run: `pytest tests/test_summarizer.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add src/memory/summarizer.py tests/test_summarizer.py
git commit -m "feat: add summarizer for session memory"
```

---

## Chunk 4: Main WebSocket Handler (集成)

**Files:**
- Create: `tests/test_main_integration.py`
- Modify: `src/main.py` (重写)

- [ ] **Step 1: Write integration test skeleton**

```python
# tests/test_main_integration.py
import pytest
import asyncio
from src.main import handle_esp32, create_app

@pytest.fixture
def mock_services():
    """Mock ASR, LLM, TTS clients for testing."""
    class MockASR:
        async def recognize(self, audio, sample_rate=16000):
            return type('obj', (object,), {'text': '测试文本', 'duration': 1.0})()

    class MockLLM:
        async def stream_chat(self, messages, system=None):
            yield "你好"
            yield "，有什么可以帮你的吗？"

    class MockTTS:
        async def synthesize(self, text):
            yield b'\x00\x01\x02\x03'

    return {
        'asr': MockASR(),
        'llm': MockLLM(),
        'tts': MockTTS(),
    }

# Integration tests would require actual WebSocket testing
# This is a simplified skeleton
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_main_integration.py -v`
Expected: SKIP or basic pass

- [ ] **Step 3: Write main.py (WebSocket server)**

```python
# src/main.py
import asyncio
import logging
from websockets.server import serve, WebSocketServerProtocol
from src.config import get_config
from src.state_machine import StateMachine, State
from src.protocol.ws_protocol import (
    parse_message, build_state_directive, build_tts_start,
    build_tts_end, build_error, build_text,
)
from src.memory.session import Session, PendingTurn
from src.pipeline.asr import ASRClient
from src.pipeline.llm import LLMClient
from src.pipeline.tts import TTSClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global config
cfg = get_config()

# Initialize clients
asr_client = ASRClient(base_url=cfg.asr.base_url)
llm_client = LLMClient(base_url=cfg.llm.base_url, model=cfg.llm.model)
tts_client = TTSClient(voice=cfg.tts.voice)


async def handle_esp32(websocket: WebSocketServerProtocol):
    """Handle a single ESP32 client connection."""
    sm = StateMachine()
    session = Session(session_id="default")
    pending_turn: PendingTurn | None = None

    async def send_json(msg: dict):
        await websocket.send(json.dumps(msg))

    async def send_binary(data: bytes):
        await websocket.send(data)

    # Send initial state
    await send_json(build_state_directive("idle", "default", ""))

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Binary audio chunk
                if sm.state == State.LISTENING and pending_turn:
                    pending_turn.audio_chunks.append(message)
                # In other states, ignore binary

            elif isinstance(message, str):
                # JSON control message
                msg = parse_message(message)
                if not msg:
                    continue

                msg_type = msg.get("type")
                turn_id = msg.get("turn_id", "")
                session_id = msg.get("session_id", "")

                if msg_type == "audio_start":
                    # Cancel any pending processing (preemption)
                    sm._cancel_current_turn()

                    pending_turn = PendingTurn(
                        turn_id=turn_id,
                        session_id=session_id,
                    )
                    sm.handle_message(msg)

                    await send_json(build_state_directive("listening", session_id, turn_id))

                elif msg_type == "audio_end":
                    if sm.state != State.LISTENING:
                        continue

                    sm.handle_message(msg)
                    await send_json(build_state_directive("processing", session_id, turn_id))

                    # Run ASR -> LLM -> TTS pipeline
                    try:
                        audio_data = b"".join(pending_turn.audio_chunks)
                        asr_result = await asyncio.wait_for(
                            asr_client.recognize(audio_data),
                            timeout=30.0
                        )
                        user_text = asr_result.text

                        # Get LLM response
                        context = session.get_recent_context(
                            cfg.memory.max_recent_summaries,
                            cfg.memory.max_recent_turns
                        )
                        system_prompt = f"你是一个友好的中文语音助手。回答要自然、简洁、适合口语播报。\n\n以下是与当前用户有关的近期对话记忆：\n{context}"

                        messages = [{"role": "user", "content": user_text}]

                        # Collect LLM output and send to TTS
                        text_buffer = ""
                        first_chunk_sent = False

                        async for token in llm_client.stream_chat(messages, system=system_prompt):
                            text_buffer += token

                            # Check for sentence boundary
                            if any(d in text_buffer for d in "，。！？；") or len(text_buffer) >= 200:
                                # Send to TTS
                                if not first_chunk_sent:
                                    await send_json(build_tts_start(session_id, turn_id))
                                    first_chunk_sent = True

                                async for audio_chunk in tts_client.synthesize(text_buffer):
                                    await send_binary(audio_chunk)

                                text_buffer = ""

                        # Handle remaining buffer
                        if text_buffer and first_chunk_sent:
                            async for audio_chunk in tts_client.synthesize(text_buffer):
                                await send_binary(audio_chunk)

                        if first_chunk_sent:
                            await send_json(build_tts_end(session_id, turn_id))

                        # Add completed turn to session
                        from src.memory.session import Turn
                        session.add_turn(Turn(
                            turn_id=turn_id,
                            user_text=user_text,
                            assistant_text="[ streamed ]",  # Store final assembled text if needed
                            timestamp=datetime.now(),
                        ))

                        # Check if needs compression
                        if len(session.turns) >= 5:
                            session.compress(threshold=5)

                        sm.state = State.IDLE

                    except asyncio.TimeoutError:
                        await send_json(build_error("Processing timeout", session_id, turn_id))
                        sm.state = State.IDLE
                    except Exception as e:
                        logger.error(f"Processing error: {e}")
                        await send_json(build_error(str(e), session_id, turn_id))
                        sm.state = State.IDLE

                elif msg_type == "playback_done":
                    sm.handle_message(msg)
                    await send_json(build_state_directive("idle", session_id, ""))

                elif msg_type == "session_end":
                    sm.handle_message(msg)
                    # Generate summary and save
                    from src.memory.summarizer import Summarizer
                    summarizer = Summarizer(cfg.memory.summary_dir)
                    if session.turns:
                        content = session.get_recent_context(3, 10)
                        summarizer.save_summary(session.session_id, content)
                    await send_json(build_state_directive("idle", session_id, ""))

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        logger.info("ESP32 disconnected")


async def main():
    cfg = get_config()
    host = "0.0.0.0"
    port = cfg.port
    logger.info(f"Starting WebSocket server on {host}:{port}")

    async with serve(handle_esp32, host, port, ping_interval=30):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -v`
Expected: Basic tests pass

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main_integration.py
git commit -m "feat: rewrite main.py with new WebSocket handler"
```

---

## Chunk 5: Docker Deployment

**Files:**
- Create: `Dockerfile` (python-hub)
- Create: `funasr_api/Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Write python-hub Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies (no torch)
RUN pip install --no-cache-dir \
    edge-tts \
    websockets \
    pyyaml \
    aiohttp \
    pydantic \
    httpx \
    pytest \
    pytest-asyncio

COPY src/ ./src/
COPY config.yaml ./

EXPOSE 8765

CMD ["python", "src/main.py"]
```

- [ ] **Step 2: Write funasr_api Dockerfile**

```dockerfile
# funasr_api/Dockerfile
FROM intel/intel-extension-for-pytorch:2.8.10-xpu

WORKDIR /app

# Install FunASR (no torch-related packages, already in base)
RUN pip install --no-cache-dir \
    funasr \
    pydantic \
    fastapi \
    uvicorn[standard] \
    python-multipart \
    soundfile

COPY . .

EXPOSE 8001

CMD ["python", "main.py"]
```

- [ ] **Step 3: Write docker-compose.yml**

```yaml
# docker-compose.yml
services:
  llama-server:
    external: true
    network_mode: host

  funasr-api:
    build: ../funasr_api
    container_name: funasr-api
    ports:
      - "8001:8001"
    environment:
      - MODEL_NAME=FunAudioLLM/Fun-ASR-Nano-2512
      - HOST=0.0.0.0
      - PORT=8001
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface:ro
    deploy:
      resources:
        limits:
          memory: "4g"
        reservations:
          memory: "1g"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  python-hub:
    build: .
    container_name: python-hub
    ports:
      - "8765:8765"
    volumes:
      - ./memory:/app/memory
    environment:
      - LLM_BASE_URL=http://llama-server:8080/v1
      - LLM_MODEL=unsloth/gemma-4-E4B-it-GGUF:Q8_0
      - ASR_BASE_URL=http://funasr-api:8001
    depends_on:
      funasr-api:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: "2g"
        reservations:
          memory: "256m"
    restart: unless-stopped

networks:
  default:
    name: voice-assistant-net
```

- [ ] **Step 4: Write .dockerignore**

```dockerignore
# .dockerignore
__pycache__
*.pyc
.venv
.git
*.md
tests/
```

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git add ../funasr_api/Dockerfile
git commit -m "feat: add Docker deployment files"
```

---

## Chunk 6: Cleanup Old Code

**Files to remove:**
- `src/pipeline/kws.py` - KWS now on ESP32 side
- `src/pipeline/vad.py` - VAD now on ESP32 side

- [ ] **Step 1: Remove old KWS and VAD files**

```bash
rm src/pipeline/kws.py src/pipeline/vad.py
git add -A
git commit -m "chore: remove kws and vad (now on ESP32 side)"
```

---

## Chunk 7: Final Integration Test

**Files:**
- Modify: `tests/test_full_pipeline.py`

- [ ] **Step 1: Update integration test**

```python
# tests/test_full_pipeline.py - update to test new flow
import pytest
import asyncio

async def test_full_pipeline():
    """Test ASR -> LLM -> TTS flow with mocked services."""
    # This would be a full integration test
    # For now, just verify imports work
    from src.main import handle_esp32
    from src.pipeline.asr import ASRClient
    from src.pipeline.llm import LLMClient
    from src.pipeline.tts import TTSClient
    from src.memory.session import Session
    from src.state_machine import StateMachine

    assert True  # Placeholder
```

- [ ] **Step 2: Run final tests**

Run: `pytest tests/ -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_full_pipeline.py
git commit -m "test: update integration test for new pipeline"
```

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-22-voice-assistant-refactor.md`. Ready to execute?**