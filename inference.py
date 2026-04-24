import sys
import serial
import serial.tools.list_ports
from classifier import HDCInferencer
from pylsl import StreamInlet, resolve_streams

SERIAL_PORT          = "COM3"   # check Device Manager → Ports for the Pi's COM port
BAUD_RATE            = 115200
CONFIDENCE_THRESHOLD = 0.20     # cosine similarity in [-1, 1]; tune after calibration

def main():

    inferencer = HDCInferencer()

    print("Connecting to Mindrove")
    streams = resolve_streams()
    
    if not streams:
        print("Error: No stream found. Check Mindrove Connect App LSL settings.")
        return

    inlet = StreamInlet(streams[0])

    available = [p.device for p in serial.tools.list_ports.comports()]
    if SERIAL_PORT not in available:
        print(f"Port {SERIAL_PORT} not found. Available: {available}")
        sys.exit(1)

    last_sent = None

    with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
        print(f"Serial → {SERIAL_PORT} | threshold={CONFIDENCE_THRESHOLD}")
        print("Running — Ctrl+C to stop.\n")

        try:
            while True:
                sample, _ = inlet.pull_sample()
                result     = inferencer.push_sample(sample)

                if result is None:
                    continue

                gesture, confidence = result

                if confidence < CONFIDENCE_THRESHOLD:
                    gesture = "rest"

                # Only send on gesture change to avoid flooding the Pi
                if gesture != last_sent:
                    ser.write(f"{gesture}\n".encode())
                    last_sent = gesture
                    print(f"{gesture:<15} confidence={confidence:.3f}")

        except KeyboardInterrupt:
            print("\nStopped.")

if __name__ == "__main__":
    main()