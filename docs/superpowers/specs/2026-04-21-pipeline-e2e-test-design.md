# Full Pipeline E2E Test Design

## Overview

Test the voice assistant pipeline end-to-end: TTS generates audio from text, audio is fed to ASR, ASR output is sent to LLM, LLM response is synthesized back to audio via TTS.

## Requirements Summary

| Aspect | Choice | Description |
|--------|--------|-------------|
| Audio Generation | C | Generate AND save to file - TTS generates both PCM and WAV files |
| Validation | A+C | Content correctness (ASR output contains expected text) + Performance metrics (stage latencies) |
| Environment | A | Docker container (models mounted, dependencies ready) |
| Framework | A | pytest (existing tests use pytest) |

## Test Flow

```
[Text Input] → TTS → [PCM Audio] → ASR → [Text] → LLM → [Response Text] → TTS → [Output Audio]
                     ↓
               Save PCM + WAV to fixture
```

## File Structure

```
tests/
  fixtures/
    test_input_tts.pcm    # PCM for pipeline processing
    test_input_tts.wav    # WAV for human verification
  test_full_pipeline.py   # Main e2e test file
```

Note: Both PCM and WAV are generated. PCM (raw audio) is used for ASR processing. WAV (with header) is saved for manual listening/verification.

## Components

### Test Input
- Text: "你好啊，你是谁啊？"
- Expected ASR output should contain: "你好" or "谁" (flexible matching)

### Fixtures

**`tts_audio_fixture()`**
- Scope: session (generated once per test run)
- If fixture files (`tests/fixtures/test_input_tts.pcm` and `.wav`) exist, skip generation
- Otherwise, use TTSGenerator to generate audio from test text
- Save both PCM (raw) and WAV (with wave header) to fixture directory
- Return path to PCM fixture

**Fixture Regeneration Policy:**
- Fixtures are regenerated if either the fixture file is missing OR the `--regenerate-fixtures` pytest flag is passed
- In CI, always regenerate fixtures to avoid stale test data
- The fixture should be version-controlled since it represents known-good test input

### Test Cases

**1. `test_tts_generation_saves_audio()`**
- Generate TTS audio and verify both PCM and WAV files are saved
- Assert PCM file size > 0
- Assert WAV file size > 0 and has valid WAV header
- Useful for confirming TTS model works before running full pipeline

**2. `test_asr_recognizes_tts_audio()`**
- Load PCM from fixture
- Feed to ASRRecognizer
- Verify ASR output contains expected Chinese text keywords

**3. `test_full_pipeline_asr_llm_tts()`**
- Load PCM from fixture → ASR → Text
- Send text to LLMClient → Stream response
- Record performance metrics for each stage
- Assert LLM response is non-empty (required, not optional)
- Final TTS synthesis to verify complete pipeline

## Performance Metrics

Each stage records elapsed time (informational, no strict SLOs for initial version):

| Stage | Metric |
|-------|--------|
| TTS generation | Time to generate input audio |
| ASR recognition | Time to decode audio to text |
| LLM response | Time to first token + total stream time |
| Final TTS | Time to synthesize LLM response |

Metrics are logged but not used for pass/fail in v1. This establishes baseline performance data.

## Dependencies

- pytest-asyncio (for async test support)
- sherpa-onnx (for TTS/ASR)
- LLM server running at `LLM_BASE_URL` (required for full pipeline test)

## Running Tests

```bash
# Inside Docker container
docker exec python-hub pytest tests/test_full_pipeline.py -v

# Force regenerate fixtures
docker exec python-hub pytest tests/test_full_pipeline.py -v --regenerate-fixtures

# Or locally (requires models mounted)
pytest tests/test_full_pipeline.py -v
```

## Error Handling

- If TTS model not available: pytest.skip with message "TTS model not available"
- If ASR model not available: pytest.skip with message "ASR model not available"
- If LLM not reachable: fail with connection error (LLM is required, not skippable)
- If fixture generation fails: fail, do not skip (fixture setup must succeed)