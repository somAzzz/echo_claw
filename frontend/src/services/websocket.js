// Always use plain WebSocket since backend doesn't have TLS
const WS_URL = `ws://${window.location.hostname}:8767`;

let ws = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY = 1000;

export function connect(onMessage, onStatusChange) {
  return new Promise((resolve, reject) => {
    try {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        console.log('WebSocket connected');
        reconnectAttempts = 0;
        resolve();
      };

      ws.onclose = (event) => {
        console.log('WebSocket closed', event.code, event.reason);
        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          const delay = RECONNECT_DELAY * Math.pow(2, reconnectAttempts);
          console.log(`Reconnecting in ${delay}ms...`);
          setTimeout(() => {
            reconnectAttempts++;
            connect(onMessage, onStatusChange);
          }, delay);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        reject(error);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'state') {
            onStatusChange(data.state);
          } else {
            onMessage(data);
          }
        } catch (e) {
          console.error('Failed to parse message:', e);
        }
      };
    } catch (error) {
      reject(error);
    }
  });
}

export function sendMessage(message) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
    return true;
  }
  console.error('WebSocket not connected, readyState:', ws ? ws.readyState : 'ws is null');
  return false;
}

export function sendAudioChunk(audioData) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'audio_chunk',
      data: audioData,
    }));
    return true;
  }
  return false;
}

export function sendAudioStart(sessionId) {
  return sendMessage({
    type: 'audio_start',
    session_id: sessionId || 'browser-session',
    turn_id: Date.now(),
  });
}

export function sendAudioEnd() {
  return sendMessage({ type: 'audio_end' });
}

export function sendCancel() {
  return sendMessage({ type: 'cancel' });
}

export function sendTextInput(text, promptContent = '') {
  return sendMessage({
    type: 'text_input',
    text: text,
    prompt: promptContent,
  });
}

export function disconnect() {
  if (ws) {
    ws.close();
    ws = null;
  }
}

export function getReadyState() {
  return ws ? ws.readyState : WebSocket.CLOSED;
}