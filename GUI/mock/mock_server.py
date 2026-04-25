"""
Mock WebSocket server for the EMG Drone GUI.

Emits the same schema as ws_bridge.py with synthetic but plausible data so
the full UI animates without any hardware:

  - 4-channel EMG, sinusoidal + noise, sent at MOCK_SAMPLE_HZ
  - gesture flips every ~3s through the real label set from classifier.py
  - command emitted whenever gesture changes to a non-rest gesture
  - status pings every 1s with everything green

Inbound control messages (stop/arm/disarm) are honored locally:
  - "stop" flips armed=false and emits a STOP command
  - "arm" / "disarm" toggles status.armed

Run:
  pip install websockets
  python GUI/mock/mock_server.py
"""

import asyncio
import json
import math
import random
import time
from typing import Set

import websockets
from websockets.server import WebSocketServerProtocol


HOST = "0.0.0.0"
PORT = 8765

# Real gesture labels — kept in sync with classifier.py::GESTURES.
# Don't invent new strings; the GUI displays these verbatim.
GESTURES = [
    "rest",
    "clench",
    "finger_spread",
    "left_tilt",
    "right_tilt",
    "upward_tilt",
    "downward_tilt",
]
NON_REST = [g for g in GESTURES if g != "rest"]

MOCK_SAMPLE_HZ   = 500     # downsampled vs real 2kHz, matches what ws_bridge forwards
GESTURE_FLIP_S   = 3.0
STATUS_PERIOD_S  = 1.0


clients: Set[WebSocketServerProtocol] = set()
state = {"armband": True, "pi": True, "drone": True, "armed": False}


async def broadcast(msg: dict) -> None:
    if not clients:
        return
    payload = json.dumps(msg)
    # Snapshot — handler() may mutate `clients` while we're awaiting send,
    # and three coroutines (emg/gesture/status) broadcast concurrently.
    for ws in list(clients):
        try:
            await ws.send(payload)
        except Exception:
            clients.discard(ws)


async def emg_loop() -> None:
    """Synth EMG: per-channel sinusoid + noise, amplitude modulated by current gesture."""
    period = 1.0 / MOCK_SAMPLE_HZ
    t0 = time.time()
    next_tick = t0
    # per-channel base frequencies (Hz) and phases
    freqs  = [3.1, 4.7, 6.3, 5.1]
    phases = [0.0, 0.7, 1.4, 2.1]
    while True:
        now = time.time()
        if now < next_tick:
            await asyncio.sleep(next_tick - now)
        next_tick += period

        t = time.time() - t0
        # amplitude profile: rest = quiet, anything else louder + per-channel skew
        gesture = current_gesture[0]
        base_amp = 0.15 if gesture == "rest" else 1.0
        # bias certain channels per gesture for visual variety
        skew = {
            "clench":         [1.4, 1.0, 0.8, 1.2],
            "finger_spread":  [0.8, 1.4, 1.2, 0.9],
            "left_tilt":      [1.3, 0.9, 0.7, 1.1],
            "right_tilt":     [0.7, 1.1, 1.3, 0.9],
            "upward_tilt":    [1.0, 1.0, 1.4, 1.2],
            "downward_tilt": [1.2, 1.4, 1.0, 0.8],
        }.get(gesture, [1.0] * 4)

        channels = []
        for ch in range(4):
            amp = base_amp * skew[ch]
            sig = (
                amp * math.sin(2 * math.pi * freqs[ch] * t + phases[ch])
                + 0.35 * amp * math.sin(2 * math.pi * (freqs[ch] * 3.7) * t)
                + random.gauss(0, 0.12)
            )
            channels.append(sig)

        await broadcast({
            "type": "emg",
            "ts": int(time.time() * 1000),
            "channels": channels,
        })


# Mutable holder so emg_loop sees gesture changes without locks.
current_gesture = ["rest"]


async def gesture_loop() -> None:
    """Flip gestures every GESTURE_FLIP_S; emit a command on every change to a non-rest gesture."""
    last_emitted = "rest"
    while True:
        # Hold rest briefly between active gestures for realism
        for g in [random.choice(NON_REST), "rest"]:
            current_gesture[0] = g
            # Stream confidence over the hold
            steps = max(1, int(GESTURE_FLIP_S * 5))   # ~5 Hz like classifier rate
            for _ in range(steps):
                conf_base = 0.75 if g != "rest" else 0.10
                conf = max(-0.2, min(0.99, conf_base + random.gauss(0, 0.05)))
                await broadcast({
                    "type": "gesture",
                    "ts": int(time.time() * 1000),
                    "label": g,
                    "confidence": conf,
                })
                await asyncio.sleep(GESTURE_FLIP_S / steps)

            if g != last_emitted and g != "rest" and state["armed"]:
                await broadcast({
                    "type": "command",
                    "ts": int(time.time() * 1000),
                    "cmd": g,
                })
                last_emitted = g
            if g == "rest":
                last_emitted = "rest"


async def status_loop() -> None:
    while True:
        await broadcast({"type": "status", **state})
        await asyncio.sleep(STATUS_PERIOD_S)


async def handler(ws: WebSocketServerProtocol) -> None:
    clients.add(ws)
    try:
        await ws.send(json.dumps({"type": "status", **state}))
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") != "control":
                continue
            action = msg.get("action")
            if action == "stop":
                state["armed"] = False
                await broadcast({
                    "type": "command",
                    "ts": int(time.time() * 1000),
                    "cmd": "STOP",
                })
            elif action == "arm":
                state["armed"] = True
            elif action == "disarm":
                state["armed"] = False
            await broadcast({"type": "status", **state})
    except websockets.ConnectionClosed:
        pass
    finally:
        clients.discard(ws)


async def main() -> None:
    print(f"mock_server listening on ws://{HOST}:{PORT}")
    async with websockets.serve(handler, HOST, PORT):
        await asyncio.gather(emg_loop(), gesture_loop(), status_loop())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
