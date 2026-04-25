"""
WebSocket bridge between the live EMG pipeline and the GUI.

Runs `inference.run_inference` in a background thread and broadcasts
JSON messages to all connected WebSocket clients on ws://0.0.0.0:8765.

Outbound message schema (server → client):
  {"type": "emg",     "ts": <ms>, "channels": [f, f, f, f]}
  {"type": "gesture", "ts": <ms>, "label": "<gesture>", "confidence": <float>}
  {"type": "command", "ts": <ms>, "cmd":   "<gesture>"}
  {"type": "status",  "armband": <bool>, "pi": <bool>, "drone": <bool>, "armed": <bool>}

Inbound message schema (client → server):
  {"type": "control", "action": "stop" | "arm" | "disarm"}

Run:
  pip install websockets
  python ws_bridge.py                       # talk to real hardware via inference.py
  python ws_bridge.py --no-serial           # skip opening the Pi serial port
  python ws_bridge.py --port 8765 --host 0.0.0.0
"""

import argparse
import asyncio
import json
import threading
import time
from typing import Set

import websockets
from websockets.server import WebSocketServerProtocol


HOST_DEFAULT = "0.0.0.0"
PORT_DEFAULT = 8765
EMG_DOWNSAMPLE = 4   # forward 1 of every N raw samples to keep WS bandwidth sane


class Bridge:
    def __init__(self, serial_writer: bool = True):
        self.clients: Set[WebSocketServerProtocol] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.stop_event = threading.Event()
        self.serial_writer = serial_writer
        self._emg_counter = 0

        # Authoritative status — updated by inference callbacks and control
        # messages, broadcast on change.
        self.status = {"armband": False, "pi": False, "drone": False, "armed": False}

    # -- broadcast helpers ---------------------------------------------------

    def _schedule_broadcast(self, message: dict) -> None:
        """Thread-safe send from the inference thread into the asyncio loop."""
        if self.loop is None:
            return
        payload = json.dumps(message)
        asyncio.run_coroutine_threadsafe(self._broadcast(payload), self.loop)

    async def _broadcast(self, payload: str) -> None:
        if not self.clients:
            return
        # Snapshot — handler() may mutate `clients` while we're awaiting send,
        # and inference-thread callbacks schedule broadcasts concurrently.
        for ws in list(self.clients):
            try:
                await ws.send(payload)
            except Exception:
                self.clients.discard(ws)

    # -- inference callbacks (run on inference thread) -----------------------

    def on_emg(self, sample: list) -> None:
        self._emg_counter += 1
        if self._emg_counter % EMG_DOWNSAMPLE != 0:
            return
        # classifier expects 4 channels; truncate if armband sends more
        channels = [float(x) for x in sample[:4]]
        self._schedule_broadcast({
            "type": "emg",
            "ts": int(time.time() * 1000),
            "channels": channels,
        })

    def on_gesture(self, label: str, confidence: float) -> None:
        self._schedule_broadcast({
            "type": "gesture",
            "ts": int(time.time() * 1000),
            "label": label,
            "confidence": float(confidence),
        })

    def on_command(self, cmd: str) -> None:
        self._schedule_broadcast({
            "type": "command",
            "ts": int(time.time() * 1000),
            "cmd": cmd,
        })

    def on_status(self, partial: dict) -> None:
        self.status.update(partial)
        self._schedule_broadcast({"type": "status", **self.status})

    # -- inbound control -----------------------------------------------------

    async def handle_control(self, msg: dict) -> None:
        action = msg.get("action")
        if action == "stop":
            # Hard kill: disarm and signal inference loop to exit.
            # When drone_controller.py grows a real hard-disarm/land path,
            # call it here before flipping the flag.
            self.status["armed"] = False
            self.stop_event.set()
            self._schedule_broadcast({"type": "command", "ts": int(time.time() * 1000), "cmd": "STOP"})
        elif action == "arm":
            self.status["armed"] = True
        elif action == "disarm":
            self.status["armed"] = False
        self._schedule_broadcast({"type": "status", **self.status})

    # -- websocket lifecycle -------------------------------------------------

    async def handler(self, ws: WebSocketServerProtocol) -> None:
        self.clients.add(ws)
        try:
            await ws.send(json.dumps({"type": "status", **self.status}))
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "control":
                    await self.handle_control(msg)
        except websockets.ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)

    # -- entrypoint ----------------------------------------------------------

    def start_inference_thread(self) -> threading.Thread:
        from inference import run_inference

        def target():
            try:
                run_inference(
                    on_emg=self.on_emg,
                    on_gesture=self.on_gesture,
                    on_command=self.on_command,
                    on_status=self.on_status,
                    stop_event=self.stop_event,
                    serial_writer=self.serial_writer,
                )
            except Exception as e:
                print(f"[inference] crashed: {e}")
                self.on_status({"armband": False, "pi": False, "drone": False})

        t = threading.Thread(target=target, name="inference", daemon=True)
        t.start()
        return t

    async def serve(self, host: str, port: int) -> None:
        self.loop = asyncio.get_running_loop()
        self.start_inference_thread()
        print(f"ws_bridge listening on ws://{host}:{port}")
        async with websockets.serve(self.handler, host, port):
            await asyncio.Future()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=HOST_DEFAULT)
    p.add_argument("--port", type=int, default=PORT_DEFAULT)
    p.add_argument("--no-serial", action="store_true",
                   help="don't open the Pi serial port (useful when running off-device)")
    args = p.parse_args()

    bridge = Bridge(serial_writer=not args.no_serial)
    try:
        asyncio.run(bridge.serve(args.host, args.port))
    except KeyboardInterrupt:
        bridge.stop_event.set()


if __name__ == "__main__":
    main()
