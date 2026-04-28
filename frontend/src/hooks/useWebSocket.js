import { useState, useEffect, useRef } from 'react';
import { BrowserWebSocket } from '../services/websocket';

export function useWebSocket(onMessage, onStatusChange) {
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    const ws = new BrowserWebSocket();
    wsRef.current = ws;

    async function init() {
      try {
        await ws.connect(onMessage, onStatusChange);
        setWsConnected(true);
      } catch (err) {
        console.error('WebSocket connection failed:', err);
      }
    }

    init();

    return () => {
      ws.disconnect();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const getWs = () => wsRef.current;

  return { wsConnected, getWs };
}
