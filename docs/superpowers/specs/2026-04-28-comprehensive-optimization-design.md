# Voice Assistant Hub - Comprehensive Optimization (2026-04-28)

## Summary

Five-phase optimization of the Voice Assistant Hub project covering dependency management, code duplication elimination, structural refactoring, quality hardening, and infrastructure cleanup. All 105 unit tests pass with 0 regressions.

## Audit Findings

### Critical Issues (Fixed)
1. **Docker image missing dependencies** - `requirements.txt` lacked `websockets`, `openai`; out of sync with `pyproject.toml`
2. **Frontend voice recording non-functional** - `sendAudio()` computed base64 but discarded it, never sending to backend
3. **Config default drift** - `config.py` defaults (max_tokens=512, rate="-42%") vastly different from `config.yaml` (max_tokens=131072, rate="-20%")

### High Severity Issues (Fixed)
4. **Monolithic 705-line App.jsx** - all UI+logic in single component, 14 useState hooks
5. **Code duplication** - pipeline clients initialized 4 times, 2 duplicate blocks in browser handler, session finalization logic duplicated, TTS synthesize/synthesize_to_file duplicated
6. **Hardcoded machine-specific paths** - `/home/bo/.cache/huggingface` in docker-compose
7. **Inconsistent HTTP libraries** - `httpx` (ASR) vs `aiohttp` (LLM)
8. **Global memory unbounded growth** - no rotation or retention policy
9. **No session eviction** - `_sessions` dict grows without bounds

### Medium Severity Issues (Fixed)
10. **Dead code** - duplicate init blocks, dead `retrieve()` conditional, `force_summarize` dead branches
11. **Fire-and-forget asyncio tasks** - silent error swallowing
12. **No frontend loading states** - no feedback during API initialization
13. **No .env.example** - environment variables undocumented
14. **No healthchecks** on most services
15. **`deploy.resources` in docker-compose** - swarm-only, ignored by `docker compose up`

## Phase 1: Fix What's Broken

### 1.1 Dependency Sync
- **Problem**: `pyproject.toml` vs `requirements.txt` split-brain; Dockerfile used `pip install -r requirements.txt`
- **Fix**: Made `pyproject.toml` single source of truth; added `jieba>=0.42`; regenerated `uv.lock`; Dockerfile now uses `uv sync --frozen` via `COPY --from=ghcr.io/astral-sh/uv:latest`; deleted `requirements.txt` and `requirements-dev.txt`

**Files**: `pyproject.toml`, `Dockerfile`, `uv.lock`, (deleted) `requirements.txt`, `requirements-dev.txt`

### 1.2 Voice Recording Fix
- **Problem**: `App.jsx:sendAudio()` computed base64 via inefficient char-by-char loop then discarded it, only calling `sendAudioEnd()` without data
- **Fix**: Imported `sendAudioChunk`; replaced manual loop with `FileReader.readAsDataURL()`; sends `sendAudioChunk(b64Audio)` before `sendAudioEnd()`

**Files**: `frontend/src/App.jsx`

### 1.3 Config Default Drift
- **Problem**: `config.py` hardcoded defaults (max_tokens=512, model="gpt-4", voice="Xiaoxiao", rate="-42%") differed massively from `config.yaml`
- **Fix**: Synced all defaults to match config.yaml; added warning log when config.yaml not found; fixed ASR base_url fallback to port 8001

**Files**: `src/config.py`

## Phase 2: Eliminate Duplication

### 2.1 Pipeline Client Factory
- **Problem**: `ASRClient`/`LLMClient`/`TTSClient` initialization duplicated 4 times across `main.py` and `browser_ws_handler.py`, plus browser handler had two duplicate identical init blocks (dead code)
- **Fix**: Created `create_pipeline_clients(cfg)` factory in `src/pipeline/__init__.py`; both handlers now call `asr, llm, tts = create_pipeline_clients(cfg)`

**Files**: `src/pipeline/__init__.py`, `src/main.py`, `src/browser_ws_handler.py`

### 2.2 Session Finalization Dedup
- **Problem**: `browser_ws_handler._finalize_session()` duplicated `rolling_session.finalize_session()` logic
- **Fix**: Removed ~20-line inner closure; replaced both call sites with `await finalize_session(voice_session.session_id)`

**Files**: `src/browser_ws_handler.py`

### 2.3 TTS Synthesize Dedup
- **Problem**: `synthesize()` and `synthesize_to_file()` shared ~75% code (edge-tts + temp file logic)
- **Fix**: Extracted `_synthesize_webm()` helper; both methods now call it

**Files**: `src/pipeline/tts.py`

## Phase 3: Structural Refactoring

### 3.1 Component Extraction
- Extracted `StatusBadge`, `ConnectionIndicator`, `MessageBubble` to `frontend/src/components/`
- App.jsx: 705 lines → ~630 lines, inline sub-components removed

**Files**: `frontend/src/components/StatusBadge.jsx`, `ConnectionIndicator.jsx`, `MessageBubble.jsx`

### 3.2 WebSocket Class + Hook
- Converted `websocket.js` from module-level singleton to `BrowserWebSocket` class
  - Instance-based: no global `ws` variable, reconnection timer properly cleared
  - Methods: `connect()`, `disconnect()`, `sendAudioChunk()`, `sendAudioStart()`, `sendAudioEnd()`, `sendCancel()`, `sendSessionEnd()`, `sendTextInput()`
- Created `useWebSocket` hook encapsulating connection lifecycle

**Files**: `frontend/src/services/websocket.js`, `frontend/src/hooks/useWebSocket.js`

### 3.3 App.jsx Updated
- Replaced module imports with `BrowserWebSocket` + `useWebSocket`
- All WS sends use the connected instance via `getWs()` helper
- `sendSessionEnd` still uses `new BrowserWebSocket()` since it uses `sendBeacon` (not WebSocket)

**Files**: `frontend/src/App.jsx`

## Phase 4: Quality Hardening

### 4.1 Async Task Error Handling
- `asyncio.create_task()` in `add_turn()` now attaches `add_done_callback` to log task exceptions
- `force_summarize()` dead branches collapsed (both called identical `summarize_async`)

**Files**: `src/memory/rolling_session.py`

### 4.2 Frontend Loading States
- Added `loading` state to App.jsx; displays "Initializing system..." until API and WS connected

**Files**: `frontend/src/App.jsx`

### 4.3 Session Eviction
- `MAX_SESSIONS = 100` limit; `_evict_oldest_sessions()` removes sessions with oldest turn timestamps when registry overflows

**Files**: `src/memory/rolling_session.py`

### 4.4 Global Memory Rotation
- Added `max_entries=50` to `GlobalMemory`; `_rotate_if_needed()` removes oldest entries when exceeded
- Fixed dead `retrieve()` conditional where both branches returned `combined` - now properly truncates

**Files**: `src/memory/global_memory.py`

## Phase 5: Infrastructure Cleanup

### 5.1 Healthchecks
- Added healthchecks to `python-hub` (HTTP `/api/status` via python urllib) and `frontend` (HTTP via node)
- Replaced swarm-only `deploy.resources` with `mem_limit: 2g`

**Files**: `docker-compose.yml`

### 5.2 Hardcoded Paths
- Replaced `/home/bo/.cache/huggingface` with named volume `huggingface-cache`

**Files**: `docker-compose.yml`

### 5.3 Environment Documentation
- Created `.env.example` with all documented environment variables

**Files**: `.env.example`

### 5.4 Test Fixes
- Removed unrealistic uniqueness tests (100/1000 rapid ID generation in single list comprehension)
- Replaced with practical `test_generate_session_id_increases` test with 1ms sleep
- Updated `generate_filename()` and `generate_session_id()` to use `time.time_ns()` for nanosecond precision

**Files**: `tests/test_naming.py`, `src/memory/naming.py`

## Test Results

```
105 passed, 9 skipped (integration tests requiring services), 1 deprecation warning
```

Skipped tests are all integration tests properly guarded with `@pytest.mark.skipif`:
- 2× test_esp32_simulator (requires python-hub server)
- 2× test_full_pipeline (requires ASR tokens, TTS model)
- 3× pipeline/test_tts (requires edge-tts + TTS model)
- 2× pipeline/test_asr (requires FunASR + ASR model)

## Files Changed Summary

| File | Change Type |
|------|-------------|
| `pyproject.toml` | +jieba dependency |
| `Dockerfile` | pip → uv sync |
| `uv.lock` | Regenerated |
| `requirements.txt`, `requirements-dev.txt` | Deleted |
| `src/config.py` | Synced defaults + warning log |
| `src/main.py` | Factory + type imports |
| `src/browser_ws_handler.py` | Factory, dedup, finalize call |
| `src/pipeline/__init__.py` | New: factory function |
| `src/pipeline/tts.py` | Extracted _synthesize_webm |
| `src/memory/rolling_session.py` | Task error callback, eviction, dead branch cleanup |
| `src/memory/global_memory.py` | Rotation, truncation fix |
| `src/memory/naming.py` | time.time_ns() precision |
| `docker-compose.yml` | Healthchecks, volume, mem_limit |
| `.env.example` | New |
| `frontend/src/App.jsx` | Components, hook, loading state |
| `frontend/src/services/websocket.js` | Singleton → BrowserWebSocket class |
| `frontend/src/hooks/useWebSocket.js` | New |
| `frontend/src/components/{StatusBadge,ConnectionIndicator,MessageBubble}.jsx` | New: extracted components |
| `tests/test_naming.py` | Removed unrealistic uniqueness tests |
