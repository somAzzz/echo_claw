"""Failing tests for ws_protocol module.

Tests the WebSocket protocol for ESP32<->Hub communication.
"""
import json
import pytest
from src.protocol.ws_protocol import (
    parse_message,
    build_state_directive,
    build_tts_start,
    build_tts_end,
    build_error,
    build_text,
)


class TestParseMessage:
    """Test parse_message for JSON and binary messages."""

    def test_parse_audio_start_message(self):
        """parse_message should parse audio_start JSON and return dict."""
        msg = json.dumps({
            "type": "audio_start",
            "session_id": "sess1",
            "turn_id": 1
        })
        result = parse_message(msg.encode())
        assert result is not None
        assert result["type"] == "audio_start"
        assert result["session_id"] == "sess1"
        assert result["turn_id"] == 1

    def test_parse_audio_end_message(self):
        """parse_message should parse audio_end JSON and return dict."""
        msg = json.dumps({
            "type": "audio_end",
            "session_id": "sess1"
        })
        result = parse_message(msg.encode())
        assert result is not None
        assert result["type"] == "audio_end"

    def test_parse_playback_done_message(self):
        """parse_message should parse playback_done JSON and return dict."""
        msg = json.dumps({
            "type": "playback_done",
            "session_id": "sess1"
        })
        result = parse_message(msg.encode())
        assert result is not None
        assert result["type"] == "playback_done"

    def test_parse_session_end_message(self):
        """parse_message should parse session_end JSON and return dict."""
        msg = json.dumps({"type": "session_end"})
        result = parse_message(msg.encode())
        assert result is not None
        assert result["type"] == "session_end"

    def test_parse_binary_returns_none(self):
        """parse_message should return None for binary audio data."""
        binary_data = b"\x00\x01\x02\x03audio data"
        result = parse_message(binary_data)
        assert result is None


class TestBuildStateDirective:
    """Test building state directive messages."""

    def test_build_state_directive_idle(self):
        """build_state_directive should create idle state message."""
        msg = build_state_directive("sess1", 1)
        data = json.loads(msg)
        assert data["type"] == "state"
        assert data["state"] == "idle"
        assert data["session_id"] == "sess1"
        assert data["turn_id"] == 1

    def test_build_state_directive_listening(self):
        """build_state_directive should create listening state message."""
        msg = build_state_directive("sess1", 1, state="listening")
        data = json.loads(msg)
        assert data["state"] == "listening"

    def test_build_state_directive_thinking(self):
        """build_state_directive should create thinking state message."""
        msg = build_state_directive("sess1", 1, state="thinking")
        data = json.loads(msg)
        assert data["state"] == "thinking"


class TestBuildTtsStart:
    """Test building tts_start messages."""

    def test_build_tts_start_default_sample_rate(self):
        """build_tts_start should create tts_start with default sample rate."""
        msg = build_tts_start("sess1", 1)
        data = json.loads(msg)
        assert data["type"] == "tts_start"
        assert data["session_id"] == "sess1"
        assert data["turn_id"] == 1
        assert data["sample_rate"] == 16000

    def test_build_tts_start_custom_sample_rate(self):
        """build_tts_start should create tts_start with custom sample rate."""
        msg = build_tts_start("sess1", 1, sample_rate=24000)
        data = json.loads(msg)
        assert data["sample_rate"] == 24000


class TestBuildTtsEnd:
    """Test building tts_end messages."""

    def test_build_tts_end(self):
        """build_tts_end should create tts_end message."""
        msg = build_tts_end("sess1", 1)
        data = json.loads(msg)
        assert data["type"] == "tts_end"
        assert data["session_id"] == "sess1"
        assert data["turn_id"] == 1


class TestBuildError:
    """Test building error messages."""

    def test_build_error(self):
        """build_error should create error message."""
        msg = build_error("Something went wrong", "sess1", 1)
        data = json.loads(msg)
        assert data["type"] == "error"
        assert data["message"] == "Something went wrong"
        assert data["session_id"] == "sess1"
        assert data["turn_id"] == 1


class TestBuildText:
    """Test building text messages."""

    def test_build_text(self):
        """build_text should create text message with transcribed text."""
        msg = build_text("Hello world", "sess1", 1)
        data = json.loads(msg)
        assert data["type"] == "text"
        assert data["text"] == "Hello world"
        assert data["session_id"] == "sess1"
        assert data["turn_id"] == 1
