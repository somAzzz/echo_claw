# TTS Complete Audio Design

## Overview

Change TTS from streaming audio chunks to sending complete audio at once. Backend waits for TTS to generate complete audio, then sends as single base64 block to frontend, which decodes and plays using AudioContext.

## Problem

Current streaming TTS with base64-encoded audio chunks causes InvalidCharacterError in browser:
- Frontend receives corrupted base64 like "UklGRv////9XQVZF..." which fails `atob()`
- Root cause: sending audio across WebSocket in multiple separate messages causes encoding/corruption issues

Note: The TTS service (edge-tts) already buffers the **entire** audio in memory before yielding chunks (see `src/pipeline/tts.py` lines 76-79). The problem is not TTS streaming, but WebSocket multi-message transmission of partial base64 data.

## Solution

Send complete audio as single message after TTS finishes.

## Data Flow

```
User Input → ASR → LLM → TTS (wait for complete) → WebSocket (single message) → Frontend Play
```

## WebSocket Protocol

### Messages Removed
- `tts_start` - no longer needed
- `tts_audio` - streaming not used (multiple WebSocket messages)
- `tts_end` - no longer needed

### Messages Added

**tts_complete** (server → client):
```json
{
  "type": "tts_complete",
  "data": "<base64 complete WAV audio>",
  "session_id": "abc123",
  "turn_id": 1234567890
}
```

**error** (server → client, on TTS failure):
```json
{
  "type": "error",
  "message": "TTS synthesis failed",
  "session_id": "abc123",
  "turn_id": 1234567890
}
```

## Backend Changes

### browser_ws_handler.py

**Import changes** (lines 16-24):
```python
from src.protocol.ws_protocol import (
    build_error,
    build_llm_chunk,
    build_state_directive,
    build_tts_complete,  # NEW: added
    build_text,
)
# Removed: build_tts_audio, build_tts_end, build_tts_start
```

**Modify `run_llm_to_tts` function** (lines 175-227):

Before (streaming):
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

After (complete audio):
```python
try:
    # Collect all audio chunks
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

### ws_protocol.py

Add `build_tts_complete` function after existing build functions (around line 173):
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

## Frontend Changes

### App.jsx - State

**Current state:**
- `fullAudioRef: React.MutableRefObject<string[]>` - array of base64 chunks

**New state:**
- `audioDataRef: React.MutableRefObject<string | null>` - single complete audio or null

Transition:
- Remove: `fullAudioRef.current = []` initialization
- Remove: `fullAudioRef.current.push(data.data)` in tts_audio handler
- Remove: `fullAudioRef.current.join('')` concatenation
- Add: `audioDataRef.current = null` initialization
- Add: `audioDataRef.current = data.data` in tts_complete handler

### App.jsx - Message Handler

**Remove cases:**
- `case 'tts_audio'` - streaming not used
- `case 'tts_start'` - not needed
- `case 'tts_end'` - not needed (logic moved to tts_complete)

**Add case:**
```javascript
case 'tts_complete':
  audioDataRef.current = data.data;  // Store complete audio base64
  setHasAudio(true);
  break;
```

**Important:** The `tts_end` handler previously did:
```javascript
setStatus(STATES.IDLE);
setMessages((prev) =>
  prev.map((m, i) =>
    i === prev.length - 1 && m.role === 'assistant' ? { ...m, complete: true } : m
  )
);
```

This logic should be moved to `tts_complete` handler or handled via state machine transitions.

### App.jsx - playFullAudio

Simplify to use single audio data:
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

Note: Button should just call `playFullAudio` (not `playFullAudio; setHasAudio(false)` since playFullAudio already handles it).

### websocket.js

No changes needed. `sendAudioEnd` sends `{ type: 'audio_end' }` for browser→server audio upload control, which is unrelated to TTS changes (server→browser).

## Behavior

1. **New message arrives** → auto-clear previous audio (audioDataRef.current = null), reset PLAY AUDIO button via setHasAudio(false)
2. **TTS processing** → status shows "processing", user waits
3. **TTS complete** → receive complete audio via tts_complete, enable PLAY AUDIO button (setHasAudio(true))
4. **User clicks PLAY AUDIO** → playFullAudio plays audio and calls setHasAudio(false) at end
5. **Playback done** → source.onended callback sets status to IDLE; button re-enables only when new audio arrives

## Files to Modify

1. `src/browser_ws_handler.py`
   - Update imports: remove build_tts_audio, build_tts_end, build_tts_start; add build_tts_complete
   - Modify run_llm_to_tts to collect audio chunks and send single tts_complete message

2. `src/protocol/ws_protocol.py`
   - Add build_tts_complete function

3. `frontend/src/App.jsx`
   - Change fullAudioRef to audioDataRef (string | null)
   - Remove tts_audio, tts_start, tts_end handlers
   - Add tts_complete handler
   - Move tts_end logic (setStatus, message completion) to appropriate handler
   - Update playFullAudio to use single audio data
   - Simplify button onClick to just playFullAudio