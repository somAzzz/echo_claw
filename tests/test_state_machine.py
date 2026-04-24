"""Failing tests for new state machine with IDLE/LISTENING/PROCESSING/SPEAKING states.

These tests define the expected behavior for the refactored state machine.
"""
import pytest
from src.state_machine import State, StateMachine, PendingTurn


class TestIdleToListening:
    """Test IDLE -> LISTENING transition on audio_start."""

    def test_idle_to_listening_on_audio_start(self):
        """When ESP32 sends audio_start in IDLE state, transition to LISTENING."""
        sm = StateMachine()
        assert sm.state == State.IDLE

        sm.handle_message({"type": "audio_start", "session_id": "sess1", "turn_id": 1})
        assert sm.state == State.LISTENING
        assert sm.current_turn is not None
        assert sm.current_turn.session_id == "sess1"
        assert sm.current_turn.turn_id == 1


class TestListeningToProcessing:
    """Test LISTENING -> PROCESSING transition on audio_end."""

    def test_listening_to_processing_on_audio_end(self):
        """When ESP32 sends audio_end in LISTENING state, transition to PROCESSING."""
        sm = StateMachine()
        sm.handle_message({"type": "audio_start", "session_id": "sess1", "turn_id": 1})
        assert sm.state == State.LISTENING

        sm.handle_message({"type": "audio_end", "session_id": "sess1"})
        assert sm.state == State.PROCESSING


class TestPreemption:
    """Test preemption logic - new audio_start cancels pending processing."""

    def test_preemption_cancels_processing(self):
        """When audio_start arrives during PROCESSING, cancel processing and go to LISTENING."""
        sm = StateMachine()
        sm.handle_message({"type": "audio_start", "session_id": "sess1", "turn_id": 1})
        sm.handle_message({"type": "audio_end", "session_id": "sess1"})
        assert sm.state == State.PROCESSING

        # New audio starts during processing - this should preempt
        sm.handle_message({"type": "audio_start", "session_id": "sess2", "turn_id": 2})
        assert sm.state == State.LISTENING
        assert sm.current_turn.session_id == "sess2"
        assert sm.current_turn.turn_id == 2


class TestSpeakingState:
    """Test SPEAKING state transitions."""

    def test_processing_to_speaking(self):
        """When TTS is ready, transition to SPEAKING."""
        sm = StateMachine()
        sm.handle_message({"type": "audio_start", "session_id": "sess1", "turn_id": 1})
        sm.handle_message({"type": "audio_end", "session_id": "sess1"})
        sm.handle_message({"type": "tts_ready"})
        assert sm.state == State.SPEAKING

    def test_speaking_to_idle_on_playback_done(self):
        """When ESP32 sends playback_done, return to IDLE."""
        sm = StateMachine()
        sm.handle_message({"type": "audio_start", "session_id": "sess1", "turn_id": 1})
        sm.handle_message({"type": "audio_end", "session_id": "sess1"})
        sm.handle_message({"type": "tts_ready"})
        sm.handle_message({"type": "playback_done", "session_id": "sess1"})
        assert sm.state == State.IDLE


class TestSessionEnd:
    """Test session_end returns to IDLE from any state."""

    def test_session_end_from_any_state(self):
        """session_end should return to IDLE regardless of current state."""
        sm = StateMachine()

        # From IDLE
        sm.handle_message({"type": "session_end"})
        assert sm.state == State.IDLE

        # From LISTENING
        sm.handle_message({"type": "audio_start", "session_id": "sess1", "turn_id": 1})
        sm.handle_message({"type": "session_end"})
        assert sm.state == State.IDLE

        # From PROCESSING
        sm.handle_message({"type": "audio_start", "session_id": "sess1", "turn_id": 1})
        sm.handle_message({"type": "audio_end", "session_id": "sess1"})
        sm.handle_message({"type": "session_end"})
        assert sm.state == State.IDLE

        # From SPEAKING
        sm.handle_message({"type": "audio_start", "session_id": "sess1", "turn_id": 1})
        sm.handle_message({"type": "audio_end", "session_id": "sess1"})
        sm.handle_message({"type": "tts_ready"})
        sm.handle_message({"type": "session_end"})
        assert sm.state == State.IDLE


class TestPendingTurn:
    """Test PendingTurn dataclass."""

    def test_pending_turn_stores_session_and_turn_id(self):
        """PendingTurn should store session_id and turn_id."""
        turn = PendingTurn(session_id="sess1", turn_id=42)
        assert turn.session_id == "sess1"
        assert turn.turn_id == 42
        assert turn.audio_chunks == []
        assert turn.text is None

    def test_pending_turn_can_store_audio_and_text(self):
        """PendingTurn should be able to store audio_chunks and text."""
        turn = PendingTurn(session_id="sess1", turn_id=1)
        turn.audio_chunks.append(b"audio_bytes")
        turn.text = "transcribed text"
        assert turn.audio_chunks == [b"audio_bytes"]
        assert turn.text == "transcribed text"
