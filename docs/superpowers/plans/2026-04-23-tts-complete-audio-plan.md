# TTS Complete Audio Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change TTS from streaming audio chunks to sending complete audio at once to fix base64 encoding corruption issues.

**Architecture:** Backend collects all TTS audio chunks, then sends single `tts_complete` message with full base64 audio. Frontend receives complete audio and plays via AudioContext. No streaming.

**Tech Stack:** Python (websockets, edge-tts, base64), JavaScript (React, AudioContext)

---

## Chunk 1: Backend Protocol - Add build_tts_complete

**Files:**
- Modify: `src/protocol/ws_protocol.py`
- Test: `tests/test_ws_protocol.py` (if exists, or manual test)

- [ ] **Step 1: Add build_tts_complete function to ws_protocol.py**

Read the file first to find the right location to add the function.

```python
def build_tts_complete(data: str, session_id: str, turn_id: int) -> str:
    """Build a TTS complete message with full audio data.

    Args:
        data: Base64 encoded complete WAV audio.
        session_id: Session identifier.
        turn_id: Turn identifier.

    Returns:
        JSON string with tts_complete directive.
    """
    return json.dumps({
        "type": "tts_complete",
        "data": data,
        "session_id": session_id,
        "turn_id": turn_id,
    })
```

Add this function after the existing `build_tts_*` functions (around line 173).

- [ ] **Step 2: Verify the function works**

Run: `python3 -c "from src.protocol.ws_protocol import build_tts_complete; print(build_tts_complete('test123', 'sess1', 1))"`

Expected output: `{"type": "tts_complete", "data": "test123", "session_id": "sess1", "turn_id": 1}`

- [ ] **Step 3: Commit**

```bash
git add src/protocol/ws_protocol.py
git commit -m "feat: add build_tts_complete function"
```

---

## Chunk 2: Backend Handler - Collect and Send Complete Audio

**Files:**
- Modify: `src/browser_ws_handler.py`
- Test: Manual test with frontend

- [ ] **Step 1: Update imports in browser_ws_handler.py**

Read lines 16-24 to see current imports.

Change:
```python
from src.protocol.ws_protocol import (
    build_error,
    build_llm_chunk,
    build_state_directive,
    build_tts_audio,
    build_tts_end,
    build_tts_start,
    build_text,
)
```

To:
```python
from src.protocol.ws_protocol import (
    build_error,
    build_llm_chunk,
    build_state_directive,
    build_tts_complete,
    build_text,
)
```

Remove: `build_tts_audio`, `build_tts_end`, `build_tts_start`
Add: `build_tts_complete`

- [ ] **Step 2: Modify run_llm_to_tts function**

Read lines 175-227 to see the current function.

Current code to replace (lines 215-226):
```python
    await websocket.send(build_tts_start(session_id, turn_id, sample_rate=16000, format="pcm_s16le", channels=1))

    try:
        async for audio_chunk in tts.synthesize(filtered_text):
            b64_audio = base64.b64encode(audio_chunk).decode()
            await websocket.send(build_tts_audio(b64_audio, session_id, turn_id))

        await websocket.send(build_tts_end(session_id, turn_id))

    except Exception as e:
        logger.error(f"TTS error: {e}")
        await websocket.send(build_error(str(e), session_id, turn_id))
```

Replace with:
```python
    try:
        # Collect all audio chunks first
        audio_parts = []
        async for audio_chunk in tts.synthesize(filtered_text):
            audio_parts.append(audio_chunk)

        if audio_parts:
            full_audio = b"".join(audio_parts)
            b64_audio = base64.b64encode(full_audio).decode()
            await websocket.send(build_tts_complete(b64_audio, session_id, turn_id))
        else:
            await websocket.send(build_state_directive(session_id, turn_id, "idle"))

    except Exception as e:
        logger.error(f"TTS error: {e}")
        await websocket.send(build_error(str(e), session_id, turn_id))
```

- [ ] **Step 3: Test the changes**

Restart the container to load new code:
```bash
docker restart python-hub
```

Check logs:
```bash
docker logs python-hub --tail 20
```

- [ ] **Step 4: Commit**

```bash
git add src/browser_ws_handler.py
git commit -m "feat: change TTS to send complete audio instead of streaming chunks"
```

---

## Chunk 3: Frontend - Update Message Handling

**Files:**
- Modify: `frontend/src/App.jsx`
- Test: Browser test with frontend

- [ ] **Step 1: Change fullAudioRef to audioDataRef**

Read App.jsx to find:
- `fullAudioRef` declaration (line ~31)
- How it's used (push, join, clear)

Current:
```javascript
const fullAudioRef = useRef([]);
```

Change to:
```javascript
const audioDataRef = useRef(null);
```

- [ ] **Step 2: Update message handler - remove old cases and add tts_complete**

Find and remove (or comment out):
- `case 'tts_start'`
- `case 'tts_audio'` - remove the push and setHasAudio lines
- `case 'tts_end'` - keep the setStatus and message completion logic, we'll add it to tts_complete

Add new case:
```javascript
case 'tts_complete':
  audioDataRef.current = data.data;
  setHasAudio(true);
  break;
```

**Important:** Move the logic from `tts_end` (setStatus to IDLE, message completion) to this handler or handle via state machine.

- [ ] **Step 3: Update playFullAudio function**

Read the current playFullAudio function (~lines 180-207).

Replace the entire function with:
```javascript
const playFullAudio = useCallback(() => {
  const b64 = audioDataRef.current;
  if (!b64) {
    setHasAudio(false);
    return;
  }

  audioDataRef.current = null;
  setHasAudio(false);

  try {
    const binaryString = atob(b64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    audioContext.decodeAudioData(bytes.buffer, (buffer) => {
      const source = audioContext.createBufferSource();
      source.buffer = buffer;
      source.connect(audioContext.destination);
      source.start();
      source.onended = () => {
        setStatus(STATES.IDLE);
      };
    }, (err) => {
      console.error('[Audio] Decode error:', err);
      setHasAudio(false);
    });
  } catch (err) {
    console.error('[Audio] Playback error:', err.message);
    setHasAudio(false);
  }
}, []);
```

- [ ] **Step 4: Update button onClick**

Find the PLAY AUDIO button. Current likely has:
```javascript
onClick={() => { playFullAudio(); setHasAudio(false); }}
```

Change to:
```javascript
onClick={playFullAudio}
```

Since playFullAudio already handles setHasAudio(false).

- [ ] **Step 5: Clean up unused refs and state**

If `fullAudioRef` is no longer used, remove it.
If `audioChunks` state is only used for old streaming, remove it too.

- [ ] **Step 6: Test in browser**

1. Open frontend at http://localhost:5173
2. Type a message and send
3. Wait for TTS to complete
4. Click PLAY AUDIO
5. Verify audio plays

Check browser console for any errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat: update frontend to handle tts_complete with single audio"
```

---

## Verification Checklist

After all chunks:

- [ ] Backend sends `tts_complete` message (check with docker logs or adding print statements)
- [ ] Frontend receives `tts_complete` and enables PLAY AUDIO button
- [ ] Clicking PLAY AUDIO plays the audio correctly
- [ ] No base64 decoding errors in browser console
- [ ] Status properly transitions to IDLE after playback