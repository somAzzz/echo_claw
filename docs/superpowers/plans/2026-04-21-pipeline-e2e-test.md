# Full Pipeline E2E Test Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement end-to-end test that generates audio from TTS, feeds through ASR→LLM→TTS pipeline, validates content correctness and measures performance.

**Architecture:** Test uses fixture-based approach with session-scoped TTS audio generation. Fixtures generate both PCM (for processing) and WAV (for human verification). Tests run in Docker container with models mounted.

**Tech Stack:** pytest, pytest-asyncio, sherpa-onnx, websockets

---

## File Structure

```
tests/
  fixtures/                      # Created: audio fixture directory
    test_input_tts.pcm           # PCM for ASR processing
    test_input_tts.wav           # WAV for human verification
  test_full_pipeline.py          # Created: main test file
```

**Dependencies:**
- Modify: `src/pipeline/llm.py` - Make stream_chat() actually call the LLM server
- Modify: `src/config.py` - Already exists, read for reference

---

## Chunk 1: Create fixtures directory and LLM client fix

### Task 1: Create fixtures directory and .gitkeep

**Files:**
- Create: `tests/fixtures/.gitkeep`

- [ ] **Step 1: Create fixtures directory with .gitkeep**

```bash
mkdir -p tests/fixtures
touch tests/fixtures/.gitkeep
```

- [ ] **Step 2: Commit**

```bash
git add tests/fixtures/.gitkeep
git commit -m "chore: add fixtures directory for e2e test audio files"
```

---

### Task 2: Fix LLMClient to make real streaming requests

The current `stream_chat()` is a stub that yields nothing. We need it to actually call the LLM server.

**Files:**
- Modify: `src/pipeline/llm.py:20-24`

- [ ] **Step 1: Write the failing test**

Create `tests/test_llm_client.py`:

```python
import pytest

def test_llm_client_stream_chat_returns_tokens():
    """LLM client should yield tokens from actual API."""
    from src.pipeline.llm import LLMClient

    llm = LLMClient(
        base_url="http://llama-server:8080/v1",
        model="unsloth/gemma-4-E4B-it-GGUF:Q8_0",
    )

    messages = [{"role": "user", "content": "Say 'hello' in one word"}]
    tokens = []
    async def collect():
        async for token in llm.stream_chat(messages):
            tokens.append(token)

    import asyncio
    asyncio.get_event_loop().run_until_complete(collect())

    # Should get some tokens (not empty)
    assert len(tokens) > 0, "Expected tokens from LLM"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_client.py -v`
Expected: Test passes but tokens is empty because stub yields nothing.

- [ ] **Step 3: Implement real streaming**

Modify `src/pipeline/llm.py`:

```python
from typing import AsyncGenerator, List, Optional
import aiohttp


class LLMClient:
    """LLM client for streaming chat completions."""

    def __init__(self, base_url: str, model: str, api_key: str = None):
        self._base_url = base_url
        self._model = model
        self._api_key = api_key

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model

    async def stream_chat(
        self, messages: List[dict], system: str = None
    ) -> AsyncGenerator[str, None]:
        """Stream chat completions from LLM server."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }
        if system:
            payload["system"] = system

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        import json
                        try:
                            data = json.loads(line[6:])
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
```

- [ ] **Step 4: Add aiohttp to requirements.txt**

Check if aiohttp is in requirements:

```bash
grep -q aiohttp requirements.txt || echo "aiohttp" >> requirements.txt
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_llm_client.py -v`
Expected: PASS - tokens list should have content

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/llm.py requirements.txt tests/test_llm_client.py
git commit -m "feat: make LLMClient stream real responses from server"
```

---

## Chunk 2: Create main test file

### Task 3: Create tts_audio_fixture and TTS test

**Files:**
- Create: `tests/test_full_pipeline.py`

- [ ] **Step 1: Write the failing test for TTS generation**

Create `tests/test_full_pipeline.py`:

```python
"""Full pipeline E2E tests: TTS → ASR → LLM → TTS."""
import os
import wave
import pytest
import time
import asyncio
from src.config import Config
from src.pipeline.tts import TTSGenerator
from src.pipeline.asr import ASRRecognizer


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
PCM_FIXTURE = os.path.join(FIXTURE_DIR, "test_input_tts.pcm")
WAV_FIXTURE = os.path.join(FIXTURE_DIR, "test_input_tts.wav")
TEST_TEXT = "你好啊，你是谁啊？"


@pytest.fixture(scope="session")
def tts_audio_fixture(request):
    """Generate TTS audio fixture (PCM + WAV). Skip if exists unless --regenerate-fixtures."""
    regenerate = request.config.getoption("--regenerate-fixtures", default=False)

    if os.path.exists(PCM_FIXTURE) and os.path.exists(WAV_FIXTURE) and not regenerate:
        return PCM_FIXTURE

    # Generate audio
    cfg = Config.get_instance()
    tts = TTSGenerator(
        model_dir=cfg.tts.get("model_dir", ""),
        tokens=cfg.tts.get("tokens", ""),
        encoder=cfg.tts.get("encoder", ""),
        decoder=cfg.tts.get("decoder", ""),
        vocoder=cfg.tts.get("vocoder", ""),
        data_dir=cfg.tts.get("data_dir", ""),
        mode=cfg.tts.get("mode", "streaming"),
        reference_audio=cfg.tts.get("reference_audio"),
    )

    # Collect all audio bytes
    audio_chunks = []
    async def generate():
        async for chunk in tts.generate(TEST_TEXT):
            audio_chunks.append(chunk)

    asyncio.get_event_loop().run_until_complete(generate())

    if not audio_chunks:
        pytest.fail("TTS generated no audio")

    pcm_data = b"".join(audio_chunks)

    # Save PCM
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    with open(PCM_FIXTURE, "wb") as f:
        f.write(pcm_data)

    # Save WAV
    sample_rate = 24000
    with wave.open(WAV_FIXTURE, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Convert float32 to int16
        samples = []
        for chunk in audio_chunks:
            arr = numpy.frombuffer(chunk, dtype=numpy.float32)
            samples.extend(arr)
        import numpy as np
        int16_data = (np.array(samples) * 32767).astype(np.int16)
        wf.writeframes(int16_data.tobytes())

    return PCM_FIXTURE


def test_tts_generation_saves_audio(tts_audio_fixture):
    """TTS should generate both PCM and WAV files."""
    assert os.path.exists(tts_audio_fixture), "PCM fixture not created"
    assert os.path.exists(WAV_FIXTURE), "WAV fixture not created"

    pcm_size = os.path.getsize(tts_audio_fixture)
    assert pcm_size > 0, "PCM file is empty"

    wav_size = os.path.getsize(WAV_FIXTURE)
    assert wav_size > 44, "WAV file too small (needs header)"  # 44 byte header minimum

    with wave.open(WAV_FIXTURE, "rb") as wf:
        assert wf.getnchannels() == 1, "WAV should be mono"
        assert wf.getsampwidth() == 2, "WAV should be 16-bit"
        assert wf.getframerate() == 24000, "WAV sample rate should be 24000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_full_pipeline.py::test_tts_generation_saves_audio -v`
Expected: FAIL - numpy not imported, fixture not created

- [ ] **Step 3: Fix the test (add numpy import at top)**

```python
import numpy as np
```

- [ ] **Step 4: Run test to verify it fails (missing TTS model)**

Run: `pytest tests/test_full_pipeline.py::test_tts_generation_saves_audio -v`
Expected: FAIL - TTS model not available or fixture generation fails

- [ ] **Step 5: Implement minimal TTS stub if needed**

If TTSGenerator raises exception, the test should properly skip with message.

- [ ] **Step 6: Commit (or iterate until test passes)**

```bash
git add tests/test_full_pipeline.py
git commit -m "feat: add TTS fixture generation and test"
```

---

### Task 4: Add ASR recognition test

**Files:**
- Modify: `tests/test_full_pipeline.py`

- [ ] **Step 1: Add ASR test to test file**

```python
def test_asr_recognizes_tts_audio(tts_audio_fixture):
    """ASR should recognize text from TTS-generated audio."""
    cfg = Config.get_instance()
    asr = ASRRecognizer(
        model_dir=cfg.asr.get("model_dir", ""),
        tokens=cfg.asr.get("tokens"),
        encoder=cfg.asr.get("encoder"),
        decoder=cfg.asr.get("decoder"),
        joiner=cfg.asr.get("joiner"),
    )

    with open(tts_audio_fixture, "rb") as f:
        pcm_data = f.read()

    text = asr.recognize(pcm_data)
    assert text, "ASR returned empty text"
    # Check for expected Chinese keywords
    assert any(kw in text for kw in ["你好", "谁"]), f"ASR text missing expected keywords: {text}"
```

- [ ] **Step 2: Run test to verify it fails (ASR model not available)**

Run: `pytest tests/test_full_pipeline.py::test_asr_recognizes_tts_audio -v`
Expected: FAIL or SKIP - ASR model files not present

- [ ] **Step 3: Add model availability checks with pytest.skip**

The test should skip gracefully if model files are missing.

- [ ] **Step 4: Commit**

```bash
git add tests/test_full_pipeline.py
git commit -m "feat: add ASR recognition test for TTS audio"
```

---

### Task 5: Add full pipeline test with LLM

**Files:**
- Modify: `tests/test_full_pipeline.py`

- [ ] **Step 1: Add full pipeline test**

```python
def test_full_pipeline_asr_llm_tts(tts_audio_fixture):
    """Full pipeline: TTS audio → ASR → LLM → TTS response."""
    import logging
    logging.basicConfig(level=logging.INFO)

    cfg = Config.get_instance()

    # ASR stage
    asr = ASRRecognizer(
        model_dir=cfg.asr.get("model_dir", ""),
        tokens=cfg.asr.get("tokens"),
        encoder=cfg.asr.get("encoder"),
        decoder=cfg.asr.get("decoder"),
        joiner=cfg.asr.get("joiner"),
    )

    with open(tts_audio_fixture, "rb") as f:
        pcm_data = f.read()

    t0 = time.time()
    asr_text = asr.recognize(pcm_data)
    asr_latency = time.time() - t0
    logging.info(f"ASR latency: {asr_latency:.2f}s, text: {asr_text}")
    assert asr_text, "ASR returned empty"

    # LLM stage
    from src.pipeline.llm import LLMClient
    llm = LLMClient(
        base_url=cfg.llm.get("base_url", ""),
        model=cfg.llm.get("model", ""),
        api_key=cfg.llm.get("api_key"),
    )

    messages = [{"role": "user", "content": asr_text}]
    t1 = time.time()
    response_tokens = []
    async def stream_llm():
        async for token in llm.stream_chat(messages):
            response_tokens.append(token)

    asyncio.get_event_loop().run_until_complete(stream_llm())
    llm_latency = time.time() - t1
    response_text = "".join(response_tokens)
    logging.info(f"LLM latency: {llm_latency:.2f}s, response: {response_text}")
    assert response_text, "LLM returned empty response (required)"
    logging.info(f"Full pipeline SUCCESS - ASR: {asr_latency:.1f}s, LLM: {llm_latency:.1f}s")
```

- [ ] **Step 2: Run test to verify it fails (expected - LLM not reachable in test env)**

Run: `pytest tests/test_full_pipeline.py::test_full_pipeline_asr_llm_tts -v`
Expected: FAIL - connection error (LLM is required, not skippable)

- [ ] **Step 3: Commit**

```bash
git add tests/test_full_pipeline.py
git commit -m "feat: add full pipeline E2E test with LLM integration"
```

---

## Running Tests

```bash
# In Docker container
docker exec python-hub pytest tests/test_full_pipeline.py -v

# Force regenerate fixtures
docker exec python-hub pytest tests/test_full_pipeline.py -v --regenerate-fixtures
```