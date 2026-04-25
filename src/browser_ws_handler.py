"""Browser WebSocket handler for voice pipeline."""

import asyncio
import base64
import json
import logging

import websockets
from websockets import ServerConnection

from src.config import Config
from src.pipeline.asr import ASRClient
from src.pipeline.llm import LLMClient
from src.pipeline.tts import TTSClient
from src.protocol.ws_protocol import (
    build_error,
    build_llm_chunk,
    build_state_directive,
    build_tts_complete,
    build_text,
)
from src.memory import get_session, get_global_memory
from src.state_machine import StateMachine
from src.utils.text_utils import filter_tts_text

logger = logging.getLogger(__name__)

# Global memory instance for cross-session context
_global_memory = None

def _get_global_memory():
    global _global_memory
    if _global_memory is None:
        _global_memory = get_global_memory()
    return _global_memory


async def handle_browser(websocket: ServerConnection) -> None:
    """Handle browser WebSocket connection.

    Args:
        websocket: WebSocket connection from browser
    """
    cfg = Config.get_config()

    sm = StateMachine()
    asr = ASRClient(base_url=cfg.asr.base_url)
    llm = LLMClient(
        base_url=cfg.llm.base_url,
        model=cfg.llm.model,
        api_key=getattr(cfg.llm, "api_key", None),
        max_tokens=cfg.llm.max_tokens,
    )
    tts = TTSClient(
        voice=cfg.tts.voice,
        rate=cfg.tts.rate,
        pitch=cfg.tts.pitch,
        volume=cfg.tts.volume,
    )

    sm = StateMachine()
    asr = ASRClient(base_url=cfg.asr.base_url)
    llm = LLMClient(
        base_url=cfg.llm.base_url,
        model=cfg.llm.model,
        api_key=getattr(cfg.llm, "api_key", None),
        max_tokens=cfg.llm.max_tokens,
    )
    tts = TTSClient(
        voice=cfg.tts.voice,
        rate=cfg.tts.rate,
        pitch=cfg.tts.pitch,
        volume=cfg.tts.volume,
    )

    session_id = ""
    turn_id = 0
    audio_chunks = []
    voice_session = None  # Per-connection session for memory tracking

    async def _finalize_session():
        """Write session to global memory and cleanup."""
        nonlocal voice_session, llm
        if voice_session:
            # Force summarize remaining turns before cleanup
            if voice_session.recent_turns:
                await voice_session.force_summarize(llm)

            # Write to global memory if summary exists
            if voice_session.global_summary and voice_session.global_summary != "暂无早期记忆记录。":
                global_mem = _get_global_memory()
                await global_mem.write(voice_session.session_id, voice_session.global_summary)
                logger.info(f"Session {voice_session.session_id} summary written to global memory")

            cleanup_session(voice_session.session_id)
            voice_session = None

    try:
        async for message in websocket:
            if isinstance(message, str):
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "audio_start":
                    session_id = data.get("session_id", "browser")
                    turn_id = data.get("turn_id", 1)
                    sm.handle_message({"type": "audio_start", "session_id": session_id, "turn_id": turn_id})
                    audio_chunks = []
                    await websocket.send(build_state_directive(session_id, turn_id, "listening"))

                elif msg_type == "audio_chunk":
                    # Decode base64 audio
                    b64_data = data.get("data", "")
                    if b64_data:
                        audio_bytes = base64.b64decode(b64_data)
                        audio_chunks.append(audio_bytes)

                elif msg_type == "audio_end":
                    sm.handle_message({"type": "audio_end"})
                    # Create/get voice session for this browser connection
                    if not voice_session:
                        voice_session = get_session(session_id or f"browser-{id(websocket)}")
                    await run_browser_pipeline(websocket, sm, asr, llm, tts, session_id, turn_id, audio_chunks, voice_session)

                elif msg_type == "text_input":
                    # Direct text input (bypasses ASR)
                    user_text = data.get("text", "").strip()
                    prompt = data.get("prompt", "")
                    if user_text:
                        logger.info(f"text_input received: user_text='{user_text}', prompt='{prompt[:50] if prompt else 'empty'}...'")
                    if not voice_session:
                        voice_session = get_session(session_id or f"browser-{id(websocket)}")
                    await run_text_pipeline(websocket, llm, tts, session_id, turn_id, user_text, prompt, voice_session)

                elif msg_type == "cancel":
                    sm.handle_cancel()
                    await websocket.send(build_state_directive(session_id, turn_id, "idle"))

            else:
                logger.warning("Received binary data on browser WebSocket - ignored")

    except websockets.exceptions.ConnectionClosed:
        await _finalize_session()
        logger.info("Browser disconnected")


async def run_browser_pipeline(
    websocket,
    sm: StateMachine,
    asr: ASRClient,
    llm: LLMClient,
    tts: TTSClient,
    session_id: str,
    turn_id: int,
    audio_chunks: list,
    voice_session = None,
) -> None:
    """Run ASR → LLM → TTS pipeline for browser."""
    if not audio_chunks:
        await websocket.send(build_state_directive(session_id, turn_id, "idle"))
        return

    audio_bytes = b"".join(audio_chunks)

    # ASR
    try:
        asr_result = await asr.recognize(audio_bytes)
        user_text = asr_result.text
    except Exception as e:
        logger.error(f"ASR error: {e}")
        await websocket.send(build_error(str(e), session_id, turn_id))
        return

    if not user_text:
        await websocket.send(build_state_directive(session_id, turn_id, "idle"))
        return

    await websocket.send(build_text(user_text, session_id, turn_id))

    # Run LLM → TTS
    await run_llm_to_tts(websocket, llm, tts, session_id, turn_id, user_text, voice_session=voice_session)


async def run_text_pipeline(
    websocket,
    llm: LLMClient,
    tts: TTSClient,
    session_id: str,
    turn_id: int,
    user_text: str,
    prompt: str = "",
    voice_session = None,
) -> None:
    """Run LLM → TTS pipeline for direct text input (bypasses ASR)."""
    logger.info(f"run_text_pipeline called: user_text='{user_text}', session_id={session_id}, turn_id={turn_id}")
    await websocket.send(build_text(user_text, session_id, turn_id))
    await run_llm_to_tts(websocket, llm, tts, session_id, turn_id, user_text, prompt, voice_session)


async def run_llm_to_tts(
    websocket,
    llm: LLMClient,
    tts: TTSClient,
    session_id: str,
    turn_id: int,
    user_text: str,
    prompt: str = "",
    voice_session = None,
) -> None:
    """Run LLM streaming followed by TTS synthesis."""
    logger.info(f"run_llm_to_tts called: user_text='{user_text}', prompt='{prompt[:50] if prompt else 'empty'}...'")

    # Resolve or create voice session
    if voice_session is None:
        voice_session = get_session(session_id)

    # Check for global context trigger
    global_context = ""
    global_mem = _get_global_memory()
    if global_mem.has_trigger(user_text):
        global_context = await global_mem.retrieve(user_text)
        logger.info(f"Global context retrieved: {len(global_context)} chars")

    # Build prompt: identity + SOUL rules + global context
    from src.memory.soul import get_soul_prompt
    identity = prompt if prompt else ""
    soul_rules = get_soul_prompt()
    built_messages = voice_session.build_prompt(
        base_identity=identity,
        current_input=user_text,
        global_context=global_context,
        soul_rules=soul_rules,
    )

    # Add user turn to session
    voice_session.add_turn(role="user", content=user_text)

    # LLM streaming with built prompt
    text_buffer = ""
    full_response = ""

    try:
        async for token in llm.stream_chat(built_messages, system=None):
            text_buffer += token
            full_response += token

            # Send llm_chunk periodically
            if len(text_buffer) >= 20:
                await websocket.send(build_llm_chunk(text_buffer, session_id, turn_id))
                text_buffer = ""

        if text_buffer:
            await websocket.send(build_llm_chunk(text_buffer, session_id, turn_id))

    except Exception as e:
        logger.error(f"LLM error: {type(e).__name__}: {e}", exc_info=True)
        await websocket.send(build_error(str(e), session_id, turn_id))
        return

    # Add assistant turn to session
    if full_response:
        voice_session.add_turn(role="assistant", content=full_response)
        logger.info(f"Session {session_id}: {len(voice_session.recent_turns)} recent turns, global_summary length: {len(voice_session.global_summary)}")

    # TTS synthesis
    logger.info(f"LLM complete, full_response length: {len(full_response)}, content: {full_response[:100] if full_response else 'EMPTY'}")
    filtered_text = filter_tts_text(full_response)
    logger.info(f"After filter_tts_text, filtered length: {len(filtered_text)}, content: {filtered_text[:100] if filtered_text else 'EMPTY'}")
    if not filtered_text.strip():
        logger.warning("Filtered text is empty, sending idle state")
        await websocket.send(build_state_directive(session_id, turn_id, "idle"))
        return

    logger.info(f"TTS synthesis starting for text length: {len(filtered_text)}")
    try:
        # Collect all audio chunks first
        audio_parts = []
        async for audio_chunk in tts.synthesize(filtered_text):
            audio_parts.append(audio_chunk)

        logger.info(f"TTS collected {len(audio_parts)} audio parts, total size: {sum(len(p) for p in audio_parts)} bytes")
        if audio_parts:
            full_audio = b"".join(audio_parts)
            b64_audio = base64.b64encode(full_audio).decode()
            logger.info(f"TTS sending tts_complete with b64 length: {len(b64_audio)}")
            await websocket.send(build_tts_complete(b64_audio, session_id, turn_id))
        else:
            logger.info("TTS audio_parts was empty, sending idle state")
            await websocket.send(build_state_directive(session_id, turn_id, "idle"))

    except Exception as e:
        logger.error(f"TTS error: {e}")
        await websocket.send(build_error(str(e), session_id, turn_id))
