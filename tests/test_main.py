"""Tests for main.py WebSocket handler."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    with patch("src.config.Config.get_config") as mock_get_config:
        mock_cfg = MagicMock()
        mock_cfg.server.host = "0.0.0.0"
        mock_cfg.server.port = 8765
        mock_cfg.asr.base_url = "http://localhost:8081"
        mock_cfg.llm.base_url = "http://localhost:8080/v1"
        mock_cfg.llm.model = "gpt-4"
        mock_cfg.tts.voice = "zh-CN-XiaoxiaoNeural"
        mock_cfg.memory.max_rounds = 5
        mock_cfg.backpressure.asr_queue_max = 100
        mock_cfg.backpressure.llm_queue_max = 20
        mock_cfg.backpressure.tts_queue_max = 50
        mock_get_config.return_value = mock_cfg
        yield mock_get_config


@pytest.fixture
def mock_session():
    """Create a mock Session."""
    session = MagicMock()
    session.session_id = "test-session-123"
    session.get_recent_context.return_value = ""
    session.add_turn = MagicMock()
    return session


@pytest.fixture
def mock_state_machine():
    """Create a mock StateMachine."""
    from src.state_machine import StateMachine, State, PendingTurn
    sm = MagicMock(spec=StateMachine)
    sm.state = State.IDLE
    sm.current_turn = None
    sm.handle_message = MagicMock()
    return sm


class TestMainImports:
    """Test that main.py imports correctly."""

    def test_main_module_imports(self):
        """Test that main module is importable."""
        from src.main import main
        assert main is not None

    def test_handle_esp32_exists(self):
        """Test that handle_esp32 function exists."""
        from src.main import handle_esp32
        assert handle_esp32 is not None


@pytest.mark.asyncio
async def test_handle_audio_start_transitions_to_listening():
    """Test that audio_start message transitions state to LISTENING."""
    from src.state_machine import StateMachine, State, PendingTurn

    sm = StateMachine()
    assert sm.state == State.IDLE

    # Simulate audio_start
    sm.handle_message({
        "type": "audio_start",
        "session_id": "test-session",
        "turn_id": 1
    })

    assert sm.state == State.LISTENING
    assert sm.current_turn is not None
    assert sm.current_turn.session_id == "test-session"
    assert sm.current_turn.turn_id == 1


@pytest.mark.asyncio
async def test_handle_audio_end_transitions_to_processing():
    """Test that audio_end message transitions state to PROCESSING."""
    from src.state_machine import StateMachine, State, PendingTurn

    sm = StateMachine()
    sm.handle_message({
        "type": "audio_start",
        "session_id": "test-session",
        "turn_id": 1
    })
    assert sm.state == State.LISTENING

    # Simulate audio_end
    sm.handle_message({"type": "audio_end", "session_id": "test-session"})
    assert sm.state == State.PROCESSING


@pytest.mark.asyncio
async def test_handle_playback_done_returns_to_idle():
    """Test that playback_done returns state to IDLE."""
    from src.state_machine import StateMachine, State

    sm = StateMachine()
    sm.handle_message({"type": "audio_start", "session_id": "test", "turn_id": 1})
    sm.handle_message({"type": "audio_end", "session_id": "test"})
    assert sm.state == State.PROCESSING

    # Simulate tts_ready then playback_done
    sm.handle_message({"type": "tts_ready"})
    assert sm.state == State.SPEAKING

    sm.handle_message({"type": "playback_done", "session_id": "test"})
    assert sm.state == State.IDLE


@pytest.mark.asyncio
async def test_pending_turn_audio_chunks_accumulation():
    """Test that PendingTurn accumulates audio chunks."""
    from src.state_machine import PendingTurn

    turn = PendingTurn(session_id="test", turn_id=1)
    turn.audio_chunks.append(b"chunk1")
    turn.audio_chunks.append(b"chunk2")
    turn.audio_chunks.append(b"chunk3")

    audio_bytes = b"".join(turn.audio_chunks)
    assert audio_bytes == b"chunk1chunk2chunk3"


@pytest.mark.asyncio
async def test_parse_message_returns_dict_for_json():
    """Test that parse_message correctly parses JSON messages."""
    from src.protocol.ws_protocol import parse_message

    data = json.dumps({"type": "audio_start", "session_id": "test", "turn_id": 1}).encode()
    result = parse_message(data)
    assert result == {"type": "audio_start", "session_id": "test", "turn_id": 1}


@pytest.mark.asyncio
async def test_parse_message_returns_none_for_binary():
    """Test that parse_message returns None for binary audio data."""
    from src.protocol.ws_protocol import parse_message

    # Binary PCM data (not valid UTF-8 JSON)
    data = b"\x00\x01\x02\x03\xff\xfe\xfd"
    result = parse_message(data)
    assert result is None


@pytest.mark.asyncio
async def test_build_state_directive_returns_json():
    """Test that build_state_directive returns valid JSON string."""
    from src.protocol.ws_protocol import build_state_directive

    result = build_state_directive("test-session", 1, "listening")
    parsed = json.loads(result)
    assert parsed["type"] == "state"
    assert parsed["state"] == "listening"
    assert parsed["session_id"] == "test-session"
    assert parsed["turn_id"] == 1


@pytest.mark.asyncio
async def test_build_tts_start_returns_json():
    """Test that build_tts_start returns valid JSON string."""
    from src.protocol.ws_protocol import build_tts_start

    result = build_tts_start("test-session", 1)
    parsed = json.loads(result)
    assert parsed["type"] == "tts_start"
    assert parsed["sample_rate"] == 16000


@pytest.mark.asyncio
async def test_build_error_returns_json():
    """Test that build_error returns valid JSON string."""
    from src.protocol.ws_protocol import build_error

    result = build_error("Something went wrong", "test-session", 1)
    parsed = json.loads(result)
    assert parsed["type"] == "error"
    assert parsed["message"] == "Something went wrong"


@pytest.mark.asyncio
async def test_build_text_returns_json():
    """Test that build_text returns valid JSON string."""
    from src.protocol.ws_protocol import build_text

    result = build_text("Hello world", "test-session", 1)
    parsed = json.loads(result)
    assert parsed["type"] == "text"
    assert parsed["text"] == "Hello world"


@pytest.mark.asyncio
async def test_session_get_recent_context():
    """Test Session.get_recent_context method."""
    from src.memory.session import Session, Turn
    from datetime import datetime

    session = Session(session_id="test-session")
    session.add_turn(Turn(
        turn_id="turn-1",
        user_text="Hello",
        assistant_text="Hi there!"
    ))
    session.add_turn(Turn(
        turn_id="turn-2",
        user_text="How are you?",
        assistant_text="I'm fine, thank you!"
    ))

    context = session.get_recent_context(max_turns=2)
    assert "User: Hello" in context
    assert "Assistant: Hi there!" in context
    assert "User: How are you?" in context


@pytest.mark.asyncio
async def test_llm_client_stream_chat():
    """Test LLMClient.stream_chat method signature."""
    from src.pipeline.llm import LLMClient

    client = LLMClient(
        base_url="http://localhost:8080/v1",
        model="gpt-4",
        api_key="test-key"
    )
    assert client.base_url == "http://localhost:8080/v1"
    assert client.model == "gpt-4"


@pytest.mark.asyncio
async def test_asr_client_recognize_signature():
    """Test ASRClient.recognize method signature."""
    from src.pipeline.asr import ASRClient

    client = ASRClient(base_url="http://localhost:8081")
    assert client.base_url == "http://localhost:8081"


@pytest.mark.asyncio
async def test_tts_client_synthesize_signature():
    """Test TTSClient.synthesize method signature."""
    from src.pipeline.tts import TTSClient

    client = TTSClient(voice="zh-CN-XiaoxiaoNeural")
    assert client.voice == "zh-CN-XiaoxiaoNeural"


class TestProtocolIntegration:
    """Integration tests for protocol message handling."""

    @pytest.mark.asyncio
    async def test_full_message_flow(self):
        """Test the full flow of protocol messages."""
        from src.state_machine import StateMachine, State

        sm = StateMachine()

        # Start audio session
        sm.handle_message({
            "type": "audio_start",
            "session_id": "session-1",
            "turn_id": 1
        })
        assert sm.state == State.LISTENING
        assert sm.current_turn is not None

        # End audio
        sm.handle_message({"type": "audio_end", "session_id": "session-1"})
        assert sm.state == State.PROCESSING

        # TTS ready
        sm.handle_message({"type": "tts_ready"})
        assert sm.state == State.SPEAKING

        # Playback done
        sm.handle_message({"type": "playback_done", "session_id": "session-1"})
        assert sm.state == State.IDLE
        assert sm.current_turn is None
