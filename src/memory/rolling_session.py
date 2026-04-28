# src/memory/rolling_session.py
"""Rolling Summary Memory System for Voice Assistant."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ..pipeline.llm import LLMClient

from .naming import generate_session_id
from .storage import get_storage
from .global_memory import get_global_memory

logger = logging.getLogger(__name__)


@dataclass
class Turn:
    """Single conversation turn."""
    role: str           # "user" or "assistant"
    content: str        # text content
    timestamp: float    # Unix timestamp


@dataclass
class VoiceSession:
    """Session with rolling summary memory management.

    Maintains:
    - global_summary: compressed representation of older turns
    - recent_turns: sliding window of recent conversation (max N)
    - is_summarizing: lock to prevent concurrent summarization
    """
    session_id: str
    global_summary: str = "暂无早期记忆记录。"
    recent_turns: List[Turn] = field(default_factory=list)
    is_summarizing: bool = False

    # Configuration (set via __post_init__ or config)
    window_size: int = 10          # N - max turns in short-term memory
    step_size: int = 5             # M - turns to compress per summary
    token_threshold: int = 8000    # chars, trigger summary if exceeded
    max_summary_length: int = 300  # max tokens for global_summary

    def estimate_tokens(self) -> int:
        """Simple token estimator: chars // 2 for Chinese.

        Conservative estimate assuming ~2 chars per token.
        """
        total_chars = len(self.global_summary)
        for turn in self.recent_turns:
            total_chars += len(turn.content)
        return total_chars // 2

    def build_prompt(self, base_identity: str, current_input: str, global_context: str = "", soul_rules: str = "") -> List[dict]:
        """Build messages for LLM with memory context.

        Prompt structure (attention-layered, top = highest priority):
        [0] system: base_identity + soul_rules (always present)
        [1] global_context (BM25 retrieved, cross-session facts)
        [2] global_summary (intra-session rolling summary)
        [3] recent turns (short-term window)
        [4] current input (user turn)

        Args:
            base_identity: Static identity prompt (from prompts/default.txt)
            current_input: Current user input
            global_context: Optional cross-session global memory (BM25 retrieved)
            soul_rules: SOUL behavioral rules from SOUL.md
        """
        messages = []

        # Layer [0]: base identity + SOUL behavioral rules
        system_content = base_identity
        if soul_rules:
            system_content += soul_rules
        messages.append({
            "role": "system",
            "content": system_content
        })

        # Layer [1]: global context (cross-session facts, only when trigger fired)
        if global_context:
            messages.append({
                "role": "system",
                "content": "[全局记忆]\n以下是你之前记住的用户信息，请直接基于这些信息回答用户的问题：\n" + global_context
            })

        # Layer [2]: session-level summary (intra-session rolling compression)
        elif self.global_summary and self.global_summary != "暂无早期记忆记录。":
            messages.append({
                "role": "system",
                "content": f"[记忆上下文]\n{self.global_summary}"
            })

        # Layer [3]: recent turns (short-term window)
        for turn in self.recent_turns[-self.window_size:]:
            messages.append({"role": turn.role, "content": turn.content})

        # Layer [4]: current user input
        messages.append({"role": "user", "content": current_input})
        return messages

    def add_turn(self, role: str, content: str,
                 llm_client=None,
                 summarize_callback: Optional[Callable] = None) -> None:
        """Add a turn and trigger async summary if needed.

        Args:
            role: "user" or "assistant"
            content: text content
            llm_client: LLM client for summarization (optional)
            summarize_callback: async function to call for summarization
        """
        self.recent_turns.append(Turn(role=role, content=content, timestamp=time.time()))

        # Check trigger conditions (async trigger, non-blocking)
        if self._should_summarize() and llm_client and summarize_callback:
            task = asyncio.create_task(
                summarize_callback(self, llm_client)
            )
            task.add_done_callback(
                lambda t: logger.error(f"Summary task failed: {t.exception()}", exc_info=t.exception())
                if t.exception() else None
            )

    def _should_summarize(self) -> bool:
        """Check if summary should be triggered (dual-gate)."""
        if self.is_summarizing:
            return False
        if len(self.recent_turns) > self.window_size:
            return True
        if self.estimate_tokens() > self.token_threshold:
            return True
        return False

    async def force_summarize(self, llm_client) -> None:
        """Force compress all remaining turns at session end.

        Called when session disconnects to ensure no dialogue is lost.
        Uses merge_all=True to compress ALL remaining turns.
        """
        if not self.recent_turns:
            return

        await summarize_async(
            session=self,
            llm_client=llm_client,
            merge_all=True,
        )


async def summarize_async(
    session: VoiceSession,
    llm_client: "LLMClient",
    max_summary_length: int = 300,
    merge_all: bool = False,
) -> None:
    """Background summarization task.

    Extracts earliest M turns, calls LLM to fuse with global_summary,
    then atomically replaces global_summary and removes the M turns.

    Args:
        session: VoiceSession to summarize
        llm_client: LLM client for summarization
        max_summary_length: Max characters for summary
        merge_all: If True, compress ALL remaining turns instead of just M
    """
    if session.is_summarizing:
        return

    session.is_summarizing = True
    try:
        M = session.step_size
        if merge_all:
            M = len(session.recent_turns)  # Compress all remaining turns

        # Extract earliest M turns (snapshot, not reference)
        turns_to_merge = session.recent_turns[:M]
        if not turns_to_merge:
            return

        # Format history for LLM
        history_text = "\n".join([f"{t.role}: {t.content}" for t in turns_to_merge])

        # Build summary prompt
        prompt = get_summary_prompt(session.global_summary, history_text)

        # Generate new summary via LLM (non-streaming complete call)
        from .prompts import SUMMARY_FUSION_PROMPT
        new_summary = None
        async for chunk in llm_client.stream_chat(
            [{"role": "user", "content": prompt}],
            system="你是一个专门负责管理对话记忆的 AI 助手。"
        ):
            if new_summary is None:
                new_summary = chunk
            else:
                new_summary += chunk

        if new_summary:
            # Truncate if too long (roughly)
            if len(new_summary) > max_summary_length * 2:
                new_summary = new_summary[:max_summary_length * 2]

            # Atomic replacement
            session.global_summary = new_summary
            session.recent_turns = session.recent_turns[M:]  # Remove merged turns
            logger.info(f"Summary updated for session {session.session_id}, new length: {len(new_summary)}")

            # Persist to disk
            storage = get_storage()
            await storage.save(session.session_id, new_summary)

    except Exception as e:
        logger.error(f"Summary failed for session {session.session_id}: {e}")
    finally:
        session.is_summarizing = False


def get_summary_prompt(current_summary: str, new_history: str) -> str:
    """Build the summary fusion prompt.

    Args:
        current_summary: Existing global_summary
        new_history: Formatted string of turns to merge

    Returns:
        Formatted prompt string
    """
    from .prompts import SUMMARY_FUSION_PROMPT
    return SUMMARY_FUSION_PROMPT.format(
        current_summary=current_summary,
        new_history=new_history
    )


# Global session registry
_sessions: Dict[str, VoiceSession] = {}
MAX_SESSIONS = 100


def _evict_oldest_sessions() -> None:
    """Remove oldest sessions if registry exceeds MAX_SESSIONS."""
    if len(_sessions) <= MAX_SESSIONS:
        return
    # Sort by most recent turn timestamp, keep newest MAX_SESSIONS
    sorted_sessions = sorted(
        _sessions.items(),
        key=lambda item: max((t.timestamp for t in item[1].recent_turns), default=0),
        reverse=True,
    )
    for sid, _ in sorted_sessions[MAX_SESSIONS:]:
        del _sessions[sid]
        logger.info("Evicted idle session: %s", sid)


def get_session(session_id: Optional[str], **kwargs) -> VoiceSession:
    """Get or create a session by ID (sync version for main.py).

    Note: Does not load from disk. Use get_session_async for disk persistence.
    If session_id is None or empty, generates a new one using NamingService.
    """
    if not session_id:
        session_id = generate_session_id()
    if session_id not in _sessions:
        _evict_oldest_sessions()
        _sessions[session_id] = VoiceSession(session_id=session_id, **kwargs)
    return _sessions[session_id]


async def get_session_async(session_id: Optional[str], **kwargs) -> VoiceSession:
    """Get or create a session by ID with disk persistence.

    Loads persisted global_summary from disk if available.
    If session_id is None or empty, generates a new one using NamingService.
    """
    if not session_id:
        session_id = generate_session_id()
    if session_id not in _sessions:
        # Try to load persisted summary from disk
        storage = get_storage()
        persisted_summary = await storage.load(session_id)

        session_kwargs = dict(kwargs)
        if persisted_summary:
            session_kwargs.setdefault("global_summary", persisted_summary)

        _sessions[session_id] = VoiceSession(session_id=session_id, **session_kwargs)
        if persisted_summary:
            logger.info(f"Loaded persisted summary for session {session_id}")

    return _sessions[session_id]


def cleanup_session(session_id: str) -> None:
    """Remove session from registry (sync version)."""
    if session_id in _sessions:
        del _sessions[session_id]


async def cleanup_session_async(session_id: str) -> None:
    """Remove session from registry and delete from disk."""
    if session_id in _sessions:
        del _sessions[session_id]
    storage = get_storage()
    await storage.delete(session_id)


async def finalize_session(session_id: str) -> dict:
    """Finalize session: write to global memory and cleanup.

    Returns dict with:
        - success: bool
        - summary_length: int (chars written)
        - turns_count: int
    """
    if session_id not in _sessions:
        logger.warning(f"finalize_session: session {session_id} not found")
        return {"success": False, "error": "session not found", "summary_length": 0, "turns_count": 0}

    voice_session = _sessions[session_id]

    # Build summary from recent turns if no summarization happened
    summary_to_write = voice_session.global_summary
    if not summary_to_write or summary_to_write == "暂无早期记忆记录。":
        if voice_session.recent_turns:
            summary_to_write = "\n".join([
                f"{t.role}: {t.content}" for t in voice_session.recent_turns[-10:]
            ])
        else:
            summary_to_write = None

    # Write to global memory if we have content
    result = {"success": False, "summary_length": 0, "turns_count": len(voice_session.recent_turns)}
    if summary_to_write:
        global_mem = get_global_memory()
        await global_mem.write(voice_session.session_id, summary_to_write)
        logger.info(f"Session {voice_session.session_id} written to global memory ({len(summary_to_write)} chars)")
        result["success"] = True
        result["summary_length"] = len(summary_to_write)

    # Remove from registry
    del _sessions[session_id]
    return result