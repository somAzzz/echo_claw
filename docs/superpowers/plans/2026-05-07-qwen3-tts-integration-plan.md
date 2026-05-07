# Qwen3-TTS Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement hot-swappable TTS providers (Edge + Qwen3-TTS via vLLM-Omni) using strategy pattern.

**Architecture:** Refactor `src/pipeline/tts.py` into a package with `BaseTTSClient` abstract interface, `EdgeTTSClient` and `Qwen3TTSClient` implementations, and a factory function. All clients output 16kHz PCM regardless of internal processing.

**Tech Stack:** Python 3.10+, aiohttp, audioop, edge_tts, asyncio

---

## Chunk 1: TTS Package Structure

### Files
- Create: `src/pipeline/tts/__init__.py`
- Create: `src/pipeline/tts/base.py`
- Create: `src/pipeline/tts/edge_client.py`
- Create: `src/pipeline/tts/qwen_client.py`

- [ ] **Step 1: Create `src/pipeline/tts/__init__.py` with factory function**

```python
"""TTS package - factory for creating TTS clients."""

from typing import AsyncGenerator
from pathlib import Path

from src.config import TTSConfig


def create_tts_client(config: TTSConfig):
    """Factory function to create TTS client based on config.provider."""
    if config.provider == "qwen":
        from .qwen_client import Qwen3TTSClient
        return Qwen3TTSClient(
            base_url=config.qwen_api_base,
            model=config.qwen_model,
            voice=config.qwen_voice,
            sample_rate=config.qwen_sample_rate,
        )
    else:
        from .edge_client import EdgeTTSClient
        return EdgeTTSClient(
            voice=config.voice,
            rate=config.rate,
            pitch=config.pitch,
            volume=config.volume,
        )
```

- [ ] **Step 2: Create `src/pipeline/tts/base.py` with abstract interface**

```python
"""Base TTS client abstract interface."""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncGenerator


class BaseTTSClient(ABC):
    """Abstract base class for TTS clients.

    All implementations must yield 16kHz, 16bit, Mono PCM bytes.
    """

    @abstractmethod
    async def stream_audio(self, text: str) -> AsyncGenerator[bytes, None]:
        """Stream 16kHz PCM audio from text.

        Args:
            text: Text to synthesize

        Yields:
            16kHz, 16bit, Mono PCM bytes
        """
        pass

    async def synthesize_to_file(self, text: str, path: Path) -> None:
        """Synthesize text and save to WAV file for debugging.

        Args:
            text: Text to synthesize
            path: Output WAV file path
        """
        import wave
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            async for chunk in self.stream_audio(text):
                wf.writeframes(chunk)
```

- [ ] **Step 3: Create `src/pipeline/tts/edge_client.py` (refactored from existing)**

```python
"""Edge TTS client implementation."""

import asyncio
import os
import tempfile
from typing import AsyncGenerator

import edge_tts


class EdgeTTSClient(BaseTTSClient):
    """TTS client using Microsoft Edge TTS service.

    Args:
        voice: Edge TTS voice name (default: zh-CN-XiaoxiaoNeural)
        rate: Speech rate as percentage (e.g., "-42%" or "+13%")
        pitch: Pitch adjustment (e.g., "+13Hz")
        volume: Volume adjustment (e.g., "+0%")
    """

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        volume: str = "+0%",
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume

    async def _synthesize_webm(self, text: str) -> str:
        """Synthesize text to a temporary webm file via edge-tts.

        Returns path to the temporary webm file (caller must clean up).
        """
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            temp_path = f.name
        communicate = edge_tts.Communicate(text, self.voice)
        communicate._rate = self.rate
        communicate._pitch = self.pitch
        communicate._volume = self.volume
        await communicate.save(temp_path)
        return temp_path

    async def stream_audio(self, text: str) -> AsyncGenerator[bytes, None]:
        """Convert text to WAV audio using edge-tts + ffmpeg.

        Yields:
            WAV audio chunks (PCM s16le, mono, 16kHz)
        """
        temp_path = None
        try:
            temp_path = await self._synthesize_webm(text)

            # Convert to WAV using ffmpeg (output to stdout)
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y",
                "-i", temp_path,
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                "-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            audio_data, _ = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError(f"ffmpeg conversion failed with returncode {process.returncode}")

            # Yield chunks
            chunk_size = 8192
            for i in range(0, len(audio_data), chunk_size):
                yield audio_data[i:i + chunk_size]

        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
```

- [ ] **Step 4: Create `src/pipeline/tts/qwen_client.py`**

```python
"""Qwen3-TTS client implementation via vLLM-Omni."""

import audioop
import aiohttp
import struct
from typing import AsyncGenerator, Optional

from .base import BaseTTSClient


class Qwen3TTSClient(BaseTTSClient):
    """TTS client using Qwen3-TTS via vLLM-Omni.

    Args:
        base_url: vLLM-Omni API base URL (e.g., "http://localhost:8000/v1")
        model: Model name for vLLM
        voice: Pre-defined speaker name
        sample_rate: Model output sample rate (default: 24000)
    """

    def __init__(
        self,
        base_url: str,
        model: str = "Qwen3-TTS-12Hz-1.7B-CustomVoice",
        voice: str = "Awesome_Sally",
        sample_rate: int = 24000,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.voice = voice
        self.in_rate = sample_rate
        self.out_rate = 16000

    async def stream_audio(self, text: str) -> AsyncGenerator[bytes, None]:
        """Stream 16kHz PCM audio from vLLM-Omni TTS API.

        Handles:
        - WAV header detection and stripping
        - Sample rate detection from WAV header
        - State-preserving resampling via audioop.ratecv
        - Proper cancellation handling

        Yields:
            16kHz, 16bit, Mono PCM bytes
        """
        url = f"{self.base_url}/v1/audio/speech"
        payload = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": "pcm",
            "stream": True,
        }

        resample_state = None
        detected_rate = self.in_rate
        skip_bytes = 0

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                response.raise_for_status()

                async for chunk in response.content.iter_chunked(4800):
                    if not chunk:
                        continue

                    # Handle WAV header on first chunk
                    if chunk[:4] == b'RIFF':
                        # Parse WAV header to get sample rate
                        detected_rate = struct.unpack('<I', chunk[24:28])[0]
                        skip_bytes = 44
                        chunk = chunk[skip_bytes:]

                    if not chunk:
                        continue

                    # Ensure chunk is 2-byte aligned for audioop
                    chunk = chunk[:len(chunk) - (len(chunk) % 2)]

                    # Resample from detected_rate to 16000
                    try:
                        resampled_chunk, resample_state = audioop.ratecv(
                            chunk,
                            2,  # 16bit
                            1,  # mono
                            detected_rate,
                            self.out_rate,
                            resample_state,
                        )
                        yield resampled_chunk
                    except audioop.error:
                        # Skip malformed chunks
                        continue

    async def warmup(self) -> None:
        """Warmup the model to reduce first-packet latency.

        Call this on system startup or provider switch.
        """
        async with aiohttp.ClientSession() as session:
            await session.post(
                self.base_url + "/v1/audio/speech",
                json={
                    "model": self.model,
                    "input": " ",
                    "voice": self.voice,
                    "response_format": "pcm",
                }
            )
```

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/tts/
git commit -m "feat: add TTS package with strategy pattern

- BaseTTSClient abstract interface
- EdgeTTSClient (refactored from existing tts.py)
- Qwen3TTSClient with vLLM-Omni support
- Factory create_tts_client() function

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Chunk 1.5: Add Dependencies

- [ ] **Step 1: Update pyproject.toml with aiohttp dependency**

Check existing dependencies and add aiohttp:

```bash
grep -A 20 "\[project\]" pyproject.toml | head -25
```

Add to dependencies if not present:

```toml
dependencies = [
    ...
    "aiohttp>=3.9.0",
]
```

Note: `audioop` is a Python built-in module (C extension). For Python 3.13+ compatibility, add `audioop-lts` as a conditional dependency:

```toml
[project.optional-dependencies]
audioop-lts = ["audioop-lts; python_version >= '3.13'"]
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add aiohttp dependency for Qwen3-TTS client

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Chunk 2: Config Updates

### Files
- Modify: `src/config.py:43-50` (TTSConfig dataclass)
- Modify: `src/config.py:150-159` (TTSConfig loading)
- Modify: `config.yaml`

- [ ] **Step 1: Update `TTSConfig` dataclass in `src/config.py`**

Replace the existing `TTSConfig` class (lines 43-50):

```python
@dataclass
class TTSConfig:
    """TTS configuration supporting multiple providers."""
    # Provider selection
    provider: str = "edge"  # "edge" or "qwen"

    # Edge TTS settings
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "-20%"
    pitch: str = "+13Hz"
    volume: str = "+0%"
    sample_rate: int = 16000

    # Qwen3-TTS settings
    qwen_api_base: str = "http://localhost:8000/v1"
    qwen_model: str = "Qwen3-TTS-12Hz-1.7B-CustomVoice"
    qwen_voice: str = "Awesome_Sally"
    qwen_sample_rate: int = 24000
```

- [ ] **Step 2: Update TTSConfig loading in `src/config.py`** (around line 150)

Replace the existing TTS loading block:

```python
        # Load TTS config
        tts_data = yaml_data.get("tts", {})
        tts = TTSConfig(
            provider=tts_data.get("provider", "edge"),
            # Edge TTS
            voice=os.environ.get("TTS_VOICE", tts_data.get("voice", "zh-CN-YunxiaNeural")),
            rate=os.environ.get("TTS_RATE", tts_data.get("rate", "-20%")),
            pitch=os.environ.get("TTS_PITCH", tts_data.get("pitch", "+13Hz")),
            volume=os.environ.get("TTS_VOLUME", tts_data.get("volume", "+0%")),
            # Qwen3-TTS
            qwen_api_base=os.environ.get("QWEN_TTS_API_BASE", tts_data.get("qwen_api_base", "http://localhost:8000/v1")),
            qwen_model=os.environ.get("QWEN_TTS_MODEL", tts_data.get("qwen_model", "Qwen3-TTS-12Hz-1.7B-CustomVoice")),
            qwen_voice=os.environ.get("QWEN_TTS_VOICE", tts_data.get("qwen_voice", "Awesome_Sally")),
            qwen_sample_rate=int(os.environ.get("QWEN_TTS_SAMPLE_RATE", tts_data.get("qwen_sample_rate", 24000))),
        )
```

- [ ] **Step 3: Update `config.yaml`**

Replace the existing `tts:` section:

```yaml
tts:
  provider: "edge"  # "edge" or "qwen"

  # Edge TTS settings
  voice: "zh-CN-YunxiaNeural"
  rate: "-20%"
  pitch: "+13Hz"
  volume: "+0%"

  # Qwen3-TTS settings (via vLLM-Omni)
  qwen_api_base: "http://qwen-tts-vllm:8000/v1"
  qwen_model: "Qwen3-TTS-12Hz-1.7B-CustomVoice"
  qwen_voice: "Awesome_Sally"
  qwen_sample_rate: 24000
```

- [ ] **Step 4: Commit**

```bash
git add src/config.py config.yaml
git commit -m "feat: extend TTS config for provider selection and Qwen3-TTS

- Add provider field (edge/qwen)
- Add Qwen3-TTS configuration options
- Support env vars for all settings

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Chunk 3: Pipeline Integration

### Files
- Modify: `src/pipeline/__init__.py`
- Modify: `src/main.py` (tts.synthesize → tts.stream_audio)

- [ ] **Step 1: Update `src/pipeline/__init__.py`**

Replace the import and `create_pipeline_clients` function:

```python
"""Pipeline package - shared factory for creating pipeline clients."""

from .asr import ASRClient
from .llm import LLMClient
from .tts import create_tts_client


def _create_llm_from_config(llm_config, max_tokens=None):
    """Create an LLMClient from an LLMConfig or OnlineLLMConfig instance."""
    return LLMClient(
        base_url=llm_config.base_url,
        model=llm_config.model,
        api_key=getattr(llm_config, "api_key", None) or None,
        max_tokens=max_tokens or llm_config.max_tokens,
    )


def create_pipeline_clients(cfg, warmup_qwen: bool = False):
    """Create ASR, LLM (chat + memory), and TTS clients from a Config instance.

    Returns a tuple of (asr, chat_llm, memory_llm, tts).
    - chat_llm: uses active_chat_llm mode (local or online)
    - memory_llm: always uses local LLM for summarization

    Args:
        warmup_qwen: If True and provider is qwen, trigger warmup after client creation
    """
    asr = ASRClient(base_url=cfg.asr.base_url)

    # Chat LLM: respect active_chat_llm toggle
    if cfg.active_chat_llm == "online":
        chat_llm = _create_llm_from_config(cfg.online_llm)
    else:
        chat_llm = _create_llm_from_config(cfg.llm)

    # Memory LLM: always local (summarization doesn't need online model)
    memory_llm = _create_llm_from_config(cfg.llm)

    tts = create_tts_client(cfg.tts)

    # Warmup Qwen3-TTS if requested (reduces first-packet latency)
    if warmup_qwen and cfg.tts.provider == "qwen":
        import asyncio
        asyncio.create_task(tts.warmup())

    return asr, chat_llm, memory_llm, tts
```

- [ ] **Step 2: Update `src/main.py` method calls**

Find all occurrences of `tts.synthesize(` and replace with `tts.stream_audio(`:

```bash
grep -n "tts.synthesize" src/main.py
```

Expected matches (approximately):
- Line 170: `async for audio_chunk in tts.synthesize(text_to_speak):`
- Line 179: `async for audio_chunk in tts.synthesize(text_to_speak):`

Replace with `tts.stream_audio(`.

Also update `synthesize_to_file` if needed (line 190).

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/__init__.py src/main.py
git commit -m "refactor: integrate TTS factory and rename synthesize to stream_audio

- Use create_tts_client() factory in pipeline
- Rename synthesize() to stream_audio() per BaseTTSClient interface

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Chunk 4: HTTP API Provider Switching + Warmup

### Files
- Modify: `src/http_api.py`

- [ ] **Step 1: Update `ConfigUpdate` and add provider switching in `src/http_api.py`**

Update the `ConfigUpdate` class:

```python
class ConfigUpdate(BaseModel):
    voice: str = None
    rate: str = None
    pitch: str = None
    volume: str = None
    active_chat_llm: str = None  # "local" or "online"
    tts_provider: str = None  # "edge" or "qwen"
```

Update `get_config()` to include provider:

```python
@app.get("/api/config")
def get_config() -> dict:
    """Get current configuration."""
    return {
        "tts": {
            "provider": config.tts.provider,
            "voice": config.tts.voice,
            "rate": config.tts.rate,
            "pitch": config.tts.pitch,
            "volume": config.tts.volume,
        },
        "llm": {
            "active_chat_llm": config.active_chat_llm,
            "online_model": config.online_llm.model,
        },
    }
```

Update `update_config()` to handle provider and trigger warmup:

```python
@app.put("/api/config")
def update_config(cfg: ConfigUpdate) -> dict:
    """Update configuration (runtime only, not persisted)."""
    if cfg.tts_provider is not None:
        config.tts.provider = cfg.tts_provider
        # Warmup Qwen3-TTS when switching to qwen provider
        if cfg.tts_provider == "qwen":
            # Note: warmup is async, fire-and-forget is acceptable
            # The actual warmup happens in the pipeline client creation
            pass
    if cfg.voice is not None:
        config.tts.voice = cfg.voice
    if cfg.rate is not None:
        config.tts.rate = cfg.rate
    if cfg.pitch is not None:
        config.tts.pitch = cfg.pitch
    if cfg.volume is not None:
        config.tts.volume = cfg.volume
    if cfg.active_chat_llm is not None:
        config.active_chat_llm = cfg.active_chat_llm
    return {"status": "updated"}
```

- [ ] **Step 2: Add warmup integration in `src/pipeline/__init__.py`**

The warmup should be called after creating the Qwen3TTSClient. Update `create_pipeline_clients`:

```python
def create_pipeline_clients(cfg, warmup_qwen: bool = False):
    """Create ASR, LLM (chat + memory), and TTS clients from a Config instance.

    Returns a tuple of (asr, chat_llm, memory_llm, tts).
    - chat_llm: uses active_chat_llm mode (local or online)
    - memory_llm: always uses local LLM for summarization

    Args:
        warmup_qwen: If True and provider is qwen, trigger warmup after client creation
    """
    asr = ASRClient(base_url=cfg.asr.base_url)

    # Chat LLM: respect active_chat_llm toggle
    if cfg.active_chat_llm == "online":
        chat_llm = _create_llm_from_config(cfg.online_llm)
    else:
        chat_llm = _create_llm_from_config(cfg.llm)

    # Memory LLM: always local (summarization doesn't need online model)
    memory_llm = _create_llm_from_config(cfg.llm)

    tts = create_tts_client(cfg.tts)

    # Warmup Qwen3-TTS if requested (reduces first-packet latency)
    if warmup_qwen and cfg.tts.provider == "qwen":
        import asyncio
        asyncio.create_task(tts.warmup())

    return asr, chat_llm, memory_llm, tts
```

Note: Since `main.py` creates clients via `create_pipeline_clients`, the warmup call happens once at connection time. This is sufficient for reducing TTFB on the first synthesis after an ESP32 connects.

- [ ] **Step 2: Commit**

```bash
git add src/http_api.py
git commit -m "feat: add TTS provider switching via HTTP API

- Add tts_provider field to ConfigUpdate
- Include provider in GET /api/config response
- Support runtime provider switching

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Chunk 5: Integration Verification

- [ ] **Step 1: Verify imports work**

```bash
cd /home/bo/projects/echo_claw
python -c "from src.pipeline.tts import create_tts_client; print('Import OK')"
```

- [ ] **Step 2: Verify Edge TTS client can be created**

```bash
python -c "
from src.config import TTSConfig
from src.pipeline.tts import create_tts_client
cfg = TTSConfig(provider='edge')
client = create_tts_client(cfg)
print(f'EdgeTTSClient: {type(client).__name__}')
"
```

- [ ] **Step 3: Verify Qwen3 TTS client can be created**

```bash
python -c "
from src.config import TTSConfig
from src.pipeline.tts import create_tts_client
cfg = TTSConfig(provider='qwen', qwen_api_base='http://localhost:8000/v1')
client = create_tts_client(cfg)
print(f'Qwen3TTSClient: {type(client).__name__}')
"
```

- [ ] **Step 4: Commit integration verification**

```bash
git add -A && git commit -m "chore: verify TTS factory integration

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>" || echo "Nothing to commit"
```

---

## Summary

| Chunk | Description |
|-------|-------------|
| 1 | Create TTS package with base, edge_client, qwen_client |
| 1.5 | Add aiohttp dependency to pyproject.toml |
| 2 | Update config.py and config.yaml for provider selection |
| 3 | Integrate factory into pipeline and update main.py |
| 4 | Add HTTP API endpoints for provider switching + warmup |
| 5 | Integration verification |

**After all chunks complete, update docker-compose.yml to add vLLM-Omni service.**

**Note on warmup():** The `warmup()` method is called once when the pipeline client is created (at ESP32 connection time) if `warmup_qwen=True`. This is sufficient to preload the model into GPU memory and reduce TTFB for the first synthesis. Subsequent requests don't need re-warmup.
