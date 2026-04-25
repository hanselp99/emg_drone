# emg_drone

EMG-armband-controlled drone. Mindrove armband → LSL → HDC classifier → serial → Pi → drone.

## Layout

```
stream_data.py     # collect calibration CSVs (one per gesture) from LSL
classifier.py      # HDC classifier: train(), HDCInferencer for live use
inference.py       # live loop: LSL → classifier → serial out (to Pi)
drone_controller.py  # stub — Pi-side drone command handling
ws_bridge.py       # WebSocket bridge: taps inference and broadcasts to GUI
GUI/               # React (Vite) demo dashboard — see GUI/README.md
```

## Live demo

The GUI talks to a WebSocket server. Run **one** of:

- `python ws_bridge.py` — real hardware (Mindrove + Pi serial). Add `--no-serial`
  to skip opening the Pi serial port.
- `python GUI/mock/mock_server.py` — synthetic data, no hardware needed.

Then in `GUI/`:

```bash
npm install
npm run dev
```

See [`GUI/README.md`](GUI/README.md) for the message schema and full setup.

## Dependencies

- Python: `numpy pandas torch torchhd scikit-learn pylsl pyserial websockets`
- Node (in `GUI/`): see `GUI/package.json`
