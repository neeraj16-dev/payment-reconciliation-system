export default function ValidationErrors({ detail }) {
  const shown = detail.errors.length
  return (
    <section className="panel alert" role="alert">
      <div className="panel-head">
        <h2>
          <span className="status-icon" aria-hidden="true">!</span> {detail.message}
        </h2>
        <span className="muted">
          {detail.total_errors} error{detail.total_errors === 1 ? '' : 's'}
          {detail.total_errors > shown ? ` (first ${shown} shown)` : ''}
        </span>
      </div>
      <div className="table-wrap">
        <table className="detail-table">
          <thead>
            <tr><th>File</th><th>Line</th><th>Column</th><th>Value</th><th>Problem</th></tr>
          </thead>
          <tbody>
            {detail.errors.map((e, i) => (
              <tr key={i}>
                <td>{e.dataset}</td>
                <td className="mono">{e.row ?? '—'}</td>
                <td className="mono">{e.column ?? '—'}</td>
                <td className="mono">{e.value === null || e.value === undefined ? '—' : e.value === '' ? '(empty)' : e.value}</td>
                <td>{e.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
