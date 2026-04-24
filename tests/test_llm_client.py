import pytest
from unittest.mock import patch, MagicMock
import aiohttp

from src.pipeline.llm import LLMClient


def test_llm_client_initialization():
    """LLMClient should be initializable with base_url, model, and optional api_key."""
    client = LLMClient(base_url="http://localhost:8080/v1", model="test-model")
    assert client.base_url == "http://localhost:8080/v1"
    assert client.model == "test-model"


def test_llm_client_initialization_with_api_key():
    """LLMClient should store api_key if provided."""
    client = LLMClient(
        base_url="http://localhost:8080/v1",
        model="test-model",
        api_key="secret-key"
    )
    assert client._api_key == "secret-key"


class MockStreamContent:
    """Mock aiohttp response content (async iterator)."""
    def __init__(self, lines):
        self._lines = lines

    def __aiter__(self):
        return self._async_iter()

    async def _async_iter(self):
        for line in self._lines:
            yield line


class MockStreamResponse:
    """Mock aiohttp response with streaming content."""
    def __init__(self, lines):
        self.content = MockStreamContent(lines)


class PostContextManager:
    """Mock async context manager for session.post()"""
    def __init__(self, coro):
        self._coro = coro

    async def __aenter__(self):
        return await self._coro

    async def __aexit__(self, *args):
        return None


class MockClientSession:
    """Mock aiohttp ClientSession that supports async context manager protocol."""
    def __init__(self, response_lines):
        self._response_lines = response_lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def post(self, url, **kwargs):
        """Return an async context manager that yields MockStreamResponse."""
        async def post_cm():
            return MockStreamResponse(self._response_lines)
        return PostContextManager(post_cm())


@pytest.mark.asyncio
async def test_stream_chat_yields_tokens():
    """stream_chat should yield tokens from SSE response."""
    client = LLMClient(
        base_url="http://mock-server:8080/v1",
        model="test-model"
    )

    lines = [
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n',
        b'data: [DONE]\n',
    ]

    mock_session = MockClientSession(lines)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        tokens = []
        async for token in client.stream_chat([{"role": "user", "content": "hi"}]):
            tokens.append(token)

        assert tokens == ["Hello", " world"]


@pytest.mark.asyncio
async def test_stream_chat_with_system_message():
    """stream_chat should include system message in payload when provided."""
    client = LLMClient(
        base_url="http://mock-server:8080/v1",
        model="test-model"
    )

    captured_json = {}

    class PayloadCapturingSession(MockClientSession):
        def post(self, url, json=None, **kwargs):
            captured_json["url"] = url
            captured_json["json"] = json
            return PostContextManager(self._make_response())

        async def _make_response(self):
            return MockStreamResponse([
                b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n',
                b'data: [DONE]\n',
            ])

    mock_session = PayloadCapturingSession([])

    with patch("aiohttp.ClientSession", return_value=mock_session):
        async for _ in client.stream_chat(
            [{"role": "user", "content": "hi"}],
            system="You are a helpful assistant"
        ):
            pass

    assert "system" in captured_json["json"]
    assert captured_json["json"]["system"] == "You are a helpful assistant"


@pytest.mark.asyncio
async def test_stream_chat_handles_empty_lines():
    """stream_chat should skip empty lines and done markers."""
    client = LLMClient(
        base_url="http://mock-server:8080/v1",
        model="test-model"
    )

    lines = [
        b'',
        b'\n',
        b'data: {"choices":[{"delta":{"content":"Test"}}]}\n',
        b'data: [DONE]\n',
        b'',
    ]

    mock_session = MockClientSession(lines)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        tokens = []
        async for token in client.stream_chat([{"role": "user", "content": "hi"}]):
            tokens.append(token)

        assert tokens == ["Test"]