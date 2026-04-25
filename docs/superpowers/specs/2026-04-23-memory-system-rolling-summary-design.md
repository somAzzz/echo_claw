# Voice Assistant Memory System - Rolling Summary Design

## Overview

A memory management system for voice assistants that maintains a bounded context window while preserving important information through asynchronous LLM-based summarization. Designed for ultra-low latency voice interactions with strict token budget control.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      VoiceSession                             │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────┐  │
│  │ global_summary  │  │  recent_turns    │  │is_summarizing│ │
│  │     (str)       │  │  (List[Turn])    │  │    (bool)  │  │
│  └─────────────────┘  └──────────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────────┐
    │ Prompt   │   │ Token    │   │  Background  │
    │ Builder  │   │ Estimator│   │  Summarizer   │
    └──────────┘   └──────────┘   └──────────────┘
```

## Core Concepts

### Rolling Window (Sliding Memory)

- **N (window_size)**: Maximum number of recent turns kept in short-term memory (default: 10)
- **M (step_size)**: Number of oldest turns to compress when window overflows (default: 5 = N/2)
- **Half-life Strategy**: When turns exceed N, compress earliest M turns into global summary

### Global Summary

- Compressed representation of all older turns
- Generated via LLM "memory fusion" - not simple concatenation
- Always replaced atomically, never appended to (prevents memory leak)
- Target max length: ~300 tokens

### Prompt Structure (sent to LLM)

```
[System Prompt] + [global_summary] + [recent_turns (max N)] + [current_input]
```

## Configuration

```yaml
memory:
  window_size: 10        # N - max turns in short-term memory
  step_size: 5          # M - turns to compress per summary (N/2)
  token_threshold: 8000 # chars, trigger summary if estimated tokens exceed this
  max_summary_length: 300 # max tokens for global_summary
```

## Data Structures

### Turn

```python
@dataclass
class Turn:
    role: str        # "user" or "assistant"
    content: str     # text content
    timestamp: float # Unix timestamp
```

### VoiceSession

```python
@dataclass
class VoiceSession:
    session_id: str
    global_summary: str = "暂无早期记忆记录。"
    recent_turns: List[Turn] = field(default_factory=list)
    is_summarizing: bool = False

    def estimate_tokens(self) -> int:
        """Simple token estimator: chars // 2 for Chinese, ~1.5 char per token"""
        total_chars = len(self.global_summary)
        for turn in self.recent_turns:
            total_chars += len(turn.content)
        return total_chars // 2

    def build_prompt(self, system_prompt: str, current_input: str) -> List[dict]:
        """Build messages for LLM with memory context"""
        messages = []
        if self.global_summary and self.global_summary != "暂无早期记忆记录。":
            messages.append({
                "role": "system",
                "content": f"[记忆上下文]\n{self.global_summary}"
            })
        for turn in self.recent_turns[-self.window_size:]:
            messages.append({"role": turn.role, "content": turn.content})
        messages.append({"role": "user", "content": current_input})
        return messages

    def add_turn(self, role: str, content: str):
        """Add a turn and trigger async summary if needed"""
        self.recent_turns.append(Turn(role=role, content=content, timestamp=time.time()))

        # Check trigger conditions (async trigger, non-blocking)
        if self._should_summarize():
            asyncio.create_task(summarize_async(self, config))

    def _should_summarize(self) -> bool:
        """Check if summary should be triggered"""
        if self.is_summarizing:
            return False
        if len(self.recent_turns) > self.window_size:
            return True
        if self.estimate_tokens() > self.token_threshold:
            return True
        return False
```

## Dual-Track Architecture (Critical Clarification)

**IMPORTANT**: LLM is **stateless** - it does NOT automatically summarize in the background while chatting. The summary is a **completely separate LLM API call**.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     REAL SERVER WORKFLOW                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  🛤️ TRACK 1: Main Chat (Fast Response)                              │
│  ────────────────────────────────────────────────────────────────    │
│  User: "我周末想去爬山"                                              │
│       │                                                               │
│       ▼                                                               │
│  1. Assemble main prompt:                                             │
│     System + global_summary + recent_turns + User input              │
│       │                                                               │
│       ▼                                                               │
│  2. Call LLM (blocking for first token)                             │
│       │                                                               │
│       ▼                                                               │
│  3. Stream response → WebSocket → TTS → User hears response         │
│       │                                                               │
│       ▼                                                               │
│  4. Add turn to recent_turns:                                        │
│     {role: "user", content: "..."} + {role: "assistant", content}    │
│                                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  🛤️ TRACK 2: Dark Summary (Background, Non-Blocking)                │
│  ────────────────────────────────────────────────────────────────    │
│  Immediately after step 4: check if should_summarize()              │
│       │                                                               │
│       ▼                                                               │
│  If triggered: asyncio.create_task(summarize_async())               │
│       │  (happens in background, user is listening to TTS)           │
│       ▼                                                               │
│  Extract earliest M turns                                             │
│       │                                                               │
│       ▼                                                               │
│  Build summary prompt: "你是记忆整理员，融合以下对话..."              │
│       │                                                               │
│       ▼                                                               │
│  SECOND LLM API CALL (2-3 sec latency OK, user doesn't wait)         │
│       │                                                               │
│       ▼                                                               │
│  Replace global_summary atomically                                    │
│  Remove M turns from recent_turns                                     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Background Summarizer

### Trigger Conditions (Dual-Gate)

1. **轮数触发**: `len(recent_turns) > window_size`
2. **Token 触发**: `estimate_tokens() > token_threshold`

Both conditions checked before triggering. If already summarizing, skip.

### Async Summary Flow

```
LLM Response Complete
    │
    ▼
add_turn() called
    │
    ▼
_should_summarize() checks:
  - is_summarizing == False?
  - len(recent_turns) > N OR tokens > threshold?
    │
    ├─ NO → No action, return immediately
    └─ YES → asyncio.create_task(summarize_async())
                │
                ├── set is_summarizing = True
                ├── extract earliest M turns
                ├── build history_text
                ├── call LLM with fusion prompt
                ├── atomically replace global_summary
                ├── remove summarized M from recent_turns
                └── set is_summarizing = False
```

### Atomic Replacement Logic

Critical: The extraction and replacement must be atomic to prevent data corruption:

```python
async def summarize_async(session: VoiceSession, config: dict):
    if session.is_summarizing:
        return

    session.is_summarizing = True
    try:
        M = config.get('step_size', 5)

        # Extract earliest M turns (snapshot, not reference)
        turns_to_merge = session.recent_turns[:M]
        if not turns_to_merge:
            return

        # Format history for LLM
        history_text = "\n".join([f"{t.role}: {t.content}" for t in turns_to_merge])

        # Generate new summary via LLM
        prompt = get_summary_prompt(session.global_summary, history_text)
        new_summary = await llm.async_complete(prompt)

        # Atomic replacement - user can still add turns during this time
        session.global_summary = new_summary
        session.recent_turns = session.recent_turns[M:]  # Remove only first M

    finally:
        session.is_summarizing = False
```

## Summary Fusion Prompt

```python
def get_summary_prompt(current_summary: str, new_history: str) -> str:
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
```

## Integration Points

### browser_ws_handler.py

1. Create `sessions: Dict[str, VoiceSession]` at module level
2. On `text_input`:
   - Get or create session for connection
   - Call `session.build_prompt(prompt_content, user_text)`
   - Pass result to `llm.stream_chat()`
   - After response, call `session.add_turn("assistant", response)`

3. On `audio_end` (ASR pipeline):
   - Same session management flow

### ESP32 Handler (main.py)

Already has `Session` class - needs to be updated to use new `VoiceSession` pattern with async summarization.

## Session Management

```python
# Global session registry
sessions: Dict[str, VoiceSession] = {}

def get_session(session_id: str) -> VoiceSession:
    if session_id not in sessions:
        sessions[session_id] = VoiceSession(session_id=session_id)
    return sessions[session_id]

def cleanup_session(session_id: str):
    """Called on session_end or idle timeout"""
    if session_id in sessions:
        del sessions[session_id]
```

## Error Handling

1. **LLM Summary Failure**: Log error, keep existing memory intact, reset `is_summarizing` flag
2. **Concurrent Summaries**: Prevented by `is_summarizing` lock
3. **Session Not Found**: Create new session with empty memory

## Performance Considerations

- Token estimation: `chars // 2` (conservative for Chinese)
- Summary is non-blocking - user can continue speaking
- Memory is bounded regardless of conversation length
- Target: Keep final prompt under 10k tokens for fast TTFB

## Files to Modify/Create

1. `src/memory/rolling_session.py` - VoiceSession class with async summarization ✅ (implemented)
2. `src/memory/prompts.py` - Summary fusion prompt template ✅ (implemented)
3. `src/memory/storage.py` - Disk persistence for summaries ✅ (implemented)
4. `src/memory/global_memory.py` - BM25 cross-session memory ✅ (implemented)
5. `src/memory/retriever.py` - BM25Plus + jieba tokenization ✅ (implemented)
6. `src/browser_ws_handler.py` - Integrate session management ✅ (implemented)
7. `src/main.py` - Update ESP32 handler to use new session pattern ✅ (implemented)

---

## Implementation Status (2026-04-25)

### Completed Features

- [x] VoiceSession with dual-track rolling compression
- [x] Async summarization via asyncio.create_task
- [x] Disk persistence via SessionStorage (JSON)
- [x] Cross-session global memory via BM25Plus + jieba
- [x] force_summarize for session-end data preservation
- [x] Global memory trigger patterns (26 Chinese patterns)
- [x] Integration into both browser_ws_handler and main.py

### Configuration

```yaml
memory:
  window_size: 10        # N - max turns in short-term memory
  step_size: 5           # M - turns to compress per summary (N/2)
  token_threshold: 8000   # chars, trigger summary if exceeded
  max_summary_length: 300 # max chars for global_summary
  global_dir: "./memory/global"  # cross-session memory directory
  top_k: 3               # BM25 retrieval top-k
  max_chars: 2000         # max chars for global context retrieval
```