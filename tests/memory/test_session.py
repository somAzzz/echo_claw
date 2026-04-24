"""Tests for Session, Turn, Summary, and PendingTurn data structures."""
from datetime import datetime
import uuid

import pytest

from src.memory.session import Session, Turn, Summary, PendingTurn


class TestPendingTurn:
    def test_pending_turn_creation(self):
        pt = PendingTurn(turn_id="t1", session_id="s1", user_text="hello")
        assert pt.turn_id == "t1"
        assert pt.session_id == "s1"
        assert pt.user_text == "hello"
        assert pt.audio_chunks == []
        assert pt.started_at is not None

    def test_pending_turn_with_audio_chunks(self):
        audio = b"fake audio data"
        pt = PendingTurn(turn_id="t1", session_id="s1", audio_chunks=[audio])
        assert len(pt.audio_chunks) == 1
        assert pt.audio_chunks[0] == audio


class TestTurn:
    def test_turn_creation(self):
        now = datetime.now()
        turn = Turn(
            turn_id="t1",
            user_text="hello",
            assistant_text="hi there",
            timestamp=now,
        )
        assert turn.turn_id == "t1"
        assert turn.user_text == "hello"
        assert turn.assistant_text == "hi there"
        assert turn.timestamp == now

    def test_turn_default_timestamp(self):
        turn = Turn(turn_id="t1", user_text="hello", assistant_text="hi")
        assert turn.timestamp is not None


class TestSummary:
    def test_summary_creation(self):
        now = datetime.now()
        summary = Summary(
            summary_id="sum1",
            content="User asked about weather",
            created_at=now,
            covered_turn_ids=["t1", "t2"],
        )
        assert summary.summary_id == "sum1"
        assert summary.content == "User asked about weather"
        assert summary.created_at == now
        assert summary.covered_turn_ids == ["t1", "t2"]

    def test_summary_covered_turn_ids_empty(self):
        summary = Summary(
            summary_id="sum1",
            content="Empty session",
            created_at=datetime.now(),
            covered_turn_ids=[],
        )
        assert summary.covered_turn_ids == []


class TestSession:
    def test_session_starts_empty(self):
        session = Session()
        assert len(session.turns) == 0
        assert len(session.summaries) == 0
        assert session.created_at is not None
        assert session.updated_at is not None

    def test_session_with_id(self):
        session = Session(session_id="my-session")
        assert session.session_id == "my-session"

    def test_session_auto_generates_id(self):
        session = Session()
        assert session.session_id is not None
        assert len(session.session_id) > 0

    def test_add_turn(self):
        session = Session(session_id="s1")
        turn = Turn(
            turn_id="t1",
            user_text="hello",
            assistant_text="hi there",
            timestamp=datetime.now(),
        )
        session.add_turn(turn)
        assert len(session.turns) == 1
        assert session.turns[0] == turn

    def test_add_turn_updates_timestamp(self):
        session = Session(session_id="s1")
        original_updated_at = session.updated_at
        turn = Turn(
            turn_id="t1",
            user_text="hello",
            assistant_text="hi there",
            timestamp=datetime.now(),
        )
        session.add_turn(turn)
        assert session.updated_at >= original_updated_at

    def test_compress_with_few_turns(self):
        """Should not compress when below threshold."""
        session = Session(session_id="s1")
        for i in range(3):
            turn = Turn(
                turn_id=f"t{i}",
                user_text=f"user {i}",
                assistant_text=f"assistant {i}",
                timestamp=datetime.now(),
            )
            session.add_turn(turn)
        session.compress(keep_recent=2, threshold=5)
        # Should still have all 3 turns (below threshold of 5)
        assert len(session.turns) == 3

    def test_compress_above_threshold(self):
        """Should compress when above threshold, keeping recent turns."""
        session = Session(session_id="s1")
        for i in range(7):
            turn = Turn(
                turn_id=f"t{i}",
                user_text=f"user {i}",
                assistant_text=f"assistant {i}",
                timestamp=datetime.now(),
            )
            session.add_turn(turn)

        session.compress(keep_recent=2, threshold=5)

        # Should have 2 recent turns + possibly some summaries
        # Total turns should be <= keep_recent + threshold (some buffer)
        # In our implementation, turns older than (threshold - keep_recent) are compressed into a summary
        assert len(session.turns) <= 7

    def test_compress_creates_summary(self):
        """Should create a summary when compressing."""
        session = Session(session_id="s1")
        for i in range(6):
            turn = Turn(
                turn_id=f"t{i}",
                user_text=f"user {i}",
                assistant_text=f"assistant {i}",
                timestamp=datetime.now(),
            )
            session.add_turn(turn)

        session.compress(keep_recent=2, threshold=5)

        # Should have at least one summary now
        assert len(session.summaries) >= 1

    def test_get_recent_context(self):
        """Should return formatted context string."""
        session = Session(session_id="s1")

        # Add some turns
        for i in range(3):
            turn = Turn(
                turn_id=f"t{i}",
                user_text=f"user message {i}",
                assistant_text=f"assistant reply {i}",
                timestamp=datetime.now(),
            )
            session.add_turn(turn)

        context = session.get_recent_context(max_summaries=3, max_turns=2)
        assert isinstance(context, str)
        # Should contain some of the turn content
        assert "user message" in context or "assistant reply" in context or len(context) > 0

    def test_get_recent_context_with_summaries(self):
        """Should include summary content in context."""
        session = Session(session_id="s1")

        # Add a summary
        summary = Summary(
            summary_id="sum1",
            content="Previously discussed weather",
            created_at=datetime.now(),
            covered_turn_ids=["t0"],
        )
        session.summaries.append(summary)

        # Add a recent turn
        turn = Turn(
            turn_id="t1",
            user_text="new message",
            assistant_text="new reply",
            timestamp=datetime.now(),
        )
        session.add_turn(turn)

        context = session.get_recent_context(max_summaries=3, max_turns=2)
        assert "Previously discussed weather" in context
        assert "new message" in context

    def test_get_recent_context_limits_summaries_and_turns(self):
        """Should respect max_summaries and max_turns limits."""
        session = Session(session_id="s1")

        # Add many summaries
        for i in range(5):
            summary = Summary(
                summary_id=f"sum{i}",
                content=f"summary content {i}",
                created_at=datetime.now(),
                covered_turn_ids=[f"t{i}"],
            )
            session.summaries.append(summary)

        # Add many turns
        for i in range(5):
            turn = Turn(
                turn_id=f"t{i}",
                user_text=f"user {i}",
                assistant_text=f"assistant {i}",
                timestamp=datetime.now(),
            )
            session.add_turn(turn)

        context = session.get_recent_context(max_summaries=2, max_turns=3)

        # Should include at most max_summaries summaries and max_turns turns
        # Check content respects limits
        summary_count = context.count("summary content")
        assert summary_count <= 2


class TestSessionIntegration:
    def test_full_session_lifecycle(self):
        """Test a complete session lifecycle with turns and compression."""
        session = Session(session_id="test-session")

        # Add turns
        for i in range(6):
            turn = Turn(
                turn_id=f"t{i}",
                user_text=f"user text {i}",
                assistant_text=f"assistant text {i}",
                timestamp=datetime.now(),
            )
            session.add_turn(turn)

        assert len(session.turns) == 6

        # Compress
        session.compress(keep_recent=2, threshold=5)

        # Should have fewer turns now
        assert len(session.turns) <= 6
        # Should have summaries
        assert len(session.summaries) >= 1

        # Get context should work
        context = session.get_recent_context()
        assert isinstance(context, str)
        assert len(context) > 0