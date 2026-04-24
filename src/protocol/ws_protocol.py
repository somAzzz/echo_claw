"""WebSocket protocol for ESP32 <-> Hub communication.

Protocol messages (ESP32 -> Hub):
- audio_start: starts a new turn with session_id and turn_id
- audio_end: audio transmission complete
- playback_done: ESP32 finished playing TTS audio
- session_end: end of session

Protocol messages (Hub -> ESP32):
- state: current state directive (idle, listening, thinking, speaking)
- text: transcribed text
- error: error message
- tts_start: TTS audio beginning with sample_rate
- tts_end: TTS audio end
"""
import json
from typing import Optional, Union


def parse_message(data: Union[bytes, bytearray, str]) -> Optional[dict]:
    """Parse incoming WebSocket message.

    Args:
        data: Raw bytes or str from WebSocket connection.

    Returns:
        Parsed dict for JSON messages, None for binary audio data.
        Binary data is detected by attempting to decode as UTF-8 and
        checking if it's valid JSON.
    """
    # Handle string data (already decoded text)
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None

    # Handle binary data
    try:
        text = data.decode("utf-8")
        return json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Binary audio data - not JSON
        return None


def build_state_directive(
    session_id: str,
    turn_id: int,
    state: str = "idle"
) -> str:
    """Build a state directive message.

    Args:
        session_id: Session identifier.
        turn_id: Turn identifier.
        state: State value (idle, listening, thinking, speaking).

    Returns:
        JSON string with state directive.
    """
    return json.dumps({
        "type": "state",
        "state": state,
        "session_id": session_id,
        "turn_id": turn_id,
    })


def build_tts_start(
    session_id: str,
    turn_id: int,
    sample_rate: int = 16000,
    format: str = "pcm_s16le",
    channels: int = 1
) -> str:
    """Build a tts_start message.

    Args:
        session_id: Session identifier.
        turn_id: Turn identifier.
        sample_rate: Audio sample rate in Hz (default 16000).
        format: Audio format (default pcm_s16le).
        channels: Number of audio channels (default 1).

    Returns:
        JSON string with tts_start directive.
    """
    return json.dumps({
        "type": "tts_start",
        "session_id": session_id,
        "turn_id": turn_id,
        "sample_rate": sample_rate,
        "format": format,
        "channels": channels,
    })


def build_tts_end(session_id: str, turn_id: int) -> str:
    """Build a tts_end message.

    Args:
        session_id: Session identifier.
        turn_id: Turn identifier.

    Returns:
        JSON string with tts_end directive.
    """
    return json.dumps({
        "type": "tts_end",
        "session_id": session_id,
        "turn_id": turn_id,
    })


def build_error(message: str, session_id: str, turn_id: int) -> str:
    """Build an error message.

    Args:
        message: Error description.
        session_id: Session identifier.
        turn_id: Turn identifier.

    Returns:
        JSON string with error directive.
    """
    return json.dumps({
        "type": "error",
        "message": message,
        "session_id": session_id,
        "turn_id": turn_id,
    })


def build_text(text: str, session_id: str, turn_id: int) -> str:
    """Build a text message with transcribed text.

    Args:
        text: Transcribed text from ASR.
        session_id: Session identifier.
        turn_id: Turn identifier.

    Returns:
        JSON string with text directive.
    """
    return json.dumps({
        "type": "text",
        "text": text,
        "session_id": session_id,
        "turn_id": turn_id,
    })


def build_llm_chunk(text: str, session_id: str, turn_id: int) -> str:
    """Build an LLM chunk message for browser client.

    Args:
        text: Partial LLM output text.
        session_id: Session identifier.
        turn_id: Turn identifier.

    Returns:
        JSON string with llm_chunk directive.
    """
    return json.dumps({
        "type": "llm_chunk",
        "text": text,
        "session_id": session_id,
        "turn_id": turn_id,
    })


def build_tts_audio(data: str, session_id: str, turn_id: int) -> str:
    """Build a TTS audio chunk message for browser client.

    Args:
        data: Base64 encoded PCM audio.
        session_id: Session identifier.
        turn_id: Turn identifier.

    Returns:
        JSON string with tts_audio directive.
    """
    return json.dumps({
        "type": "tts_audio",
        "data": data,
        "session_id": session_id,
        "turn_id": turn_id,
    })


def build_tts_complete(data: str, session_id: str, turn_id: int) -> str:
    """Build a TTS complete message with full audio data.

    Args:
        data: Base64 encoded complete WAV audio.
        session_id: Session identifier.
        turn_id: Turn identifier.

    Returns:
        JSON string with tts_complete directive.
    """
    return json.dumps({
        "type": "tts_complete",
        "data": data,
        "session_id": session_id,
        "turn_id": turn_id,
    })
