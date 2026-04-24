"""Summarizer for generating and saving conversation summaries to disk."""
import os
import uuid
from datetime import datetime

import aiofiles

SUMMARY_TEMPLATE = """请将以下对话精简为3句话的摘要，保留关键信息（人名、偏好、承诺的事项）：
---
{conversation}
---"""


class Summarizer:
    """Handles summarization of conversation turns and saving summaries to disk."""

    def __init__(self, llm_client, summary_dir: str = "/app/memory/summaries"):
        self.llm_client = llm_client
        self.summary_dir = summary_dir

    def _build_summary_prompt(self, turns: list) -> str:
        """Build a summary prompt from a list of turns.

        Args:
            turns: List of Turn objects

        Returns:
            A formatted prompt string for summarization
        """
        conversation_lines = []
        for turn in turns:
            conversation_lines.append(f"用户：{turn.user_text}")
            conversation_lines.append(f"助手：{turn.assistant_text}")
        conversation = "\n".join(conversation_lines)
        return SUMMARY_TEMPLATE.format(conversation=conversation)

    @staticmethod
    def format_summary_md(date: str, content: str, turn_ids: list[str] = None) -> str:
        """Format summary content as markdown.

        Args:
            date: Date string for the summary
            content: Summary content text
            turn_ids: Optional list of turn IDs covered by this summary

        Returns:
            Markdown formatted string
        """
        turn_ids_str = ", ".join(turn_ids) if turn_ids else ""
        turn_ids_line = f"\n涵盖Turn IDs: {turn_ids_str}" if turn_ids else ""
        return f"""=== {date} 会话摘要 ===
{content}
==================={turn_ids_line}"""

    async def save_summary(self, session_id: str, content: str, turn_ids: list[str]) -> None:
        """Save a summary to a .md file.

        Args:
            session_id: Session identifier to use as filename
            content: Summary content text
            turn_ids: List of turn IDs covered by this summary
        """
        os.makedirs(self.summary_dir, exist_ok=True)
        filepath = os.path.join(self.summary_dir, f"{session_id}.md")
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md_content = self.format_summary_md(date_str, content, turn_ids)
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(md_content)

    async def generate_summary(self, turns: list) -> str:
        """Generate a summary from a list of turns.

        This is a placeholder implementation that concatenates turn content.
        A real implementation would call an LLM to generate a proper summary.

        Args:
            turns: List of Turn objects to summarize

        Returns:
            Summary content string
        """
        if not turns:
            return ""

        # Placeholder: simple concatenation of turns
        summary_parts = []
        for turn in turns:
            summary_parts.append(f"用户：{turn.user_text}")
            summary_parts.append(f"助手：{turn.assistant_text}")
        return "\n".join(summary_parts)
