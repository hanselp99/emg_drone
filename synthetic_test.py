"""
Full synthetic pipeline test — no armband required.

Loads real calibration CSVs to learn per-channel amplitude statistics,
generates synthetic windows from those distributions, trains the HDC model
in memory, then tests it through HDCInferencer one sample at a time.
"""

import os
import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import train_test_split

from classifier import (
    EMGEncoder, ChannelNorm, WINDOW_SIZE, DIMENSIONS,
    N_CLASSES, GESTURES, extract_features, HDCInferencer
)
from torchhd.models import Centroid

N_TRAIN_WIN          = 60    # synthetic windows to generate per gesture
CONFIDENCE_THRESHOLD = 0.20


# ---------------------------------------------------------------------------
# Learn per-channel statistics from real calibration CSVs
# ---------------------------------------------------------------------------

def load_profiles() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """
    Read each calibration_<gesture>.csv and return per-gesture
    (mean, std) arrays of shape [N_CHANNELS].
    """
    profiles = {}
    missing  = []

    for name in GESTURES:
        path = f"calibration_{name}.csv"
        if not os.path.exists(path):
            missing.append(name)
            continue

        data = pd.read_csv(path).values.astype(np.float32)
        profiles[name] = (data.mean(axis=0), data.std(axis=0) + 1e-8)
        print(f"  {name:<16}: {len(data)} samples | "
              f"mean amplitude {np.abs(data).mean():.2f}")

    if missing:
        print(f"\n[skip] No CSV found for: {', '.join(missing)}")

    return profiles


# ---------------------------------------------------------------------------
# Synthetic window generation
# ---------------------------------------------------------------------------

def make_window(mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    """
    Sample one [WINDOW_SIZE, N_CHANNELS] window from N(mean, std) per channel.
    This matches the observed amplitude distribution of the real gesture.
    """
    n_channels = len(mean)
    noise      = np.random.randn(WINDOW_SIZE, n_channels)
    return (noise * std + mean).astype(np.float32)


# ---------------------------------------------------------------------------
# Dataset + training
# ---------------------------------------------------------------------------

def build_dataset(profiles: dict) -> tuple[np.ndarray, np.ndarray]:
    X_parts, y_parts = [], []
    for name, label in GESTURES.items():
        if name not in profiles:
            continue
        mean, std = profiles[name]
        windows = [extract_features(make_window(mean, std)) for _ in range(N_TRAIN_WIN)]
        X_parts.append(np.stack(windows))
        y_parts.append(np.full(N_TRAIN_WIN, label, dtype=np.int64))
    return np.concatenate(X_parts), np.concatenate(y_parts)


def train_in_memory(profiles: dict):
    X, y = build_dataset(profiles)

    norm = ChannelNorm().fit(X)
    X_n  = norm.transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X_n, y, test_size=0.2, random_state=42, stratify=y
    )

    X_train_t = torch.tensor(X_train, dtype=torch.float32)
    X_test_t  = torch.tensor(X_test,  dtype=torch.float32)
    y_train_t = torch.tensor(y_train, dtype=torch.long)
    y_test_t  = torch.tensor(y_test,  dtype=torch.long)

    encoder = EMGEncoder(n_features=X.shape[1])
    model   = Centroid(DIMENSIONS, N_CLASSES)

    with torch.no_grad():
        model.add(encoder(X_train_t), y_train_t)

    with torch.no_grad():
        preds = model(encoder(X_test_t)).argmax(dim=-1)
        acc   = (preds == y_test_t).float().mean().item()

    print(f"Hold-out accuracy on synthetic data: {acc * 100:.1f}%\n")
    return encoder, model, norm


# ---------------------------------------------------------------------------
# Inference test
# ---------------------------------------------------------------------------

def run():
    print("Loading calibration statistics...\n")
    profiles = load_profiles()

    if not profiles:
        print("No calibration CSVs found. Run stream_data.py first.")
        return

    print(f"\nGenerating {N_TRAIN_WIN} synthetic windows per gesture and training...\n")
    encoder, model, norm = train_in_memory(profiles)

    # Patch HDCInferencer to use the in-memory synthetic model
    clf            = HDCInferencer.__new__(HDCInferencer)
    clf.encoder    = encoder
    clf.model      = model
    clf.norm       = norm
    clf.buffer     = []
    clf._label_map = {v: k for k, v in GESTURES.items()}
    clf.encoder.eval()

    print(f"{'Simulated':<16} {'Predicted':<16} {'Confidence':>10}  Match")
    print("-" * 55)

    correct, total = 0, 0

    for gesture_name in profiles:
        mean, std = profiles[gesture_name]
        samples   = make_window(mean, std).tolist()

        clf.buffer = []
        predictions = []
        for sample in samples:
            result = clf.push_sample(sample)
            if result is not None:
                predictions.append(result)

        if not predictions:
            print(f"{gesture_name:<16} {'no prediction':<16}        --     --")
            continue

        predicted, confidence = predictions[-1]
        label_str = predicted if confidence >= CONFIDENCE_THRESHOLD else "low conf"
        match     = "OK" if predicted == gesture_name else "--"

        print(f"{gesture_name:<16} {label_str:<16} {confidence:>10.3f}  {match}")
        total += 1
        if predicted == gesture_name and confidence >= CONFIDENCE_THRESHOLD:
            correct += 1

    print("-" * 55)
    if total:
        print(f"Result: {correct}/{total} correct ({100*correct/total:.0f}%)")
    print("\nAccuracy here reflects how separable your real gesture recordings are.")


if __name__ == "__main__":
    run()
