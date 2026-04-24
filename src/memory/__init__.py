# src/memory/__init__.py
"""Memory management module for voice assistant.

Architecture:
    - Short-term: VoiceSession.recent_turns (sliding window, N turns)
    - Medium-term: VoiceSession.global_summary (rolling compression)

Implementation:
    - VoiceSession: rolling summary with dual-track architecture
    - Track 1: Main pipeline (synchronous, for LLM context)
    - Track 2: Background summarization (async, via asyncio.create_task)
"""

from .rolling_session import (
    Turn,
    VoiceSession,
    get_session,
    cleanup_session,
    summarize_async,
    get_summary_prompt,
)

__all__ = [
    "Turn",
    "VoiceSession",
    "get_session",
    "cleanup_session",
    "summarize_async",
    "get_summary_prompt",
]
