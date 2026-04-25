from pylsl import StreamInlet, resolve_streams
from classifier import HDCInferencer

CONFIDENCE_THRESHOLD = 0.20

clf     = HDCInferencer()
streams = resolve_streams()
if not streams:
    raise RuntimeError("No LSL stream found. Is the Mindrove app running?")
inlet = StreamInlet(streams[0])

print("Classifying live — Ctrl+C to stop\n")
while True:
    sample, _ = inlet.pull_sample()
    result = clf.push_sample(sample)
    if result:
        gesture, confidence = result
        label = gesture if confidence >= CONFIDENCE_THRESHOLD else f"(low conf) {gesture}"
        print(f"{label:<25} {confidence:.3f}")
