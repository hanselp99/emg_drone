import { useEffect, useRef } from 'react';

const N_CHANNELS = 4;
const WINDOW_SECONDS = 5;
const SAMPLE_RATE_HZ = 500;            // post-bridge downsample (raw is ~2kHz)
const BUF_LEN = WINDOW_SECONDS * SAMPLE_RATE_HZ;
const ENVELOPE_ALPHA = 0.05;           // EMA for rectified envelope

const COLORS = ['#4ea1ff', '#3ddc97', '#f5a524', '#c084fc'];
const ENVELOPE_COLORS = ['#4ea1ff80', '#3ddc9780', '#f5a52480', '#c084fc80'];

/**
 * EMGStrip
 *
 * Receives an `emgBufferRef` — a ref to an object with shape:
 *   { channels: Float32Array[N_CHANNELS][BUF_LEN], envelope: same, head, total }
 * Drawn imperatively at requestAnimationFrame; React state never re-renders
 * for incoming samples (would die at 500Hz × 4ch).
 */
export default function EMGStrip({ emgBufferRef, stale }) {
  const canvasRef = useRef(null);
  const rafRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const draw = () => {
      const buf = emgBufferRef.current;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;

      ctx.clearRect(0, 0, w, h);

      // 4 horizontal lanes
      const laneH = h / N_CHANNELS;

      for (let ch = 0; ch < N_CHANNELS; ch++) {
        const yMid = laneH * ch + laneH / 2;

        // Lane separator
        ctx.strokeStyle = '#232b38';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, laneH * (ch + 1));
        ctx.lineTo(w, laneH * (ch + 1));
        ctx.stroke();

        // Channel label
        ctx.fillStyle = '#8b97a8';
        ctx.font = '11px ui-monospace, Menlo, monospace';
        ctx.fillText(`CH ${ch + 1}`, 8, laneH * ch + 14);

        const data = buf.channels[ch];
        const env  = buf.envelope[ch];

        // Compute auto-scale on the visible window
        let maxAbs = 1e-6;
        for (let i = 0; i < BUF_LEN; i++) {
          const v = Math.abs(data[i]);
          if (v > maxAbs) maxAbs = v;
        }
        const scale = (laneH * 0.42) / maxAbs;

        // Rectified envelope (filled)
        ctx.fillStyle = ENVELOPE_COLORS[ch];
        ctx.beginPath();
        ctx.moveTo(0, yMid);
        for (let i = 0; i < BUF_LEN; i++) {
          const idx = (buf.head + i) % BUF_LEN;
          const x = (i / (BUF_LEN - 1)) * w;
          const y = yMid - env[idx] * scale;
          ctx.lineTo(x, y);
        }
        ctx.lineTo(w, yMid);
        ctx.closePath();
        ctx.fill();

        // Raw trace
        ctx.strokeStyle = COLORS[ch];
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let i = 0; i < BUF_LEN; i++) {
          const idx = (buf.head + i) % BUF_LEN;
          const x = (i / (BUF_LEN - 1)) * w;
          const y = yMid - data[idx] * scale;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(rafRef.current);
      ro.disconnect();
    };
  }, [emgBufferRef]);

  return (
    <section className={`panel emg ${stale ? 'stale' : ''}`}>
      <h2 className="panel__title">Live EMG · 4ch · {WINDOW_SECONDS}s window</h2>
      <div className="emg__canvas-wrap">
        <canvas ref={canvasRef} className="emg__canvas" />
        <div className="emg__legend">raw + rectified envelope · auto-scale</div>
      </div>
    </section>
  );
}

/**
 * Helper used by App: create an empty buffer and a push() function.
 * Kept here so EMGStrip owns the buffer shape contract.
 */
export function createEmgBuffer() {
  return {
    channels: Array.from({ length: N_CHANNELS }, () => new Float32Array(BUF_LEN)),
    envelope: Array.from({ length: N_CHANNELS }, () => new Float32Array(BUF_LEN)),
    head: 0,    // index of oldest sample (next slot to overwrite)
    total: 0,
  };
}

export function pushEmgSample(buf, channels) {
  const i = buf.head;
  for (let ch = 0; ch < N_CHANNELS; ch++) {
    const v = channels[ch] ?? 0;
    buf.channels[ch][i] = v;
    const prev = buf.envelope[ch][(i - 1 + BUF_LEN) % BUF_LEN];
    const rect = Math.abs(v);
    buf.envelope[ch][i] = prev + ENVELOPE_ALPHA * (rect - prev);
  }
  buf.head = (i + 1) % BUF_LEN;
  buf.total++;
}
