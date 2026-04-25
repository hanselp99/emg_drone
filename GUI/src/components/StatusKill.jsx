export default function StatusKill({ status, killActive, onArmToggle, onStop }) {
  const armed = !!status.armed;

  return (
    <section className="panel status">
      <h2 className="panel__title">Status &amp; Safety</h2>

      <div className="status__indicators">
        <Pill label="Armband" on={!!status.armband} />
        <Pill label="Pi"       on={!!status.pi} />
        <Pill label="Drone"    on={!!status.drone} />
      </div>

      <div className="status__row">
        <div className="status__armed-label">
          State<span className={`val ${armed ? 'on' : ''}`}>{armed ? 'ARMED' : 'DISARMED'}</span>
        </div>
        <button
          className={`toggle ${armed ? 'on' : ''}`}
          onClick={onArmToggle}
        >
          {armed ? 'Disarm' : 'Arm'}
        </button>
      </div>

      <button
        className={`kill ${killActive ? 'active' : ''}`}
        onClick={onStop}
        aria-label="Emergency stop"
      >
        STOP
        <span className="kill__hint">SPACEBAR</span>
      </button>
    </section>
  );
}

function Pill({ label, on }) {
  return (
    <div className={`status__pill ${on ? 'on' : ''}`}>
      <span className="status__dot" />
      {label}
    </div>
  );
}
