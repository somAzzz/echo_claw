"""Tests for TTS client using edge-tts."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Check if edge_tts is available
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False


class TestTTSError:
    """Test TTSError exception."""

    def test_tts_error_is_exception(self):
        # TTSError is defined in tts module, which requires edge_tts to import
        # We test that it exists and is an exception by checking the module
        import importlib
        import sys

        # Temporarily mock edge_tts to allow import
        if not EDGE_TTS_AVAILABLE:
            import types
            mock_edge_tts = types.ModuleType("edge_tts")
            mock_edge_tts.Communicate = MagicMock
            sys.modules["edge_tts"] = mock_edge_tts

            # Reload the module to get TTSError
            import importlib
            from src.pipeline import tts
            importlib.reload(tts)

            error = tts.TTSError("test error")
            assert isinstance(error, Exception)
            assert str(error) == "test error"
        else:
            from src.pipeline.tts import TTSError
            error = TTSError("test error")
            assert isinstance(error, Exception)
            assert str(error) == "test error"


@pytest.mark.skipif(not EDGE_TTS_AVAILABLE, reason="edge_tts not installed")
class TestTTSClientInit:
    """Test TTSClient initialization."""

    def test_tts_client_default_voice(self):
        from src.pipeline.tts import TTSClient
        client = TTSClient()
        assert client.voice == "zh-CN-XiaoxiaoNeural"

    def test_tts_client_custom_voice(self):
        from src.pipeline.tts import TTSClient
        client = TTSClient(voice="zh-CN-YunxiNeural")
        assert client.voice == "zh-CN-YunxiNeural"


@pytest.mark.skipif(not EDGE_TTS_AVAILABLE, reason="edge_tts not installed")
class TestTTSClientSynthesize:
    """Test TTSClient.synthesize method."""

    @pytest.mark.asyncio
    async def test_synthesize_is_async_generator(self):
        from src.pipeline.tts import TTSClient

        client = TTSClient()

        # Mock edge_tts.Communicate
        mock_communicate = MagicMock()
        mock_communicate.save = AsyncMock()

        with patch("edge_tts.Communicate", return_value=mock_communicate):
            # Mock asyncio.create_subprocess_exec
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"\x00" * 4096, b""))
            mock_process.returncode = 0

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                result = client.synthesize("你好")

                # Check it's an async generator
                import inspect
                assert inspect.isasyncgen(result)

                # Consume the generator to verify it works
                chunks = []
                async for chunk in result:
                    chunks.append(chunk)
                assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_synthesize_yields_chunks(self):
        from src.pipeline.tts import TTSClient

        client = TTSClient()

        mock_communicate = MagicMock()
        mock_communicate.save = AsyncMock()

        with patch("edge_tts.Communicate", return_value=mock_communicate):
            mock_process = AsyncMock()
            # Simulate multiple chunks
            audio_data = b"\x00" * 8192  # More than 4096 to test chunking
            mock_process.communicate = AsyncMock(return_value=(audio_data, b""))
            mock_process.returncode = 0

            with patch("asyncio.create_subprocess_exec", return_value=mock_process):
                chunks = []
                async for chunk in client.synthesize("hello"):
                    chunks.append(chunk)

                # Should have 2 chunks (4096 bytes each for 8192 total)
                assert len(chunks) == 2

    @pytest.mark.asyncio
    async def test_synthesize_uses_correct_ffmpeg_args(self):
        from src.pipeline.tts import TTSClient

        client = TTSClient()

        mock_communicate = MagicMock()
        mock_communicate.save = AsyncMock()

        with patch("edge_tts.Communicate", return_value=mock_communicate):
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 0

            with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
                async for _ in client.synthesize("test"):
                    pass

                # Verify ffmpeg was called with correct args
                call_args = mock_exec.call_args
                assert "ffmpeg" in str(call_args)


@pytest.mark.skipif(not EDGE_TTS_AVAILABLE, reason="edge_tts not installed")
class TestTTSClientInterface:
    """Test TTSClient has expected interface."""

    def test_tts_client_has_synthesize_method(self):
        from src.pipeline.tts import TTSClient
        client = TTSClient()
        assert hasattr(client, "synthesize")
        assert callable(client.synthesize)

    def test_tts_client_has_init_method(self):
        from src.pipeline.tts import TTSClient
        assert hasattr(TTSClient, "__init__")

    def test_tts_client_has_voice_attribute(self):
        from src.pipeline.tts import TTSClient
        client = TTSClient()
        assert hasattr(client, "voice")