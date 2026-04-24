"""Tests for Summarizer memory management."""
import os
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.memory.summarizer import Summarizer, SUMMARY_TEMPLATE
from src.memory.session import Session, Turn


class TestSummarizerBuildPrompt:
    def test_build_summary_prompt(self):
        """Test building a summary prompt from turns."""
        session = Session(session_id="s1")
        session.add_turn(Turn(
            turn_id="t1",
            user_text="今天天气怎么样？",
            assistant_text="今天是晴天，气温25度。",
            timestamp=datetime.now(),
        ))
        summarizer = Summarizer(llm_client=None)
        prompt = summarizer._build_summary_prompt(session.turns)
        assert "今天天气怎么样？" in prompt
        assert "今天是晴天，气温25度。" in prompt


class TestSummarizerFormatMd:
    def test_format_summary_md(self):
        """Test formatting summary as markdown."""
        md = Summarizer.format_summary_md("2026-04-21", "- 用户询问天气，已告知晴天")
        assert "2026-04-21" in md
        assert "用户询问天气" in md
        assert "===================" in md


class TestSummarizerSaveSummary:
    @pytest.mark.asyncio
    async def test_save_summary_creates_file(self):
        """Test saving a summary creates a .md file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            summarizer = Summarizer(llm_client=None, summary_dir=tmpdir)
            await summarizer.save_summary("sess1", "User discussed weather", ["t1", "t2"])

            filepath = os.path.join(tmpdir, "sess1.md")
            assert os.path.exists(filepath)

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            assert "User discussed weather" in content
            assert "t1" in content
            assert "t2" in content

    @pytest.mark.asyncio
    async def test_save_summary_creates_directory(self):
        """Test saving a summary creates the directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            summary_dir = os.path.join(tmpdir, "nested", "summaries")
            summarizer = Summarizer(llm_client=None, summary_dir=summary_dir)
            await summarizer.save_summary("sess1", "Test summary", ["t1"])

            assert os.path.exists(summary_dir)

    @pytest.mark.asyncio
    async def test_save_summary_multiple_times(self):
        """Test saving multiple summaries to different files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            summarizer = Summarizer(llm_client=None, summary_dir=tmpdir)
            await summarizer.save_summary("sess1", "Summary 1", ["t1"])
            await summarizer.save_summary("sess2", "Summary 2", ["t2"])

            filepath1 = os.path.join(tmpdir, "sess1.md")
            filepath2 = os.path.join(tmpdir, "sess2.md")
            assert os.path.exists(filepath1)
            assert os.path.exists(filepath2)


class TestSummarizerGenerateSummary:
    @pytest.mark.asyncio
    async def test_generate_summary_returns_content(self):
        """Test generate_summary returns summary content (placeholder)."""
        summarizer = Summarizer(llm_client=None)
        turns = [
            Turn(
                turn_id="t1",
                user_text="hello",
                assistant_text="hi there",
                timestamp=datetime.now(),
            ),
        ]
        result = await summarizer.generate_summary(turns)
        # Placeholder returns simple concatenation
        assert isinstance(result, str)
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_generate_summary_with_multiple_turns(self):
        """Test generate_summary handles multiple turns."""
        summarizer = Summarizer(llm_client=None)
        turns = [
            Turn(
                turn_id="t1",
                user_text="first message",
                assistant_text="first reply",
                timestamp=datetime.now(),
            ),
            Turn(
                turn_id="t2",
                user_text="second message",
                assistant_text="second reply",
                timestamp=datetime.now(),
            ),
        ]
        result = await summarizer.generate_summary(turns)
        assert isinstance(result, str)
        assert "first" in result
        assert "second" in result


class TestSummarizerIntegration:
    @pytest.mark.asyncio
    async def test_full_summarization_workflow(self):
        """Test the full workflow: generate and save summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            summarizer = Summarizer(llm_client=None, summary_dir=tmpdir)

            # Create session with turns
            session = Session(session_id="test-session")
            for i in range(3):
                session.add_turn(Turn(
                    turn_id=f"t{i}",
                    user_text=f"user message {i}",
                    assistant_text=f"assistant reply {i}",
                    timestamp=datetime.now(),
                ))

            # Generate summary
            summary_content = await summarizer.generate_summary(session.turns)
            turn_ids = [t.turn_id for t in session.turns]

            # Save summary
            await summarizer.save_summary(session.session_id, summary_content, turn_ids)

            # Verify file was created
            filepath = os.path.join(tmpdir, f"{session.session_id}.md")
            assert os.path.exists(filepath)

            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            assert "user message" in content
            assert "assistant reply" in content

    def test_build_summary_prompt_with_empty_turns(self):
        """Test building prompt with empty turns list."""
        summarizer = Summarizer(llm_client=None)
        prompt = summarizer._build_summary_prompt([])
        assert "---" in prompt  # Template placeholder
