# Memory System E2E Test Design

## Overview

End-to-end test for the dual-track memory system (Global Memory, Sessions, Summaries) via Playwright + Frontend + Backend WebSocket pipeline.

## Architecture

```
Browser (Playwright)  →  Frontend (5173)  →  Backend WS (8767)
                                                   ↓
                                              Memory Pipeline
                                                   ↓
                           ┌────────────────────────┼────────────────────────┐
                           ↓                        ↓                        ↓
                    Global Memory            Rolling Summary            Session
                    (memory/global/)         (memory/summaries/)       (in-memory)
```

## Test Flow

### 1. Precondition
- Clean test environment: clear summaries and global directories
- All Docker services running (python-hub, frontend, llama-server, funasr-api)

### 2. Send Messages
- 12 messages sent via Playwright through Frontend WebSocket
- Messages designed to trigger:
  - Rolling summary after 10 turns (window_size=10)
  - Global memory recall with trigger words ("还记得", "上次", "之前")

### 3. Capture Session ID
- Extract `session_id=ts-{timestamp}` from Backend logs

### 4. Wait for Async Processing
- Summarization runs via `asyncio.create_task()` in background
- Wait 3-5 seconds for completion

### 5. Verify Results

| Component | Verification | File Location |
|-----------|-------------|---------------|
| Session | Messages received | Backend logs |
| Rolling Summary | JSON created | `memory/summaries/ts-{ts}.json` |
| Global Memory | MD created with front-matter | `memory/global/{ts}.md` |

## Verification Points

### Session Verification
- Backend logs show `text_input received: session_id=ts-{ts}`

### Summary Verification
```json
{
  "session_id": "ts-{ts}",
  "global_summary": "...",
  "saved_at": "2026-04-26T..."
}
```

### Global Memory Verification
```markdown
---
created: 2026-04-26T...
session_id: ts-{ts}
---
[Summary content]
```

## Key Functions

- `generate_filename(".json")` → `{YYYYMMDD}_{HHMMSS}_{ts}.json`
- `generate_session_id()` → `ts-{timestamp}`
- `summarize_async()` - Background rolling summary
- `GlobalMemory.write()` - Cross-session memory storage

## Test Script Location

`frontend/test_memory_e2e.cjs` - Playwright script for E2E testing

## Success Criteria

1. New summary JSON file appears in `memory/summaries/`
2. New global memory MD file appears in `memory/global/`
3. Session ID format is `ts-{timestamp}` (unified naming)
4. Summary JSON contains session_id matching the conversation
5. Global memory front-matter contains correct session_id
6. No errors in Backend logs during processing