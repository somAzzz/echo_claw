"""Memory session management with Turn, Summary, and PendingTurn data structures."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class PendingTurn:
    """Represents an ongoing turn that is still being processed."""
    turn_id: str
    session_id: str
    audio_chunks: list[bytes] = field(default_factory=list)
    user_text: str | None = None
    started_at: datetime = field(default_factory=datetime.now)


@dataclass
class Turn:
    """Represents a completed conversation turn."""
    turn_id: str
    user_text: str
    assistant_text: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Summary:
    """Represents a compressed summary of multiple turns."""
    summary_id: str
    content: str
    created_at: datetime = field(default_factory=datetime.now)
    covered_turn_ids: list[str] = field(default_factory=list)


@dataclass
class Session:
    """Manages a conversation session with turns and summaries."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    turns: list[Turn] = field(default_factory=list)
    summaries: list[Summary] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_turn(self, turn: Turn) -> None:
        """Add a completed turn to the session."""
        self.turns.append(turn)
        self.updated_at = datetime.now()

    def compress(self, keep_recent: int = 2, threshold: int = 5) -> None:
        """Compress older turns into a summary when exceeding threshold.

        Note: This method uses simple concatenation-based compression for
        fast, synchronous operation without external dependencies. For
        LLM-based summarization with proper context compression, use the
        Summarizer class (src/memory/summarizer.py) which provides async
        LLM-powered summarization.

        Args:
            keep_recent: Number of recent turns to keep uncompressed
            threshold: Total number of turns before compression is triggered
        """
        if len(self.turns) <= threshold:
            return

        # Number of turns to compress into summary
        compress_count = len(self.turns) - keep_recent
        if compress_count <= 0:
            return

        # Take older turns for summarization
        turns_to_summarize = self.turns[:-keep_recent] if keep_recent > 0 else self.turns

        # Build summary content from turns
        summary_parts = []
        for turn in turns_to_summarize:
            summary_parts.append(f"User: {turn.user_text}")
            summary_parts.append(f"Assistant: {turn.assistant_text}")
        summary_content = "\n".join(summary_parts)

        # Create summary with references to covered turn IDs
        summary = Summary(
            summary_id=str(uuid.uuid4()),
            content=summary_content,
            created_at=datetime.now(),
            covered_turn_ids=[t.turn_id for t in turns_to_summarize],
        )
        self.summaries.append(summary)

        # Keep only recent turns
        self.turns = self.turns[-keep_recent:] if keep_recent > 0 else []

    def get_recent_context(
        self,
        max_summaries: int = 3,
        max_turns: int = 2,
    ) -> str:
        """Build a context string from recent summaries and turns.

        Args:
            max_summaries: Maximum number of summaries to include
            max_turns: Maximum number of recent turns to include

        Returns:
            A formatted string with recent context
        """
        parts = []

        # Add recent summaries
        recent_summaries = self.summaries[-max_summaries:]
        for summary in recent_summaries:
            parts.append(f"[Summary] {summary.content}")

        # Add recent turns
        recent_turns = self.turns[-max_turns:]
        for turn in recent_turns:
            parts.append(f"User: {turn.user_text}")
            parts.append(f"Assistant: {turn.assistant_text}")

        return "\n".join(parts) if parts else ""


# Legacy Message class for backwards compatibility
@dataclass
class Message:
    """Legacy message class for backwards compatibility."""
    role: str  # "user" or "assistant"
    content: str


# Legacy Session class for backwards compatibility
class LegacySession:
    """Legacy Session class for backwards compatibility."""

    def __init__(self, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.messages: list[Message] = []
        self.created_at = datetime.now()

    @property
    def round_count(self) -> int:
        return sum(1 for m in self.messages if m.role == "user")

    def add_user(self, content: str):
        self.messages.append(Message(role="user", content=content))

    def add_assistant(self, content: str):
        self.messages.append(Message(role="assistant", content=content))

    def clear(self):
        self.messages.clear()
