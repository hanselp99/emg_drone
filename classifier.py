"""
Hyperdimensional classifier for EMG gesture recognition using torchhd.

Pipeline:
  raw EMG windows → time-domain features → Projection encoding → Centroid classifier
"""

import os
from typing import Optional

import numpy as np
import pandas as pd
import torch
from torchhd import embeddings
from torchhd.models import Centroid
from sklearn.model_selection import train_test_split

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DIMENSIONS  = 10000  # HD vector dimensionality (higher = more accurate, slower)
WINDOW_SIZE = 256    # raw samples per classification window (~128ms at 2000 Hz)
STRIDE      = 128    # window hop — 50% overlap gives one decision per ~64ms
N_CHANNELS  = 4

GESTURES = {
    "rest":          0,  # drone in place
    "clench":        1,  # drone up
    "finger_spread": 2,  # drone down
    "left_tilt":     3,  # drone left
    "right_tilt":    4,  # drone right
    "upward_tilt":   5,  # drone forward
    "downward_tilt": 6,  # drone backward
}
N_CLASSES  = len(GESTURES)
N_FEATURES = N_CHANNELS * 4   # RMS, MAV, VAR, WL per channel → 32 total

CHECKPOINT = "hdc_emg.pt"

# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def extract_features(window: np.ndarray):
    """
    Extract 4 time-domain features per channel from a [WINDOW_SIZE, N_CHANNELS] array.
    Returns a flat [N_FEATURES] vector.
    """
    feats = []
    for ch in range(window.shape[1]):
        x = window[:, ch].astype(np.float64)
        feats.extend([
            np.sqrt(np.mean(x ** 2)),       # RMS
            np.mean(np.abs(x)),             # MAV
            np.var(x),                      # Variance
            np.sum(np.abs(np.diff(x))),     # Waveform Length
        ])
    return np.array(feats, dtype=np.float32)


def windows_from_array(data: np.ndarray):
    """Slide a window over [N_samples, N_channels] → [N_windows, N_FEATURES]."""
    wins = [
        extract_features(data[i : i + WINDOW_SIZE])
        for i in range(0, len(data) - WINDOW_SIZE + 1, STRIDE)
    ]
    return np.stack(wins)


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

def build_dataset() -> tuple[np.ndarray, np.ndarray]:
    """
    Load calibration csv files to obtain both X and y features.
        Load calibration_<gesture>.csv files → (X [N, N_FEATURES], y [N]) arrays.
    """
    X_parts, y_parts = [], []
    for name, label in GESTURES.items():
        path = f"calibration_{name}.csv"
        if not os.path.exists(path):
            print(f"  [skip] {path} not found")
            continue
        data  = pd.read_csv(path).values.astype(np.float32)
        feats = windows_from_array(data)
        X_parts.append(feats)
        y_parts.append(np.full(len(feats), label, dtype=np.int64))
        print(f"  {name:15s}: {len(feats)} windows")

    if not X_parts:
        return np.empty((0, N_FEATURES), dtype=np.float32), np.empty(0, dtype=np.int64)
    return np.concatenate(X_parts), np.concatenate(y_parts)


# ---------------------------------------------------------------------------
# Normalizer  (z-score, no sklearn dependency at inference time)
# ---------------------------------------------------------------------------

class ChannelNorm:
    mean: np.ndarray
    std: np.ndarray

    def fit(self, X: np.ndarray):
        self.mean = X.mean(axis=0)
        self.std  = X.std(axis=0) + 1e-8
        return self

    def transform(self, X: np.ndarray):
        return (X - self.mean) / self.std

    def state_dict(self):
        return {"mean": torch.tensor(self.mean), "std": torch.tensor(self.std)}

    def load_state_dict(self, d: dict):
        self.mean = d["mean"].numpy()
        self.std  = d["std"].numpy()
        return self


# ---------------------------------------------------------------------------
# HDC encoder
# ---------------------------------------------------------------------------

class EMGEncoder(torch.nn.Module):
    """
    Maps a [batch, N_FEATURES] feature tensor into [batch, DIMENSIONS] HD space
    using a fixed random projection (no gradient updates needed).
    """
    def __init__(self, n_features: int = N_FEATURES, dimensions: int = DIMENSIONS):
        super().__init__()
        self.projection = embeddings.Projection(n_features, dimensions)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.projection(x)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train():
    print("Loading calibration data...")
    X, y = build_dataset()

    if len(X) == 0:
        raise FileNotFoundError(
            "No calibration CSVs found. Run stream_data.py first."
        )

    present = np.unique(y)
    print(f"\nDataset  : {len(X)} windows | {X.shape[1]} features | {len(present)} classes found")

    norm = ChannelNorm().fit(X)
    X_n  = norm.transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X_n, y, test_size=0.2, random_state=42, stratify=y
    )

    X_train_t = torch.tensor(X_train, dtype=torch.float32)
    X_test_t  = torch.tensor(X_test,  dtype=torch.float32)
    y_train_t = torch.tensor(y_train, dtype=torch.long)
    y_test_t  = torch.tensor(y_test,  dtype=torch.long)

    # If number of channels changes and N_CHANNELS isn't updated and error will form
    encoder = EMGEncoder()
    model   = Centroid(DIMENSIONS, N_CLASSES)

    # Single-pass training: accumulate class prototypes
    with torch.no_grad():
        model.add(encoder(X_train_t), y_train_t)

    # Evaluate
    with torch.no_grad():
        sims  = model(encoder(X_test_t))           # [N, N_CLASSES] cosine sims
        preds = sims.argmax(dim=-1)
        acc   = (preds == y_test_t).float().mean().item()

    print(f"Test accuracy: {acc * 100:.1f}%")

    torch.save({
        "encoder":   encoder.state_dict(),
        "model":     model.state_dict(),
        "norm":      norm.state_dict(),
        "dimensions": DIMENSIONS,
        "n_features": N_FEATURES,
    }, CHECKPOINT)
    print(f"Saved → {CHECKPOINT}")

    return encoder, model, norm


# ---------------------------------------------------------------------------
# Real-time inference
# ---------------------------------------------------------------------------

class HDCInferencer:
    """
    Sliding-window classifier for live EMG streams.

    Usage:
        clf = HDCInferencer()
        # inside your LSL loop:
        sample, _ = inlet.pull_sample()
        gesture = clf.push_sample(sample)
        if gesture:
            send_drone_command(gesture)
    """

    _label_map = {v: k for k, v in GESTURES.items()}

    def __init__(self):
        ckpt = torch.load(CHECKPOINT, weights_only=True)

        self.norm = ChannelNorm().load_state_dict(ckpt["norm"])

        self.encoder = EMGEncoder(ckpt["n_features"], ckpt["dimensions"])
        self.encoder.load_state_dict(ckpt["encoder"])
        self.encoder.eval()

        self.model = Centroid(ckpt["dimensions"], N_CLASSES)
        self.model.load_state_dict(ckpt["model"])

        self.buffer: list = []

    def push_sample(self, sample: list) -> Optional[tuple[str, float]]:
        """
        Feed one raw EMG sample (list of N_CHANNELS floats).
        Returns (gesture_name, confidence) when a full window is ready, else None.
        Confidence is the cosine similarity of the winning class in [-1, 1].
        """
        self.buffer.append(sample)
        if len(self.buffer) < WINDOW_SIZE:
            return None

        window = np.array(self.buffer[-WINDOW_SIZE:], dtype=np.float32)
        feats  = extract_features(window).reshape(1, -1)
        feats  = self.norm.transform(feats)

        x = torch.tensor(feats, dtype=torch.float32)
        with torch.no_grad():
            sims       = self.model(self.encoder(x))   # [1, N_CLASSES]
            pred       = sims.argmax(dim=-1).item()
            confidence = sims[0, pred].item()

        self.buffer = self.buffer[STRIDE:]
        return self._label_map[pred], confidence


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    train()