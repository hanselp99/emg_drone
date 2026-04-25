import { useEffect, useRef, useState } from 'react';

const RECONNECT_MS = 2000;

/**
 * Auto-reconnecting WebSocket hook.
 *
 *   onMessage         — called for each parsed JSON frame (use a ref-stable fn)
 *   returns { connected, send }
 */
export function useWebSocket(url, onMessage) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const onMessageRef = useRef(onMessage);
  const closedByUserRef = useRef(false);

  // keep latest handler without re-opening the socket
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

  useEffect(() => {
    closedByUserRef.current = false;

    const connect = () => {
      let ws;
      try {
        ws = new WebSocket(url);
      } catch {
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closedByUserRef.current) scheduleReconnect();
      };
      ws.onerror = () => { /* close handler will fire */ };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          onMessageRef.current?.(msg);
        } catch { /* ignore malformed frames */ }
      };
    };

    const scheduleReconnect = () => {
      if (reconnectTimerRef.current) return;
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, RECONNECT_MS);
    };

    connect();

    return () => {
      closedByUserRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, [url]);

  const send = (obj) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  };

  return { connected, send };
}
