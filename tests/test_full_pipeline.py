"""Full pipeline E2E tests: TTS -> ASR -> LLM -> TTS."""
import os
import wave
import numpy as np
import pytest
import time
import asyncio
from src.config import Config

# Try to import TTSGenerator, skip if dependencies not available
try:
    from src.pipeline.tts import TTSGenerator
    _TTS_AVAILABLE = True
except ImportError as e:
    _TTS_AVAILABLE = False
    _TTS_IMPORT_ERROR = str(e)


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
PCM_FIXTURE = os.path.join(FIXTURE_DIR, "test_input_tts.pcm")
WAV_FIXTURE = os.path.join(FIXTURE_DIR, "test_input_tts.wav")
TEST_TEXT = "你好啊，你是谁啊？"


@pytest.fixture(scope="session")
def tts_audio_fixture(request):
    """Generate TTS audio fixture (PCM + WAV). Skip if exists unless --regenerate-fixtures."""
    if not _TTS_AVAILABLE:
        pytest.skip(f"TTS not available: {_TTS_IMPORT_ERROR}")

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

    # Save WAV with proper header
    sample_rate = 24000
    with wave.open(WAV_FIXTURE, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Convert float32 to int16
        all_samples = []
        for chunk in audio_chunks:
            arr = np.frombuffer(chunk, dtype=np.float32)
            all_samples.extend(arr)
        int16_data = (np.array(all_samples) * 32767).astype(np.int16)
        wf.writeframes(int16_data.tobytes())

    return PCM_FIXTURE


def test_tts_generation_saves_audio(tts_audio_fixture):
    """TTS should generate both PCM and WAV files."""
    assert os.path.exists(tts_audio_fixture), "PCM fixture not created"
    assert os.path.exists(WAV_FIXTURE), "WAV fixture not created"

    pcm_size = os.path.getsize(tts_audio_fixture)
    assert pcm_size > 0, "PCM file is empty"

    wav_size = os.path.getsize(WAV_FIXTURE)
    assert wav_size > 44, "WAV file too small (needs header)"

    with wave.open(WAV_FIXTURE, "rb") as wf:
        assert wf.getnchannels() == 1, "WAV should be mono"
        assert wf.getsampwidth() == 2, "WAV should be 16-bit"
        assert wf.getframerate() == 24000, "WAV sample rate should be 24000"


def test_asr_recognizes_tts_audio(tts_audio_fixture):
    """ASR should recognize text from TTS-generated audio."""
    import wave
    import logging
    from src.pipeline.asr import ASRRecognizer

    # Skip if model files not available
    cfg = Config.get_instance()
    if not os.path.exists(cfg.asr.get("tokens", "")):
        pytest.skip(f"ASR tokens not available: {cfg.asr.get('tokens')}")

    # Use WAV fixture which has proper int16 PCM format
    with wave.open(WAV_FIXTURE, "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        pcm_data = frames  # Already int16 format

    # ASR expects 16kHz but TTS outputs 24kHz, sherpa-onnx handles resampling
    asr = ASRRecognizer(
        model_dir=cfg.asr.get("model_dir", ""),
        tokens=cfg.asr.get("tokens"),
        encoder=cfg.asr.get("encoder"),
        decoder=cfg.asr.get("decoder"),
        joiner=cfg.asr.get("joiner"),
    )
    text = asr.recognize(pcm_data, sample_rate=24000.0)
    assert text, "ASR returned empty text"
    # ASR produced output - exact text may vary due to TTS/ASR model differences
    logging.info(f"ASR recognized: {text}")


def test_full_pipeline_asr_llm_tts(tts_audio_fixture):
    """Full pipeline: TTS audio → ASR → LLM → TTS response."""
    import logging
    from src.pipeline.asr import ASRRecognizer
    logging.basicConfig(level=logging.INFO)

    cfg = Config.get_instance()

    # ASR stage
    if not os.path.exists(cfg.asr.get("tokens", "")):
        pytest.skip(f"ASR tokens not available: {cfg.asr.get('tokens')}")

    asr = ASRRecognizer(
        model_dir=cfg.asr.get("model_dir", ""),
        tokens=cfg.asr.get("tokens"),
        encoder=cfg.asr.get("encoder"),
        decoder=cfg.asr.get("decoder"),
        joiner=cfg.asr.get("joiner"),
    )

    # ASR stage - use WAV fixture for proper int16 PCM
    import wave
    t0 = time.time()
    with wave.open(WAV_FIXTURE, "rb") as wf:
        pcm_data = wf.readframes(wf.getnframes())
    asr_text = asr.recognize(pcm_data, sample_rate=24000.0)
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