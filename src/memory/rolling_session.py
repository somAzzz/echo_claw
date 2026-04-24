# src/memory/rolling_session.py
"""Rolling Summary Memory System for Voice Assistant."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ..pipeline.llm import LLMClient

from .storage import get_storage

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

    def build_prompt(self, system_prompt: str, current_input: str, global_context: str = "") -> List[dict]:
        """Build messages for LLM with memory context.

        Prompt structure:
        [System Prompt] + [global_context] + [global_summary] + [recent_turns] + [current_input]

        Args:
            system_prompt: Base system prompt
            current_input: Current user input
            global_context: Optional cross-session global memory (BM25 retrieved)
        """
        messages = []

        # Add memory context if exists
        if global_context:
            messages.append({
                "role": "system",
                "content": f"[全局记忆]\n{global_context}\n\n【重要】当全局记忆中的信息与当前对话冲突时，以时间更近的记录为准。"
            })
        elif self.global_summary and self.global_summary != "暂无早期记忆记录。":
            messages.append({
                "role": "system",
                "content": f"[记忆上下文]\n{self.global_summary}"
            })

        # Add recent turns (up to window_size)
        for turn in self.recent_turns[-self.window_size:]:
            messages.append({"role": turn.role, "content": turn.content})

        # Add current user input
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
            asyncio.create_task(
                summarize_callback(self, llm_client)
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


async def summarize_async(
    session: VoiceSession,
    llm_client: "LLMClient",
    max_summary_length: int = 300
) -> None:
    """Background summarization task.

    Extracts earliest M turns, calls LLM to fuse with global_summary,
    then atomically replaces global_summary and removes the M turns.
    """
    if session.is_summarizing:
        return

    session.is_summarizing = True
    try:
        M = session.step_size

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
            session.recent_turns = session.recent_turns[M:]  # Remove only first M
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


def get_session(session_id: str, **kwargs) -> VoiceSession:
    """Get or create a session by ID (sync version for main.py).

    Note: Does not load from disk. Use get_session_async for disk persistence.
    """
    if session_id not in _sessions:
        _sessions[session_id] = VoiceSession(session_id=session_id, **kwargs)
    return _sessions[session_id]


async def get_session_async(session_id: str, **kwargs) -> VoiceSession:
    """Get or create a session by ID with disk persistence.

    Loads persisted global_summary from disk if available.
    """
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