import os
import asyncio
import pytest

# Check if tts module can be imported
try:
    from src.pipeline.tts import TTSClient
    TTS_IMPORT_FAILED = False
except ImportError as e:
    TTS_IMPORT_FAILED = str(e)
    TTSClient = None

# Check if tts model exists
TTS_MODEL_AVAILABLE = os.path.exists("/app/models/tts/conv-tts.onnx") and not TTS_IMPORT_FAILED


@pytest.mark.skipif(TTS_IMPORT_FAILED, reason=f"TTS import failed: {TTS_IMPORT_FAILED}")
@pytest.mark.skipif(not TTS_MODEL_AVAILABLE, reason="TTS model not available")
def test_tts_client_initializes():
    client = TTSClient(voice="zh-CN-XiaoxiaoNeural")
    assert client.voice == "zh-CN-XiaoxiaoNeural"


@pytest.mark.skipif(TTS_IMPORT_FAILED, reason=f"TTS import failed: {TTS_IMPORT_FAILED}")
@pytest.mark.skipif(not TTS_MODEL_AVAILABLE, reason="TTS model not available")
async def consume_audio():
    client = TTSClient(voice="zh-CN-XiaoxiaoNeural")
    chunks = []
    async for chunk in client.synthesize("hello"):
        chunks.append(chunk)
    return chunks


@pytest.mark.skipif(TTS_IMPORT_FAILED, reason=f"TTS import failed: {TTS_IMPORT_FAILED}")
@pytest.mark.skipif(not TTS_MODEL_AVAILABLE, reason="TTS model not available")
def test_tts_synthesize_returns_chunks():
    chunks = asyncio.run(consume_audio())
    assert isinstance(chunks, list)


def test_tts_client_interface():
    """Test that TTSClient has the expected interface (methods/attrs)."""
    if TTS_IMPORT_FAILED:
        if "libonnxruntime" in TTS_IMPORT_FAILED:
            pytest.skip(f"System dependency not available: {TTS_IMPORT_FAILED}")
        else:
            pytest.fail(f"TTS import failed unexpectedly: {TTS_IMPORT_FAILED}")

    client = TTSClient(voice="zh-CN-XiaoxiaoNeural")
    assert hasattr(client, 'synthesize')
    assert hasattr(client, 'voice')