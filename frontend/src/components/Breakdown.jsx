import { formatCount, formatINR, isZeroAmount, ISSUE_TYPES, issueLabel, issueSlot } from '../format'

// Bar length only needs a proportion, so Number() is acceptable here; displayed
// amounts always come from the exact decimal strings.
function VarianceBars({ components, total, totalLabel }) {
  const max = Math.max(...components.map((c) => Math.abs(Number(c.amount))), 0)
  return (
    <div className="variance-list" role="table" aria-label={totalLabel}>
      {components.map((c) => {
        const n = Number(c.amount)
        const zero = isZeroAmount(c.amount)
        const width = max > 0 && !zero ? Math.max((Math.abs(n) / max) * 100, 1.5) : 0
        return (
          <div className={`variance-row${zero ? ' is-zero' : ''}`} role="row" key={c.key}>
            <span className="variance-name" role="cell">
              {c.label}
              <span className="variance-count">{formatCount(c.record_count)} rec.</span>
            </span>
            <span className="variance-track" role="cell" aria-hidden="true">
              <span
                className={`variance-bar ${n < 0 ? 'is-negative' : 'is-positive'}`}
                style={{ width: `${width}%` }}
                title={`${c.label}: ${formatINR(c.amount, { sign: true })}`}
              />
            </span>
            <span className="variance-amount num" role="cell">{formatINR(c.amount, { sign: true })}</span>
          </div>
        )
      })}
      <div className="variance-row variance-total" role="row">
        <span className="variance-name" role="cell">{totalLabel}</span>
        <span className="variance-track" role="cell" />
        <span className="variance-amount num" role="cell">{formatINR(total, { sign: true })}</span>
      </div>
    </div>
  )
}

export default function Breakdown({ report, activeType, onSelectType }) {
  const { summary: s, parameters: p } = report
  const typeOrder = Object.keys(ISSUE_TYPES)
  const counts = Object.entries(report.issue_counts).sort(
    ([a], [b]) => typeOrder.indexOf(a) - typeOrder.indexOf(b),
  )

  return (
    <section className="breakdown-grid" aria-label="Discrepancy breakdown">
      <div className="panel">
        <div className="panel-head">
          <h2>Discrepancies by type</h2>
          <span className="muted">Click to filter</span>
        </div>
        {counts.length === 0 ? (
          <p className="empty">No discrepancies found.</p>
        ) : (
          <ul className="issue-list">
            {counts.map(([type, count]) => (
              <li key={type}>
                <button
                  type="button"
                  className={`issue-item${activeType === type ? ' is-active' : ''}`}
                  aria-pressed={activeType === type}
                  onClick={() => onSelectType(activeType === type ? 'ALL' : type)}
                >
                  <span className={`dot slot-${issueSlot(type)}`} aria-hidden="true" />
                  <span className="issue-name">{issueLabel(type)}</span>
                  <span className="issue-count num">{formatCount(count)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="rounding-callout">
          <h3>Aggregate rounding</h3>
          <dl>
            <dt>Exact sum of sub-paise differences</dt>
            <dd className="num">{formatINR(s.aggregate_rounding_difference, { sign: true })}</dd>
            <dt>Same rows, compared after rounding to 2dp</dt>
            <dd className="num">{formatINR(s.individually_rounded_difference, { sign: true })}</dd>
            <dt>Materiality threshold</dt>
            <dd className="num">{formatINR(p.materiality_threshold)}</dd>
          </dl>
          <p className={`status-line ${s.rounding_threshold_breached ? 'is-critical' : 'is-good'}`}>
            <span aria-hidden="true">{s.rounding_threshold_breached ? '!' : '✓'}</span>
            {s.rounding_threshold_breached
              ? `Threshold breached across ${s.sub_paise_variances} transactions`
              : `Within threshold (${s.sub_paise_variances} sub-paise rows)`}
          </p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>Variance bridge</h2>
          <span className="legend">
            <span className="legend-item"><span className="swatch is-positive" />Platform higher</span>
            <span className="legend-item"><span className="swatch is-negative" />Bank higher</span>
          </span>
        </div>
        <h3 className="subhead">All-time (platform − all bank settlements)</h3>
        <VarianceBars components={report.variance_breakdown} total={s.total_variance} totalLabel="Total variance" />
        <h3 className="subhead">At cutoff {p.cutoff_date} (adds post-cutoff settlements)</h3>
        <VarianceBars
          components={report.cutoff_variance_breakdown.slice(report.variance_breakdown.length)}
          total={s.variance_at_cutoff}
          totalLabel="Variance at cutoff"
        />
      </div>
    </section>
  )
}
