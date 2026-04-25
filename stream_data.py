import numpy as np
import pandas as pd
from pylsl import StreamInlet, resolve_streams
import time
import os

def collect_calibration_data(inlet, gesture_name, target_samples=1000):
    """
    Collects exactly target_samples for a specific hand gesture.
    """
    print(f"\n{'='*50}")
    print(f"PREPARING GESTURE: {gesture_name.upper()}")
    print(f"{'='*50}")
    
    # 3-second countdown to get your hand in position
    for i in range(3, 0, -1):
        print(f"Starting in {i}...", end='\r')
        time.sleep(1)
    
    print("\n>>> RECORDING... HOLD POSITION! <<<")

    inlet.flush()  # discard samples buffered during the countdown
    data = []
    print('Check')

    while len(data) < target_samples:
        # pull_sample() returns [values], timestamp
        sample, timestamp = inlet.pull_sample()
        if sample:
            data.append(sample)
            
            # Simple progress tracker
            if len(data) % 100 == 0:
                print(f"Progress: {len(data)}/{target_samples}", end='\r')

    print('Test')

    # Convert the list of lists into a clean DataFrame
    # Mindrove typically provides 8 EMG channels
    columns = [f'CH_{i+1}' for i in range(len(data[0]))]
    df = pd.DataFrame(data, columns=columns)
    
    # Save the file
    filename = f"calibration_{gesture_name.lower()}.csv"
    df.to_csv(filename, index=False)
    print(f"\n\nSUCCESS: {filename} saved.")
    
    print("RELAX YOUR ARM COMPLETELY...")
    time.sleep(3) # Mandatory rest to avoid muscle fatigue

def main():
    print("Connecting to Mindrove")
    streams = resolve_streams()
    
    if not streams:
        print("Error: No stream found. Check Mindrove Connect App LSL settings.")
        return

    inlet = StreamInlet(streams[0])
    
    gestures = [
        "rest",
        "clench",
        "finger_spread",
        "left_tilt",
        "right_tilt",
        "upward_tilt",
        "downward_tilt",
    ]

    try:
        for g in gestures:
            collect_calibration_data(inlet, g, target_samples=2000)
            
        print("\nAll calibration files are ready for model training.")
        
    except KeyboardInterrupt:
        print("\nProcess stopped by user.")

if __name__ == "__main__":
    main()