"""State machine for voice assistant with ESP32 audio pipeline.

States:
- IDLE: waiting for ESP32 audio_start
- LISTENING: receiving audio from ESP32
- PROCESSING: running ASR->LLM->TTS pipeline
- SPEAKING: sending TTS audio to ESP32

Protocol messages (ESP32->Hub):
- audio_start: starts a new turn (session_id, turn_id)
- audio_end: audio transmission complete
- playback_done: ESP32 finished playing TTS audio
- session_end: end of session

Protocol messages (Hub->ESP32):
- state: current state directive
- text: transcribed text
- error: error message
- tts_start: TTS audio beginning
- tts_end: TTS audio end
"""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Any


class State(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()


@dataclass
class PendingTurn:
    """Represents an in-progress voice turn."""
    session_id: str
    turn_id: int
    audio_chunks: list[bytes] = field(default_factory=list)
    text: Optional[str] = None


class StateMachine:
    """State machine managing voice assistant interaction with ESP32."""

    def __init__(self):
        self.state = State.IDLE
        self.current_turn: Optional[PendingTurn] = None

    def handle_message(self, message: dict[str, Any]) -> None:
        """Handle a message from ESP32.

        Args:
            message: Dict with 'type' key and message-specific fields.
                - audio_start: {'type': 'audio_start', 'session_id': str, 'turn_id': int}
                - audio_end: {'type': 'audio_end', 'session_id': str}
                - playback_done: {'type': 'playback_done', 'session_id': str}
                - session_end: {'type': 'session_end'}
                - tts_ready: {'type': 'tts_ready'}
        """
        msg_type = message.get("type")

        if msg_type == "audio_start":
            self._handle_audio_start(message)
        elif msg_type == "audio_end":
            self._handle_audio_end(message)
        elif msg_type == "tts_ready":
            self._handle_tts_ready()
        elif msg_type == "playback_done":
            self._handle_playback_done(message)
        elif msg_type == "session_end":
            self._handle_session_end()
        else:
            pass  # Ignore unknown message types

    def handle_cancel(self) -> None:
        """Handle client cancel request during processing.

        Note: This only cancels between turns, not during active operations.
        """
        if self.state == State.PROCESSING or self.state == State.SPEAKING:
            self.state = State.IDLE
            self.current_turn = None

    def _handle_audio_start(self, message: dict) -> None:
        """Handle audio_start - starts new turn or preempts processing."""
        session_id = message["session_id"]
        turn_id = message["turn_id"]

        # Preemption: if we're processing or speaking, cancel and restart
        if self.state in (State.PROCESSING, State.SPEAKING):
            # Signal preemption to higher level by clearing current turn
            self.current_turn = None

        # Always start fresh with new turn
        self.current_turn = PendingTurn(session_id=session_id, turn_id=turn_id)
        self.state = State.LISTENING

    def _handle_audio_end(self, message: dict) -> None:
        """Handle audio_end - transition to PROCESSING."""
        if self.state == State.LISTENING and self.current_turn is not None:
            self.state = State.PROCESSING

    def _handle_tts_ready(self) -> None:
        """Handle tts_ready - transition to SPEAKING."""
        if self.state == State.PROCESSING:
            self.state = State.SPEAKING

    def _handle_playback_done(self, message: dict) -> None:
        """Handle playback_done - return to IDLE."""
        if self.state == State.SPEAKING:
            self.state = State.IDLE
            self.current_turn = None

    def _handle_session_end(self) -> None:
        """Handle session_end - return to IDLE from any state."""
        self.state = State.IDLE
        self.current_turn = None
