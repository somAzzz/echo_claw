"""Global memory with BM25 retrieval for cross-session context."""

import asyncio
import os
from datetime import datetime
from typing import Optional

import aiofiles

from .naming import generate_filename
from .retriever import GlobalRetriever


GLOBAL_DIR = "./memory/global"

# Global async lock for single-process write safety
_global_write_lock = asyncio.Lock()


class GlobalMemory:
    """Manages global (cross-session) memory storage and retrieval."""

    def __init__(
        self,
        global_dir: str = GLOBAL_DIR,
        top_k: int = 3,
        max_chars: int = 2000,
        max_entries: int = 50,
    ):
        self.global_dir = global_dir
        self.top_k = top_k
        self.max_chars = max_chars
        self.max_entries = max_entries
        self._retriever: Optional[GlobalRetriever] = None
        # Single append-only file
        self.global_file = os.path.join(global_dir, "memory.md")
        # Migration flag file
        self.migration_done_file = os.path.join(global_dir, ".migration_done")

    def _ensure_dir(self) -> None:
        os.makedirs(self.global_dir, exist_ok=True)

    async def _rotate_if_needed(self) -> None:
        """Remove oldest entries if total exceeds max_entries."""
        if not os.path.exists(self.global_file):
            return

        async with aiofiles.open(self.global_file, "r", encoding="utf-8") as f:
            content = await f.read()

        # Split on entry separator (front matter starts with "---")
        entries = content.strip().split("\n\n---")
        if len(entries) <= self.max_entries:
            return

        # Keep only the newest max_entries entries
        kept = entries[-self.max_entries:]
        # First entry needs its leading "---" back
        if kept and not kept[0].startswith("---"):
            kept[0] = "---" + kept[0]
        rotated = "\n\n---".join(kept).rstrip() + "\n"

        async with aiofiles.open(self.global_file, "w", encoding="utf-8") as f:
            await f.write(rotated)

        logger = __import__('logging').getLogger(__name__)
        logger.info(
            "Global memory rotated: %d entries removed, %d kept (max=%d)",
            len(entries) - self.max_entries, self.max_entries, self.max_entries
        )

    async def write(
        self,
        session_id: str,
        content: str,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """Append session summary to single memory.md file.

        Format:
            ---
            created: {iso_timestamp}
            session_id: {session_id}
            ---
            {content}

        Args:
            session_id: Session identifier (stored in front matter)
            content: Summary content
            timestamp: Optional datetime (defaults to now)

        Returns:
            Path to the global file (for logging/debugging)
        """
        self._ensure_dir()

        # Migrate old .md files on startup
        await self._migrate_if_needed()

        ts = timestamp or datetime.now()

        front_matter = f"---\ncreated: {ts.isoformat()}\nsession_id: {session_id}\n---\n"
        full_content = front_matter + content + "\n\n"

        async with _global_write_lock:
            async with aiofiles.open(self.global_file, "a", encoding="utf-8") as f:
                await f.write(full_content)

            # Rotate: keep only max_entries newest entries
            await self._rotate_if_needed()

        # Invalidate retriever cache
        self._retriever = None
        return self.global_file

    async def _migrate_if_needed(self) -> bool:
        """Migrate old .md files to single memory.md.

        Returns True if migration happened, False if skipped (already done or nothing to migrate).
        """
        # Check if migration already done
        if os.path.exists(self.migration_done_file):
            return False

        # Ensure directory exists before listing
        if not os.path.isdir(self.global_dir):
            os.makedirs(self.global_dir, exist_ok=True)

        # Find old .md files (excluding special files)
        old_files = [
            f for f in os.listdir(self.global_dir)
            if f.endswith(".md") and not f.startswith(".")
        ]

        if not old_files:
            # Nothing to migrate, mark as done
            async with aiofiles.open(self.migration_done_file, "w") as f:
                await f.write("done")
            return False

        # Read and append each old file in sorted order (oldest first)
        for filename in sorted(old_files):
            filepath = os.path.join(self.global_dir, filename)
            try:
                async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
                    content = await f.read()

                # Append to memory.md
                async with aiofiles.open(self.global_file, "a", encoding="utf-8") as f:
                    await f.write(content + "\n\n")

                # Delete old file after successful migration
                os.unlink(filepath)
            except OSError:
                # Skip files that can't be read, continue with next
                continue

        # Mark migration done
        async with aiofiles.open(self.migration_done_file, "w") as f:
            await f.write("done")

        return True

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

        # Apply soft truncation
        if len(combined) > self.max_chars:
            combined = combined[:self.max_chars]

        return combined

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