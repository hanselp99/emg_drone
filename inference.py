import sys
import threading
from typing import Callable, Optional

import serial
import serial.tools.list_ports
from classifier import HDCInferencer
from pylsl import StreamInlet, resolve_streams

SERIAL_PORT          = "COM3"   # check Device Manager → Ports for the Pi's COM port
BAUD_RATE            = 115200
CONFIDENCE_THRESHOLD = 0.20     # cosine similarity in [-1, 1]; tune after calibration


# ---------------------------------------------------------------------------
# Hookable runner
#
# Added so ws_bridge.py can tap the live EMG stream, classifier output, and
# command stream without monkey-patching this module. Pass any subset of
# callbacks; pass `serial_writer=False` to skip opening a serial port (useful
# when the bridge runs on a host that isn't wired to the Pi).
# ---------------------------------------------------------------------------

def run_inference(
    on_emg:        Optional[Callable[[list], None]]               = None,
    on_gesture:    Optional[Callable[[str, float], None]]         = None,
    on_command:    Optional[Callable[[str], None]]                = None,
    on_status:     Optional[Callable[[dict], None]]               = None,
    stop_event:    Optional[threading.Event]                      = None,
    serial_writer: bool                                            = True,
    serial_port:   str                                             = SERIAL_PORT,
    baud:          int                                             = BAUD_RATE,
    threshold:     float                                           = CONFIDENCE_THRESHOLD,
) -> None:
    """
    Run the live EMG → gesture → command loop with optional callbacks.

    Callbacks (all optional, all invoked from this thread):
      on_emg(sample)                   — raw EMG sample (list[float])
      on_gesture(label, confidence)    — every classifier window
      on_command(cmd)                  — when a new command is dispatched
      on_status(dict)                  — connection state changes
                                         keys: armband (bool), pi (bool), drone (bool)

    Caller may set stop_event to interrupt the loop cleanly.
    """
    inferencer = HDCInferencer()

    if on_status:
        on_status({"armband": False, "pi": False, "drone": False})

    print("Connecting to Mindrove")
    streams = resolve_streams()
    if not streams:
        print("Error: No stream found. Check Mindrove Connect App LSL settings.")
        if on_status:
            on_status({"armband": False})
        return
    inlet = StreamInlet(streams[0])
    if on_status:
        on_status({"armband": True})

    ser = None
    if serial_writer:
        available = [p.device for p in serial.tools.list_ports.comports()]
        if serial_port not in available:
            print(f"Port {serial_port} not found. Available: {available}")
            if on_status:
                on_status({"pi": False, "drone": False})
            sys.exit(1)
        ser = serial.Serial(serial_port, baud, timeout=1)
        if on_status:
            on_status({"pi": True, "drone": True})
        print(f"Serial → {serial_port} | threshold={threshold}")

    print("Running — Ctrl+C to stop.\n")
    last_sent = None

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break

            sample, _ = inlet.pull_sample()
            if on_emg and sample:
                on_emg(sample)

            result = inferencer.push_sample(sample)
            if result is None:
                continue

            gesture, confidence = result
            if on_gesture:
                on_gesture(gesture, confidence)

            if confidence < threshold:
                gesture = "rest"

            if gesture != last_sent:
                if ser is not None:
                    ser.write(f"{gesture}\n".encode())
                last_sent = gesture
                if on_command:
                    on_command(gesture)
                print(f"{gesture:<15} confidence={confidence:.3f}")

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if ser is not None:
            ser.close()


def main():
    run_inference()


if __name__ == "__main__":
    main()
