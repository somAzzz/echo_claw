// Always use plain WebSocket since backend doesn't have TLS
const WS_URL = `ws://${window.location.hostname}:8767`;
const API_URL = `http://${window.location.hostname}:8766`;

export class BrowserWebSocket {
  constructor() {
    this._ws = null;
    this._reconnectAttempts = 0;
    this._maxReconnectAttempts = 5;
    this._reconnectDelay = 1000;
    this._onMessage = null;
    this._onStatusChange = null;
    this._reconnectTimer = null;
  }

  connect(onMessage, onStatusChange) {
    this._onMessage = onMessage;
    this._onStatusChange = onStatusChange;
    return this._connectInternal();
  }

  _connectInternal() {
    return new Promise((resolve, reject) => {
      try {
        this._ws = new WebSocket(WS_URL);

        this._ws.onopen = () => {
          console.log('WebSocket connected');
          this._reconnectAttempts = 0;
          resolve();
        };

        this._ws.onclose = (event) => {
          console.log('WebSocket closed', event.code, event.reason);
          this._tryReconnect();
        };

        this._ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          reject(error);
        };

        this._ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'state') {
              this._onStatusChange?.(data.state);
            } else {
              this._onMessage?.(data);
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

  _tryReconnect() {
    if (this._reconnectAttempts < this._maxReconnectAttempts) {
      const delay = this._reconnectDelay * Math.pow(2, this._reconnectAttempts);
      console.log(`Reconnecting in ${delay}ms...`);
      this._reconnectTimer = setTimeout(() => {
        this._reconnectAttempts++;
        this._connectInternal().catch(() => {});
      }, delay);
    }
  }

  _send(message) {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(message));
      return true;
    }
    console.error('WebSocket not connected, readyState:', this._ws ? this._ws.readyState : 'ws is null');
    return false;
  }

  sendAudioChunk(audioData) {
    return this._send({
      type: 'audio_chunk',
      data: audioData,
    });
  }

  sendAudioStart(sessionId) {
    return this._send({
      type: 'audio_start',
      session_id: sessionId || 'browser-session',
      turn_id: Date.now(),
    });
  }

  sendAudioEnd() {
    return this._send({ type: 'audio_end' });
  }

  sendCancel() {
    return this._send({ type: 'cancel' });
  }

  sendSessionEnd(sessionId) {
    const data = new URLSearchParams({ session_id: sessionId });
    navigator.sendBeacon(`${API_URL}/api/session/end?${data.toString()}`);
    return true;
  }

  sendTextInput(text, promptContent = '', sessionId = 'browser-session') {
    return this._send({
      type: 'text_input',
      text: text,
      prompt: promptContent,
      session_id: sessionId,
    });
  }

  disconnect() {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
  }

  get readyState() {
    return this._ws ? this._ws.readyState : WebSocket.CLOSED;
  }
}
