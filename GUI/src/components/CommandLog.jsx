function formatTs(ts) {
  const d = new Date(ts);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  const ms = String(d.getMilliseconds()).padStart(3, '0');
  return `${hh}:${mm}:${ss}.${ms}`;
}

export default function CommandLog({ commands, stale }) {
  return (
    <section className={`panel log ${stale ? 'stale' : ''}`}>
      <h2 className="panel__title">Command Log · last 20</h2>
      {commands.length === 0 ? (
        <div className="log__empty">no commands yet</div>
      ) : (
        <ul className="log__list">
          {commands.map((c, i) => (
            <li className="log__row" key={`${c.ts}-${i}`}>
              <span className="log__ts">{formatTs(c.ts)}</span>
              <span className={`log__cmd ${c.cmd === 'STOP' ? 'stop' : ''}`}>
                {c.cmd}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
