# src/memory/__init__.py
"""Memory management module for voice assistant.

Architecture:
    - Short-term: VoiceSession.recent_turns (sliding window, N turns)
    - Medium-term: VoiceSession.global_summary (rolling compression)
    - Persistence: SessionStorage saves summaries to disk as JSON

Implementation:
    - VoiceSession: rolling summary with dual-track architecture
    - Track 1: Main pipeline (synchronous, for LLM context)
    - Track 2: Background summarization (async, via asyncio.create_task)
"""

from .rolling_session import (
    Turn,
    VoiceSession,
    get_session,
    get_session_async,
    cleanup_session,
    cleanup_session_async,
    finalize_session,
    summarize_async,
    get_summary_prompt,
)

from .storage import SessionStorage, get_storage

from .global_memory import GlobalMemory, get_global_memory, GLOBAL_DIR

from .retriever import GlobalRetriever

__all__ = [
    "Turn",
    "VoiceSession",
    "get_session",
    "get_session_async",
    "cleanup_session",
    "cleanup_session_async",
    "finalize_session",
    "summarize_async",
    "get_summary_prompt",
    "SessionStorage",
    "get_storage",
    "GlobalMemory",
    "get_global_memory",
    "GLOBAL_DIR",
    "GlobalRetriever",
]

from .soul import get_soul_prompt, get_cached_soul_prompt, clear_cache
