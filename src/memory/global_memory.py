"""Global memory with BM25 retrieval for cross-session context."""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles

from .retriever import GlobalRetriever


GLOBAL_DIR = "./memory/global"


class GlobalMemory:
    """Manages global (cross-session) memory storage and retrieval."""

    def __init__(
        self,
        global_dir: str = GLOBAL_DIR,
        top_k: int = 3,
        max_chars: int = 2000,
    ):
        self.global_dir = global_dir
        self.top_k = top_k
        self.max_chars = max_chars
        self._retriever: Optional[GlobalRetriever] = None

    def _ensure_dir(self) -> None:
        os.makedirs(self.global_dir, exist_ok=True)

    async def write(
        self,
        session_id: str,
        content: str,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """Write a session summary to global memory.

        Filename: session_YYYYMMDD_HHMMSS_<short_id>.md
        Front-matter includes created timestamp.

        Args:
            session_id: Session identifier
            content: Summary content
            timestamp: Optional datetime (defaults to now)

        Returns:
            Path to written file
        """
        self._ensure_dir()
        ts = timestamp or datetime.now()
        ts_str = ts.strftime("%Y%m%d_%H%M%S")
        short_id = session_id[:8]
        filename = f"session_{ts_str}_{short_id}.md"
        filepath = os.path.join(self.global_dir, filename)

        front_matter = f"---\ncreated: {ts.isoformat()}\nsession_id: {session_id}\n---\n"
        full_content = front_matter + content

        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(full_content)

        # Invalidate retriever cache
        self._retriever = None
        return filepath

    def get_retriever(self) -> GlobalRetriever:
        """Get or create the BM25 retriever (lazy init)."""
        if self._retriever is None:
            self._retriever = GlobalRetriever(self.global_dir)
        return self._retriever

    async def retrieve(self, query: str) -> str:
        """Retrieve relevant global memory content for a query.

        Args:
            query: User input text (may contain trigger words)

        Returns:
            Relevant memory content, or empty string if no match
        """
        retriever = self.get_retriever()

        matched = retriever.retrieve(query, top_k=self.top_k)
        if not matched:
            return ""

        # Merge matched content
        combined = "\n\n".join(matched)

        # Soft truncation: if over max_chars, caller should do Map-Reduce
        if len(combined) <= self.max_chars:
            return combined

        return combined  # Let caller decide if truncation needed

    def has_trigger(self, text: str) -> bool:
        """Check if text contains a global memory trigger phrase."""
        retriever = self.get_retriever()
        return retriever.has_trigger(text)


# Global singleton
_global_memory: Optional[GlobalMemory] = None


def get_global_memory(
    global_dir: str = GLOBAL_DIR,
    top_k: int = 3,
    max_chars: int = 2000,
) -> GlobalMemory:
    """Get or create global memory singleton."""
    global _global_memory
    if _global_memory is None:
        _global_memory = GlobalMemory(
            global_dir=global_dir,
            top_k=top_k,
            max_chars=max_chars,
        )
    return _global_memory
