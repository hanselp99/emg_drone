import { useCallback, useEffect, useRef, useState } from 'react';
import { useWebSocket } from './hooks/useWebSocket.js';
import EMGStrip, { createEmgBuffer, pushEmgSample } from './components/EMGStrip.jsx';
import CurrentGesture from './components/CurrentGesture.jsx';
import CommandLog from './components/CommandLog.jsx';
import StatusKill from './components/StatusKill.jsx';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8765';
const COMMAND_LOG_LIMIT = 20;
const KILL_PULSE_MS = 2500;

export default function App() {
  // EMG goes through a ref-backed ring buffer, not React state — too fast.
  const emgBufferRef = useRef(createEmgBuffer());

  const [gesture, setGesture]   = useState(null);
  const [commands, setCommands] = useState([]);
  const [status, setStatus]     = useState({ armband: false, pi: false, drone: false, armed: false });
  const [killActive, setKillActive] = useState(false);
  const killTimerRef = useRef(null);

  const onMessage = useCallback((msg) => {
    switch (msg.type) {
      case 'emg':
        if (Array.isArray(msg.channels)) {
          pushEmgSample(emgBufferRef.current, msg.channels);
        }
        break;
      case 'gesture':
        setGesture({ label: msg.label, confidence: msg.confidence, ts: msg.ts });
        break;
      case 'command':
        setCommands((prev) => [
          { cmd: msg.cmd, ts: msg.ts },
          ...prev,
        ].slice(0, COMMAND_LOG_LIMIT));
        if (msg.cmd === 'STOP') triggerKillPulse();
        break;
      case 'status':
        setStatus((prev) => ({ ...prev, ...msg }));
        break;
      default:
        break;
    }
  }, []);

  const { connected, send } = useWebSocket(WS_URL, onMessage);

  const triggerKillPulse = () => {
    setKillActive(true);
    if (killTimerRef.current) clearTimeout(killTimerRef.current);
    killTimerRef.current = setTimeout(() => setKillActive(false), KILL_PULSE_MS);
  };

  const onStop = useCallback(() => {
    send({ type: 'control', action: 'stop' });
    triggerKillPulse();
    // Optimistic local log entry — bridge will also echo a STOP command
    setCommands((prev) => [
      { cmd: 'STOP', ts: Date.now() },
      ...prev,
    ].slice(0, COMMAND_LOG_LIMIT));
  }, [send]);

  const onArmToggle = useCallback(() => {
    send({ type: 'control', action: status.armed ? 'disarm' : 'arm' });
  }, [send, status.armed]);

  // Global spacebar → STOP. Works regardless of focus.
  useEffect(() => {
    const handler = (e) => {
      if (e.code !== 'Space') return;
      // Avoid scrolling and don't let buttons handle it twice
      e.preventDefault();
      onStop();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onStop]);

  return (
    <div className="app">
      <header className="app__header">
        <h1>EMG Drone · Live Demo</h1>
        <span className={`conn ${connected ? 'online' : 'offline'}`}>
          {connected ? `connected · ${WS_URL}` : `offline · retrying ${WS_URL}`}
        </span>
      </header>

      <EMGStrip emgBufferRef={emgBufferRef} stale={!connected} />
      <CurrentGesture gesture={gesture} stale={!connected} />
      <CommandLog commands={commands} stale={!connected} />
      <StatusKill
        status={status}
        killActive={killActive}
        onArmToggle={onArmToggle}
        onStop={onStop}
      />
    </div>
  );
}
