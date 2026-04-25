/**
 * Renders the currently classified gesture + confidence bar.
 *
 * Confidence from the HDC classifier is cosine similarity in [-1, 1].
 * We clamp+scale to [0, 1] for the bar but show the raw value too.
 */
export default function CurrentGesture({ gesture, stale }) {
  const isIdle = !gesture || gesture.label === 'rest';
  const label  = !gesture ? '—' : gesture.label;
  const conf   = gesture?.confidence ?? 0;
  const pct    = Math.max(0, Math.min(1, (conf + 1) / 2));

  return (
    <section className={`panel gesture ${stale ? 'stale' : ''}`}>
      <h2 className="panel__title">Current Gesture</h2>
      <div className="gesture__body">
        <div className={`gesture__label ${isIdle ? 'idle' : ''}`}>
          {label}
        </div>
        <div className="gesture__bar">
          <div className="gesture__bar-fill" style={{ width: `${pct * 100}%` }} />
        </div>
        <div className="gesture__conf">
          confidence: {gesture ? conf.toFixed(3) : '—'} · cos sim ∈ [-1, 1]
        </div>
      </div>
    </section>
  );
}
