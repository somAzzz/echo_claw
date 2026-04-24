# src/memory/storage.py
"""Disk persistence for memory sessions.

Saves global_summary to disk after each compression cycle.
Session data persists across restarts.
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles


SUMMARY_DIR = "/app/memory/summaries"


class SessionStorage:
    """Handles saving/loading session summaries to disk."""

    def __init__(self, summary_dir: str = SUMMARY_DIR):
        self.summary_dir = summary_dir

    def _get_filepath(self, session_id: str) -> str:
        """Get filepath for session summary file."""
        return os.path.join(self.summary_dir, f"{session_id}.json")

    async def save(self, session_id: str, global_summary: str) -> None:
        """Save session summary to disk.

        Args:
            session_id: Session identifier
            global_summary: Current summary text
        """
        if not global_summary or global_summary == "暂无早期记忆记录。":
            return

        os.makedirs(self.summary_dir, exist_ok=True)
        filepath = self._get_filepath(session_id)

        data = {
            "session_id": session_id,
            "global_summary": global_summary,
            "saved_at": datetime.now().isoformat(),
        }

        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

    async def load(self, session_id: str) -> Optional[str]:
        """Load session summary from disk.

        Args:
            session_id: Session identifier

        Returns:
            global_summary string if found, None otherwise
        """
        filepath = self._get_filepath(session_id)
        if not os.path.exists(filepath):
            return None

        try:
            async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
                content = await f.read()
            data = json.loads(content)
            return data.get("global_summary")
        except (json.JSONDecodeError, OSError):
            return None

    async def delete(self, session_id: str) -> None:
        """Delete session summary from disk.

        Args:
            session_id: Session identifier
        """
        filepath = self._get_filepath(session_id)
        if os.path.exists(filepath):
            os.remove(filepath)


# Global storage instance
_storage: Optional[SessionStorage] = None


def get_storage(summary_dir: str = SUMMARY_DIR) -> SessionStorage:
    """Get or create global storage instance."""
    global _storage
    if _storage is None:
        _storage = SessionStorage(summary_dir=summary_dir)
    return _storage