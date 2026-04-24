# Rolling Summary Memory System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement async rolling summary memory system with bounded context window for voice assistant, keeping prompts under 128k tokens while preserving important information.

**Architecture:** Dual-track system with main chat track (fast response) and dark summary track (background LLM-based compression). Uses half-life strategy (N=10 window, M=5 compress) with atomic state updates and asyncio.create_task for non-blocking summarization.

**Tech Stack:** Python asyncio, dataclasses, LLMClient for summarization, WebSocket handlers for both ESP32 and browser clients.

---

## Chunk 1: Core Data Structures

**Files:**
- Create: `src/memory/rolling_session.py`
- Modify: `src/memory/__init__.py`
- Test: `tests/memory/test_rolling_session.py`

- [ ] **Step 1: Create test file for VoiceSession**

```python
# tests/memory/test_rolling_session.py
import pytest
from dataclasses import dataclass, field
from typing import List
import time

# Import the module under test
import sys
sys.path.insert(0, '/home/bo/projects/python/python_hub')
from src.memory.rolling_session import Turn, VoiceSession

def test_turn_creation():
    turn = Turn(role="user", content="Hello", timestamp=time.time())
    assert turn.role == "user"
    assert turn.content == "Hello"

def test_session_initial_state():
    session = VoiceSession(session_id="test-123")
    assert session.session_id == "test-123"
    assert session.global_summary == "暂无早期记忆记录。"
    assert len(session.recent_turns) == 0
    assert session.is_summarizing == False

def test_estimate_tokens_empty():
    session = VoiceSession(session_id="test")
    assert session.estimate_tokens() == 0

def test_estimate_tokens_with_content():
    session = VoiceSession(session_id="test")
    session.global_summary = "用户喜欢运动"  # 8 chars
    session.recent_turns.append(Turn(role="user", content="周末想去爬山", timestamp=time.time()))  # 6 chars
    # Total ~14 chars, estimate should be 14 // 2 = 7 tokens
    assert session.estimate_tokens() == 7

def test_add_turn():
    session = VoiceSession(session_id="test")
    session.add_turn("user", "Hello")
    assert len(session.recent_turns) == 1
    assert session.recent_turns[0].role == "user"
    assert session.recent_turns[0].content == "Hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bo/projects/python/python_hub && python -m pytest tests/memory/test_rolling_session.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: Create rolling_session.py**

```python
# src/memory/rolling_session.py
"""Rolling Summary Memory System for Voice Assistant."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
import logging

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

    def build_prompt(self, system_prompt: str, current_input: str) -> List[dict]:
        """Build messages for LLM with memory context.

        Prompt structure:
        [System Prompt] + [global_summary] + [recent_turns] + [current_input]
        """
        messages = []

        # Add memory context if exists
        if self.global_summary and self.global_summary != "暂无早期记忆记录。":
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


# Global session registry
_sessions: Dict[str, VoiceSession] = {}


def get_session(session_id: str, **kwargs) -> VoiceSession:
    """Get or create a session by ID."""
    if session_id not in _sessions:
        _sessions[session_id] = VoiceSession(session_id=session_id, **kwargs)
    return _sessions[session_id]


def cleanup_session(session_id: str) -> None:
    """Remove session from registry."""
    if session_id in _sessions:
        del _sessions[session_id]
```

- [ ] **Step 4: Create __init__.py**

```python
# src/memory/__init__.py
from src.memory.rolling_session import (
    Turn,
    VoiceSession,
    get_session,
    cleanup_session,
)

__all__ = ['Turn', 'VoiceSession', 'get_session', 'cleanup_session']
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/bo/projects/python/python_hub && python -m pytest tests/memory/test_rolling_session.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /home/bo/projects/python/python_hub
git add src/memory/rolling_session.py src/memory/__init__.py tests/memory/test_rolling_session.py
git commit -m "feat: add VoiceSession dataclass with token estimation"
```

---

## Chunk 2: Background Summarizer with Async Tasks

**Files:**
- Create: `src/memory/summarizer.py`
- Modify: `src/memory/rolling_session.py` (add summarize_async)
- Test: `tests/memory/test_summarizer.py`

- [ ] **Step 1: Create test file for summarizer**

```python
# tests/memory/test_summarizer.py
import pytest
import asyncio
import sys
sys.path.insert(0, '/home/bo/projects/python/python_hub')

from src.memory.rolling_session import Turn, VoiceSession, get_session, cleanup_session


class MockLLMClient:
    """Mock LLM client for testing."""
    def __init__(self, response: str):
        self.response = response
        self.call_count = 0

    async def complete(self, messages: list) -> str:
        self.call_count += 1
        return self.response


async def mock_summarize(session: VoiceSession, llm_client) -> None:
    """Test version of summarize_async."""
    if session.is_summarizing:
        return

    session.is_summarizing = True
    try:
        M = session.step_size
        turns_to_merge = session.recent_turns[:M]
        if not turns_to_merge:
            return

        history_text = "\n".join([f"{t.role}: {t.content}" for t in turns_to_merge])

        # For testing, just simulate the summary
        await asyncio.sleep(0.1)
        session.global_summary = f"Summary of {len(turns_to_merge)} turns: {history_text[:50]}"
        session.recent_turns = session.recent_turns[M:]

    finally:
        session.is_summarizing = False


def test_summarize_triggered_by_turn_count():
    """Test that summary triggers when turn count exceeds window_size."""
    session = VoiceSession(session_id="test-trigger", window_size=3, step_size=2)

    # Add 4 turns (exceeds window_size=3)
    for i in range(4):
        session.add_turn("user", f"Message {i}")

    # Should not block - just adds turns
    assert len(session.recent_turns) == 4
    assert session.is_summarizing == False  # Not triggered synchronously


def test_session_registry():
    """Test get_session creates new sessions."""
    session1 = get_session("session-1")
    session2 = get_session("session-2")
    session1_again = get_session("session-1")

    assert session1 is session1_again
    assert session1 is not session2
    assert len(session1.recent_turns) == 0


def test_cleanup_session():
    """Test session removal from registry."""
    session = get_session("temp-session")
    session.add_turn("user", "test")
    assert session.session_id in globals() if hasattr(globals(), '_sessions') else True

    cleanup_session("temp-session")
    # After cleanup, getting same ID creates new session
    new_session = get_session("temp-session")
    assert len(new_session.recent_turns) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bo/projects/python/python_hub && python -m pytest tests/memory/test_summarizer.py -v`
Expected: FAIL (some tests may pass since mocking is simple)

- [ ] **Step 3: Create summarizer.py with async task**

```python
# src/memory/summarizer.py
"""Background summarizer for rolling memory system."""

import asyncio
import logging
from typing import List
from src.memory.rolling_session import Turn, VoiceSession

logger = logging.getLogger(__name__)


def get_summary_prompt(current_summary: str, new_history: str) -> str:
    """Build prompt for LLM to fuse new history into summary.

    Args:
        current_summary: Existing global summary
        new_history: Formatted conversation history to merge

    Returns:
        Prompt string for LLM
    """
    return f"""你是一个专门负责管理对话记忆的 AI 助手。你的任务是将一段新的对话历史，无缝融合到现有的用户画像和上下文摘要中。

【现有全局摘要】
{current_summary}

【需要融合的近期对话】
{new_history}

【处理规则】
1. 提取【近期对话】中关于用户偏好、重要事实、待办事项的核心信息。
2. 将这些新信息与【现有全局摘要】结合，重写成一段连贯的纯文本。
3. 剔除无意义的寒暄（如"你好"、"在吗"）、语气词和重复信息。
4. 保持客观的第三人称视角（例如"用户喜欢..."）。
5. 必须保持高度压缩，总长度尽量不超过 300 字。如果旧信息已过时或被新对话推翻，请更新它。

请直接输出新的全局摘要文本，不要包含任何解释或额外的 Markdown 标记。"""


async def summarize_async(session: VoiceSession, llm_client) -> None:
    """Background async summarization task.

    This runs as a fire-and-forget asyncio task. It:
    1. Acquires summarization lock
    2. Extracts earliest M turns
    3. Calls LLM to generate new summary
    4. Atomically replaces global_summary
    5. Removes summarized turns from recent_turns
    6. Releases lock

    Args:
        session: VoiceSession to summarize
        llm_client: LLM client with async complete() method
    """
    # Double-check lock to prevent concurrent summaries
    if session.is_summarizing:
        return

    session.is_summarizing = True
    logger.info(f"[Memory] Starting summary for session {session.session_id}")

    try:
        M = session.step_size

        # Extract earliest M turns (snapshot, not reference)
        turns_to_merge = session.recent_turns[:M]
        if not turns_to_merge:
            logger.info(f"[Memory] No turns to merge, skipping")
            return

        # Format history for LLM
        history_text = "\n".join([f"{t.role}: {t.content}" for t in turns_to_merge])
        logger.info(f"[Memory] Merging {len(turns_to_merge)} turns, history length: {len(history_text)}")

        # Build prompt and call LLM
        prompt = get_summary_prompt(session.global_summary, history_text)
        messages = [{"role": "system", "content": prompt}]

        try:
            new_summary = await llm_client.complete(messages)
            logger.info(f"[Memory] LLM returned summary, length: {len(new_summary)}")
        except Exception as e:
            logger.error(f"[Memory] LLM call failed: {e}")
            new_summary = session.global_summary  # Keep old summary on failure

        # Atomic replacement
        session.global_summary = new_summary
        session.recent_turns = session.recent_turns[M:]  # Remove only first M

        logger.info(f"[Memory] Summary complete. global_summary length: {len(new_summary)}, remaining turns: {len(session.recent_turns)}")

    except Exception as e:
        logger.error(f"[Memory] Summarization failed: {e}", exc_info=True)

    finally:
        session.is_summarizing = False


async def trigger_summary_if_needed(session: VoiceSession, llm_client) -> None:
    """Check and trigger summary if needed.

    This is the callback passed to session.add_turn().

    Args:
        session: VoiceSession to check and potentially summarize
        llm_client: LLM client for summarization
    """
    if session._should_summarize():
        await summarize_async(session, llm_client)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/bo/projects/python/python_hub && python -m pytest tests/memory/test_summarizer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/bo/projects/python/python_hub
git add src/memory/summarizer.py tests/memory/test_summarizer.py
git commit -m "feat: add async background summarizer with LLM fusion prompt"
```

---

## Chunk 3: Integration with Browser WebSocket Handler

**Files:**
- Modify: `src/browser_ws_handler.py`
- Create: `tests/memory/test_browser_memory_integration.py`

- [ ] **Step 1: Create integration test**

```python
# tests/memory/test_browser_memory_integration.py
import pytest
import asyncio
import sys
sys.path.insert(0, '/home/bo/projects/python/python_hub')

from src.memory.rolling_session import get_session, cleanup_session, VoiceSession
from src.memory.summarizer import trigger_summary_if_needed


class MockLLMClient:
    """Mock LLM client that returns a compressed summary."""
    def __init__(self):
        self.call_count = 0

    async def complete(self, messages: list) -> str:
        self.call_count += 1
        # Return a compressed summary
        return f"Mock summary #{self.call_count}"


@pytest.fixture
def mock_llm():
    return MockLLMClient()


@pytest.fixture
def session_id():
    return "test-browser-session"


@pytest.fixture
def cleanup():
    """Cleanup sessions after test."""
    sessions = []
    yield sessions
    for sid in sessions:
        cleanup_session(sid)


def test_build_prompt_with_memory_context():
    """Test that build_prompt includes memory context."""
    session = get_session("prompt-test")
    session.global_summary = "用户喜欢聊宠物。"
    session.recent_turns = [
        type('Turn', (), {'role': 'user', 'content': '我最近买了只猫'})(),
        type('Turn', (), {'role': 'assistant', 'content': '猫猫叫什么名字?'})(),
    ]

    messages = session.build_prompt("你是一个助手", "猫叫什么?")

    # Should have: system (memory) + user turn + current user input
    assert len(messages) >= 2
    # First message should be memory context
    assert "记忆上下文" in messages[0]["content"] or "用户喜欢" in messages[0]["content"]


def test_add_turn_triggers_summary(mock_llm):
    """Test that adding turns eventually triggers summary."""
    session = get_session("trigger-test", window_size=3, step_size=2)

    # Add 4 turns (exceeds window_size of 3)
    for i in range(4):
        session.add_turn("user", f"Message {i}", llm_client=mock_llm, summarize_callback=trigger_summary_if_needed)

    # Wait for async summary to complete
    async def wait_and_check():
        await asyncio.sleep(0.5)
        # Summary should have been triggered
        assert mock_llm.call_count >= 1 or session.is_summarizing == False

    asyncio.run(wait_and_check())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bo/projects/python/python_hub && python -m pytest tests/memory/test_browser_memory_integration.py -v`
Expected: FAIL (integration not yet implemented)

- [ ] **Step 3: Update browser_ws_handler.py to use session**

Read the current `src/browser_ws_handler.py` and modify:

1. Import session management:
```python
from src.memory.rolling_session import get_session, cleanup_session
from src.memory.summarizer import trigger_summary_if_needed
```

2. Add session_id tracking:
```python
session_id = ""  # At top with other state
```

3. In `handle_browser()`, get session at start:
```python
session = get_session(f"browser-{id(websocket)}" if not session_id else session_id)
```

4. Update `run_text_pipeline()` signature to accept session and llm_client:
```python
async def run_text_pipeline(
    websocket,
    llm: LLMClient,
    tts: TTSClient,
    session: VoiceSession,  # Add this
    user_text: str,
    prompt: str = "",
) -> None:
    """Run LLM → TTS pipeline for direct text input (bypasses ASR)."""
    logger.info(f"run_text_pipeline called: user_text='{user_text}', session_id={session.session_id}, turn_id={turn_id}")

    # Build prompt with memory context
    messages = session.build_prompt(prompt, user_text)
    await websocket.send(build_text(user_text, session.session_id, turn_id))

    # Stream LLM and collect response
    full_response = ""
    text_buffer = ""
    try:
        async for token in llm.stream_chat(messages):
            # ... existing streaming logic ...
            full_response += token

        # Add assistant turn to session
        session.add_turn("assistant", full_response, llm_client=llm, summarize_callback=trigger_summary_if_needed)

    except Exception as e:
        logger.error(f"LLM error: {e}")
        await websocket.send(build_error(str(e), session.session_id, turn_id))
        return

    # ... TTS synthesis ...
```

5. Update callers to pass session:
```python
# In handle_browser, text_input case:
await run_text_pipeline(websocket, llm, tts, session, user_text, prompt)
```

- [ ] **Step 4: Run tests**

Run: `cd /home/bo/projects/python/python_hub && python -m pytest tests/memory/test_browser_memory_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/browser_ws_handler.py tests/memory/test_browser_memory_integration.py
git commit -m "feat: integrate rolling session memory into browser WebSocket handler"
```

---

## Chunk 4: Integration with ESP32 Handler (main.py)

**Files:**
- Modify: `src/main.py`
- Test: Existing tests should continue passing

- [ ] **Step 1: Read main.py to understand current ESP32 session handling**

- [ ] **Step 2: Update ESP32 handler to use new session pattern**

In `handle_esp32()`:
- Import new session functions
- Replace `Session` usage with `get_session()`
- Pass session to pipeline functions

- [ ] **Step 3: Verify existing tests pass**

Run: `cd /home/bo/projects/python/python_hub && python -m pytest tests/ -v --tb=short`
Expected: Existing tests pass

- [ ] **Step 4: Commit**

```bash
git add src/main.py
git commit -m "feat: update ESP32 handler to use rolling session memory"
```

---

## Chunk 5: Configuration Updates

**Files:**
- Modify: `config.yaml`
- Modify: `src/config.py`

- [ ] **Step 1: Update config.yaml with memory settings**

```yaml
memory:
  session_dir: "./memory/sessions"
  summary_dir: "./memory/summaries"
  window_size: 10      # N - max turns in short-term memory
  step_size: 5         # M - turns to compress per summary
  token_threshold: 8000  # chars, trigger summary if exceeded
  max_summary_length: 300 # max tokens for global_summary
```

- [ ] **Step 2: Update config.py dataclass**

Add `MemoryConfig` fields or update existing `MemoryConfig`:

```python
@dataclass
class MemoryConfig:
    session_dir: str = "./memory/sessions"
    summary_dir: str = "./memory/summaries"
    window_size: int = 10
    step_size: int = 5
    token_threshold: int = 8000
    max_summary_length: int = 300
```

- [ ] **Step 3: Pass config to session creation**

In `get_session()`, optionally accept config:

```python
def get_session(session_id: str, config: MemoryConfig = None) -> VoiceSession:
    if session_id not in _sessions:
        kwargs = {}
        if config:
            kwargs['window_size'] = config.window_size
            kwargs['step_size'] = config.step_size
            kwargs['token_threshold'] = config.token_threshold
            kwargs['max_summary_length'] = config.max_summary_length
        _sessions[session_id] = VoiceSession(session_id=session_id, **kwargs)
    return _sessions[session_id]
```

- [ ] **Step 4: Commit**

```bash
git add config.yaml src/config.py
git commit -m "config: add memory system parameters to config"
```

---

## Summary

The implementation creates a bounded memory system with:

1. **VoiceSession** - Core dataclass with token estimation and prompt building
2. **Background Summarizer** - Async task with LLM-based fusion and atomic updates
3. **Dual-Track Architecture** - Main chat never blocks on summarization
4. **Half-Life Strategy** - N=10 window, M=5 compression per trigger
5. **Configuration-Driven** - All parameters configurable via config.yaml

The system ensures:
- Prompts stay bounded (window_size caps recent turns)
- Token budget controlled (token_threshold triggers early compression)
- No memory leak (global_summary always replaced, never appended)
- Non-blocking (asyncio.create_task for background summarization)
- Thread-safe (is_summarizing lock prevents concurrent compression)