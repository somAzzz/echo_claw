"""Tests for ASR client using FunASR HTTP API."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import base64


class TestASRResult:
    """Test ASRResult dataclass."""

    def test_asr_result_create_with_text(self):
        from src.pipeline.asr import ASRResult
        result = ASRResult(text="hello world")
        assert result.text == "hello world"
        assert result.duration is None

    def test_asr_result_create_with_duration(self):
        from src.pipeline.asr import ASRResult
        result = ASRResult(text="test", duration=1.5)
        assert result.text == "test"
        assert result.duration == 1.5


class TestASRError:
    """Test ASRError exception."""

    def test_asr_error_is_exception(self):
        from src.pipeline.asr import ASRError
        error = ASRError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"


class TestASRClientInit:
    """Test ASRClient initialization."""

    def test_asr_client_default_values(self):
        from src.pipeline.asr import ASRClient
        client = ASRClient()
        assert client.base_url == "http://funasr-api:8001"
        assert client.timeout == 30.0

    def test_asr_client_custom_base_url(self):
        from src.pipeline.asr import ASRClient
        client = ASRClient(base_url="http://custom-api:9000")
        assert client.base_url == "http://custom-api:9000"
        assert client.timeout == 30.0

    def test_asr_client_custom_timeout(self):
        from src.pipeline.asr import ASRClient
        client = ASRClient(timeout=60.0)
        assert client.base_url == "http://funasr-api:8001"
        assert client.timeout == 60.0

    def test_asr_client_strips_trailing_slash(self):
        from src.pipeline.asr import ASRClient
        client = ASRClient(base_url="http://funasr-api:8001/")
        assert client.base_url == "http://funasr-api:8001"


class TestASRClientRecognize:
    """Test ASRClient.recognize method using httpx mock."""

    @pytest.mark.asyncio
    async def test_recognize_builds_correct_url(self):
        from src.pipeline.asr import ASRClient

        client = ASRClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "test", "duration": 0.5}

        call_info = {}

        class MockAsyncClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass

            async def post(self, url, **kwargs):
                call_info["url"] = url
                call_info["json"] = kwargs.get("json", {})
                return mock_response

        with patch("httpx.AsyncClient", return_value=MockAsyncClient()):
            await client.recognize(b"\x00" * 16000)

        assert "/asr/json" in call_info["url"]
        assert call_info["json"]["sample_rate"] == 16000

    @pytest.mark.asyncio
    async def test_recognize_raises_on_error_status(self):
        from src.pipeline.asr import ASRClient, ASRError

        client = ASRClient()

        class MockErrorResponse:
            status_code = 500
            text = "Server Error"

        class MockAsyncClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass

            async def post(self, url, **kwargs):
                return MockErrorResponse()

        with patch("httpx.AsyncClient", return_value=MockAsyncClient()):
            with pytest.raises(ASRError) as exc_info:
                await client.recognize(b"\x00" * 16000)
            assert "500" in str(exc_info.value)


class TestASRClientInterface:
    """Test ASRClient has expected interface."""

    def test_asr_client_has_recognize_method(self):
        from src.pipeline.asr import ASRClient
        client = ASRClient()
        assert hasattr(client, "recognize")
        assert callable(client.recognize)

    def test_asr_client_has_init_method(self):
        from src.pipeline.asr import ASRClient
        assert hasattr(ASRClient, "__init__")

    def test_asr_client_recognize_is_async(self):
        from src.pipeline.asr import ASRClient
        import inspect
        client = ASRClient()
        assert inspect.iscoroutinefunction(client.recognize)