import asyncio
import os
import pytest

# Check if asr module can be imported
try:
    from src.pipeline.asr import ASRClient
    ASR_IMPORT_FAILED = False
except ImportError as e:
    ASR_IMPORT_FAILED = str(e)
    ASRClient = None

# Check if asr model exists
ASR_MODEL_AVAILABLE = os.path.exists("/app/models/asr/asr-onnx.onnx") and not ASR_IMPORT_FAILED


@pytest.mark.skipif(ASR_IMPORT_FAILED, reason=f"ASR import failed: {ASR_IMPORT_FAILED}")
@pytest.mark.skipif(not ASR_MODEL_AVAILABLE, reason="ASR model not available")
def test_asr_client_initializes():
    client = ASRClient(base_url="http://localhost:8081")
    assert client.base_url == "http://localhost:8081"
    assert client.timeout == 30.0


@pytest.mark.skipif(ASR_IMPORT_FAILED, reason=f"ASR import failed: {ASR_IMPORT_FAILED}")
@pytest.mark.skipif(not ASR_MODEL_AVAILABLE, reason="ASR model not available")
def test_asr_recognize_from_pcm():
    client = ASRClient(base_url="http://localhost:8081")
    fake_pcm = b"\x00" * 4800  # 300ms at 16kHz
    result = asyncio.run(client.recognize(fake_pcm, 16000))
    assert isinstance(result.text, str)


def test_asr_client_interface():
    """Test that ASRClient has the expected interface (methods/attrs)."""
    if ASR_IMPORT_FAILED:
        if "libonnxruntime" in ASR_IMPORT_FAILED:
            pytest.skip(f"System dependency not available: {ASR_IMPORT_FAILED}")
        else:
            pytest.fail(f"ASR import failed unexpectedly: {ASR_IMPORT_FAILED}")

    client = ASRClient(base_url="http://localhost:8081")
    assert hasattr(client, 'recognize')
    assert hasattr(client, 'base_url')
    assert hasattr(client, 'timeout')