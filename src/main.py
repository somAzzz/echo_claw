"""Main WebSocket handler for ESP32 voice assistant.

This module provides the WebSocket server that:
1. Accepts ESP32 connections
2. Handles audio streaming and protocol messages
3. Orchestrates ASR → LLM → TTS pipeline

Protocol Flow:
- ESP32 sends audio_start → transitions to LISTENING
- ESP32 sends binary PCM audio chunks → accumulated in PendingTurn
- ESP32 sends audio_end → triggers pipeline processing
- Hub streams TTS audio chunks → ESP32 plays audio
- ESP32 sends playback_done → returns to IDLE
"""

import asyncio
import json
import logging
import os
import threading
from datetime import datetime
from typing import Optional

import websockets
from websockets.server import WebSocketServerProtocol

from src.config import Config
from src.http_api import app as http_app
from src.browser_ws_handler import handle_browser
from src.memory import get_session, cleanup_session, summarize_async
from src.pipeline.asr import ASRClient
from src.pipeline.llm import LLMClient
from src.pipeline.tts import TTSClient
from src.protocol.ws_protocol import (
    build_error,
    build_state_directive,
    build_tts_end,
    build_tts_start,
    build_text,
    parse_message,
)
from src.state_machine import PendingTurn, State, StateMachine
from src.utils.text_utils import filter_tts_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Delimiters that trigger TTS synthesis
TTS_DELIMITERS = [".", "!", "?", "\n"]
MAX_BUFFER_CHARS = 200

# Debug output directory (set via environment variable)
DEBUG_OUTPUT_DIR = os.environ.get("DEBUG_OUTPUT_DIR")


async def send_json(websocket: WebSocketServerProtocol, data: dict | str) -> None:
    """Send a JSON message to the WebSocket client."""
    if isinstance(data, str):
        await websocket.send(data)
    else:
        await websocket.send(json.dumps(data))


async def send_binary(websocket: WebSocketServerProtocol, data: bytes) -> None:
    """Send binary data to the WebSocket client."""
    await websocket.send(data)


async def run_pipeline(
    websocket: WebSocketServerProtocol,
    pending_turn: PendingTurn,
    asr: ASRClient,
    llm: LLMClient,
    tts: TTSClient,
    voice_session,
    sm: StateMachine,
) -> None:
    """Run the ASR → LLM → TTS pipeline for a pending turn.

    Args:
        websocket: WebSocket connection to ESP32
        pending_turn: The turn with accumulated audio chunks
        asr: ASR client for speech recognition
        llm: LLM client for text generation
        tts: TTS client for audio synthesis
        voice_session: VoiceSession for context management
        sm: State machine for tracking pipeline state
    """
    session_id = pending_turn.session_id
    turn_id = pending_turn.turn_id

    # Step 1: Concatenate audio chunks
    audio_bytes = b"".join(pending_turn.audio_chunks)
    if not audio_bytes:
        logger.warning("No audio data in pending turn")
        return

    # Step 2: ASR recognition
    try:
        asr_result = await asr.recognize(audio_bytes)
        user_text = asr_result.text
    except Exception as e:
        logger.error(f"ASR error: {e}")
        await send_json(websocket, build_error(str(e), session_id, turn_id))
        return

    if not user_text:
        logger.info("No speech recognized")
        await send_json(websocket, build_state_directive(session_id, turn_id, "idle"))
        return

    # Debug output: save ASR result
    logger.info(f"ASR recognized: {user_text}")
    await send_json(websocket, build_text(user_text, session_id, turn_id))

    if DEBUG_OUTPUT_DIR:
        asr_file = os.path.join(DEBUG_OUTPUT_DIR, f"{session_id}_{turn_id}_asr.txt")
        with open(asr_file, "w", encoding="utf-8") as f:
            f.write(user_text)
        logger.info(f"Debug: ASR output saved to {asr_file}")

    # Step 3: Get LLM context using memory system
    messages = voice_session.build_prompt("", user_text)

    text_buffer = ""
    full_llm_response = ""  # Accumulate the complete LLM response
    first_chunk_sent = False
    tts_audio_buffer = bytearray()  # Accumulate TTS audio for WAV output

    try:
        async for token in llm.stream_chat(messages):
            text_buffer += token
            full_llm_response += token

            # Check for delimiter or buffer full
            delimiter_found = any(d in text_buffer for d in TTS_DELIMITERS)
            buffer_full = len(text_buffer) >= MAX_BUFFER_CHARS

            if delimiter_found or buffer_full:
                # Step 5: TTS synthesis (filter emojis first)
                text_to_speak = filter_tts_text(text_buffer)
                if text_to_speak and not first_chunk_sent:
                    # Transition to SPEAKING before sending first TTS chunk
                    sm._handle_tts_ready()
                    await send_json(websocket, build_tts_start(
                        session_id, turn_id,
                        sample_rate=16000,
                        format="pcm_s16le",
                        channels=1
                    ))
                    first_chunk_sent = True

                # Send TTS audio chunks and accumulate (text already filtered above)
                async for audio_chunk in tts.synthesize(text_to_speak):
                    await send_binary(websocket, audio_chunk)
                    tts_audio_buffer.extend(audio_chunk)

                text_buffer = ""

        # Send any remaining text (filter emojis first)
        if text_buffer and first_chunk_sent:
            text_to_speak = filter_tts_text(text_buffer)
            async for audio_chunk in tts.synthesize(text_to_speak):
                await send_binary(websocket, audio_chunk)
                tts_audio_buffer.extend(audio_chunk)

        if first_chunk_sent:
            await send_json(websocket, build_tts_end(session_id, turn_id))

        # Debug output: save TTS audio as WAV using synthesize_to_file
        if DEBUG_OUTPUT_DIR and full_llm_response:
            wav_file = os.path.join(DEBUG_OUTPUT_DIR, f"{session_id}_{turn_id}_tts.wav")
            try:
                await tts.synthesize_to_file(full_llm_response, wav_file)
                logger.info(f"Debug: TTS output saved to {wav_file}")
            except Exception as e:
                logger.error(f"Debug: Failed to save TTS WAV: {e}")

        # Ensure state transitions out of PROCESSING even if no TTS audio was sent
        # This handles the case where LLM output was empty or had no delimiters
        if not first_chunk_sent:
            sm._handle_session_end()  # Transition to IDLE
            await send_json(websocket, build_state_directive(
                session_id, turn_id,
                state="idle"
            ))

        # Debug output: save LLM response
        if DEBUG_OUTPUT_DIR:
            llm_file = os.path.join(DEBUG_OUTPUT_DIR, f"{session_id}_{turn_id}_llm.txt")
            with open(llm_file, "w", encoding="utf-8") as f:
                f.write(full_llm_response)
            logger.info(f"Debug: LLM output saved to {llm_file}")

        # Add turn to memory system and trigger async summary
        voice_session.add_turn("user", user_text)
        voice_session.add_turn("assistant", full_llm_response, voice_session, summarize_async)

    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        await send_json(websocket, build_error(str(e), session_id, turn_id))


async def handle_esp32(websocket: WebSocketServerProtocol) -> None:
    """Handle a single ESP32 client connection.

    Args:
        websocket: WebSocket connection from ESP32
    """
    cfg = Config.get_config()

    # Create per-connection instances
    sm = StateMachine()
    voice_session = None  # Will be created on audio_start

    # Create pipeline clients
    asr = ASRClient(base_url=cfg.asr.base_url)
    llm = LLMClient(
        base_url=cfg.llm.base_url,
        model=cfg.llm.model,
        api_key=getattr(cfg.llm, "api_key", None),
    )
    tts = TTSClient(
        voice=cfg.tts.voice,
        rate=cfg.tts.rate,
        pitch=cfg.tts.pitch,
        volume=cfg.tts.volume,
    )

    logger.info(f"ESP32 connected: {websocket.remote_address}")

    # Send initial idle state
    if sm.current_turn:
        session_id = sm.current_turn.session_id
        turn_id = sm.current_turn.turn_id
    else:
        session_id = ""
        turn_id = 0

    try:
        async for message in websocket:
            # Parse message - returns dict for JSON, None for binary
            parsed = parse_message(message)

            if parsed is None:
                # Binary audio data
                if sm.state == State.LISTENING and sm.current_turn:
                    sm.current_turn.audio_chunks.append(message)
                # In other states, binary audio is dropped
                continue

            # JSON message from ESP32
            msg_type = parsed.get("type")
            logger.debug(f"Received from ESP32: {parsed}")

            if msg_type == "audio_start":
                session_id = parsed.get("session_id", "")
                turn_id = parsed.get("turn_id", 0)
                # Create or get memory session for this session_id
                voice_session = get_session(session_id)

                sm.handle_message(parsed)
                await send_json(websocket, build_state_directive(
                    session_id, turn_id,
                    state="listening"
                ))

            elif msg_type == "audio_end":
                session_id = parsed.get("session_id", session_id)

                sm.handle_message(parsed)

                if sm.state == State.PROCESSING and sm.current_turn:
                    # Run the ASR → LLM → TTS pipeline
                    await run_pipeline(
                        websocket,
                        sm.current_turn,
                        asr,
                        llm,
                        tts,
                        voice_session,
                        sm,
                    )

                    # After pipeline, wait for tts_ready from ESP32
                    # The state machine should transition to SPEAKING on tts_ready

            elif msg_type == "tts_ready":
                sm.handle_message(parsed)
                # ESP32 is ready to receive TTS audio
                logger.info("ESP32 ready for TTS audio")

            elif msg_type == "playback_done":
                sm.handle_message(parsed)
                await send_json(websocket, build_state_directive(
                    session_id, turn_id,
                    state="idle"
                ))

            elif msg_type == "session_end":
                sm.handle_message(parsed)
                if voice_session:
                    cleanup_session(voice_session.session_id)
                    voice_session = None
                session_id = ""
                turn_id = 0
                await send_json(websocket, build_state_directive(
                    session_id, turn_id,
                    state="idle"
                ))

            else:
                logger.debug(f"Ignored message type: {msg_type}")

    except websockets.exceptions.ConnectionClosed:
        logger.info("ESP32 disconnected")
    except Exception as e:
        logger.error(f"WebSocket handler error: {e}")
        if sm.current_turn:
            await send_json(websocket, build_error(
                str(e),
                sm.current_turn.session_id,
                sm.current_turn.turn_id
            ))


async def main() -> None:
    """Start the WebSocket server and HTTP API."""
    cfg = Config.get_config()

    # Start HTTP API in background thread
    def run_http():
        import uvicorn
        uvicorn.run(http_app, host="0.0.0.0", port=cfg.server.http_port, log_level="info")

    http_thread = threading.Thread(target=run_http, daemon=True)
    http_thread.start()
    logger.info(f"Starting HTTP API server on port {cfg.server.http_port}")

    # Start WebSocket server for ESP32 on port 8765
    esp32_server = websockets.serve(handle_esp32, cfg.server.host, cfg.server.port, ping_interval=None)
    # Start WebSocket server for browser on port 8767
    browser_server = websockets.serve(handle_browser, cfg.server.host, cfg.server.http_port + 1, ping_interval=None)

    logger.info(f"Starting WebSocket servers - ESP32 on {cfg.server.port}, Browser on {cfg.server.http_port + 1}")

    # Run both servers concurrently
    async with esp32_server, browser_server:
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
