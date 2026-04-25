# EMG Drone GUI

Live demo dashboard for the EMG-controlled drone. One purpose: prove
**EMG → gesture → drone command** works in front of an audience. Read-mostly
with one write path (the kill switch).

```
┌────────────────────────────────────────────────────────────┐
│  HEADER · connection status                                │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  LIVE EMG · 4 channels · 5s scrolling window               │
│                                                            │
├──────────────────────────────┬─────────────────────────────┤
│  CURRENT GESTURE             │                             │
│  large label + confidence    │  COMMAND LOG · last 20      │
├──────────────────────────────┤  newest on top              │
│  STATUS · armband / Pi /     │                             │
│  drone · ARM toggle          │                             │
│  big red STOP                │                             │
└──────────────────────────────┴─────────────────────────────┘
```

## Run with mock server (no hardware)

In two terminals from the repo root:

```bash
# 1. install once
pip install websockets
cd GUI && npm install

# 2. terminal A — mock data source
python GUI/mock/mock_server.py

# 3. terminal B — dev server
cd GUI && npm run dev
# open http://localhost:5173
```

You should see all four panels animating: EMG traces scrolling, gesture
flipping every ~3s, commands populating the log, status pills green.

## Run against real hardware (Pi)

On the Pi (or laptop wired to the Mindrove armband + Pi serial):

```bash
pip install websockets
python ws_bridge.py             # opens COM3 by default
# or, if no Pi serial available:
python ws_bridge.py --no-serial
```

In the GUI, point at the Pi's IP via `.env`:

```
VITE_WS_URL=ws://192.168.1.42:8765
```

Then `npm run dev` as above. No code changes needed to swap mock ↔ real.

## Message schema

Server → client:

```json
{ "type": "emg",     "ts": 1714000000000, "channels": [0.12, -0.04, 0.31, 0.08] }
{ "type": "gesture", "ts": 1714000000000, "label": "clench", "confidence": 0.81 }
{ "type": "command", "ts": 1714000000000, "cmd": "clench" }
{ "type": "status",  "armband": true, "pi": true, "drone": true, "armed": false }
```

Client → server:

```json
{ "type": "control", "action": "stop" }
{ "type": "control", "action": "arm" }
{ "type": "control", "action": "disarm" }
```

### Notes on values

- **Gesture labels** come straight from `classifier.py::GESTURES`:
  `rest`, `clench`, `finger_spread`, `left_tilt`, `right_tilt`, `upward_tilt`, `downward_tilt`.
- **Commands** are the same strings (the current `inference.py` writes the
  gesture name straight to serial — `drone_controller.py` is empty). The one
  exception is `STOP`, emitted on a kill-switch press.
- **Confidence** is cosine similarity in `[-1, 1]`, not `[0, 1]`. The bar
  rescales for display; the raw value is shown beneath it. Inference treats
  anything below `0.20` as `rest`.
- **EMG sample rate** on the wire is ~500 Hz (`ws_bridge.py` downsamples the
  raw 2 kHz LSL stream by 4× to keep WebSocket bandwidth sane). The classifier
  still sees the full-rate stream server-side.

## Keyboard

- **Space** anywhere on the page → STOP. Also redirects scroll keys, so don't
  bind it elsewhere.

## Disconnect handling

- WebSocket auto-reconnects every 2 s.
- Header switches to `offline · retrying …`.
- All four panels show an `OFFLINE` overlay until reconnected.

## Stack

- Vite + React 18, plain CSS (no Tailwind, no UI kit, no charting lib).
- EMG strip is a single `<canvas>` driven by a ring buffer + `requestAnimationFrame`.
  React state never re-renders for incoming samples — that path would die at 4 ch × 500 Hz.

## Layout files

```
GUI/
  index.html
  package.json
  vite.config.js
  .env                     # VITE_WS_URL
  src/
    main.jsx
    App.jsx                # WS, state, spacebar handler
    styles.css             # all styling, single file
    hooks/useWebSocket.js  # auto-reconnect
    components/
      EMGStrip.jsx         # canvas + ring buffer
      CurrentGesture.jsx
      CommandLog.jsx
      StatusKill.jsx
  mock/
    mock_server.py         # synthetic data on ws://localhost:8765
```
