import { formatCount, formatINR, isZeroAmount } from '../format'

function Tile({ label, value, detail, tone }) {
  return (
    <div className={`tile${tone ? ` tile-${tone}` : ''}`}>
      <span className="tile-label">{label}</span>
      <span className="tile-value">{value}</span>
      {detail && <span className="tile-detail">{detail}</span>}
    </div>
  )
}

export default function SummaryCards({ report }) {
  const s = report.summary
  const issueTone = (n) => (n > 0 ? 'flag' : undefined)

  return (
    <section aria-labelledby="summary-heading">
      <div className="section-head">
        <h2 id="summary-heading">Summary</h2>
        <span className={`status-pill ${s.variance_fully_explained ? 'is-good' : 'is-critical'}`}>
          <span aria-hidden="true">{s.variance_fully_explained ? '✓' : '!'}</span>
          {s.variance_fully_explained ? 'Variance fully explained' : 'Unexplained variance remains'}
        </span>
      </div>

      <div className="tiles tiles-amounts">
        <Tile
          label="Platform amount"
          value={formatINR(s.aggregate_platform_amount)}
          detail={`${formatCount(s.total_platform_records)} records`}
        />
        <Tile
          label="Bank amount"
          value={formatINR(s.aggregate_bank_amount)}
          detail={`${formatINR(s.aggregate_bank_amount_at_cutoff)} settled by cutoff`}
        />
        <Tile
          label="Total variance"
          value={formatINR(s.total_variance, { sign: true })}
          detail="Platform − all bank settlements"
          tone={isZeroAmount(s.total_variance) ? undefined : 'flag'}
        />
        <Tile
          label="Variance at cutoff"
          value={formatINR(s.variance_at_cutoff, { sign: true })}
          detail={`Includes ${formatINR(s.late_settlement_amount)} in transit`}
          tone={isZeroAmount(s.variance_at_cutoff) ? undefined : 'flag'}
        />
      </div>

      <div className="tiles tiles-counts">
        <Tile
          label="Platform transactions"
          value={formatCount(s.total_platform_records)}
          detail={`${formatCount(s.unique_platform_transactions)} unique IDs`}
        />
        <Tile
          label="Bank settlements"
          value={formatCount(s.total_bank_settlements)}
          detail={`${formatCount(s.unique_bank_transactions)} unique IDs`}
        />
        <Tile label="Matched" value={formatCount(s.matched_transactions)} detail="One-to-one on transaction ID" />
        <Tile
          label="Unmatched"
          value={formatCount(s.unmatched_transactions)}
          detail={`${s.unmatched_platform_transactions} platform · ${s.unmatched_bank_settlements} bank`}
          tone={issueTone(s.unmatched_transactions)}
        />
        <Tile
          label="Duplicate records"
          value={formatCount(s.duplicate_records)}
          detail={`${s.duplicate_groups} group(s)${s.unresolved_duplicate_ids ? ` · ${s.unresolved_duplicate_ids} unresolved` : ''}`}
          tone={issueTone(s.duplicate_records + s.unresolved_duplicate_ids)}
        />
        <Tile
          label="Late settlements"
          value={formatCount(s.late_settlements)}
          detail="Timing differences"
          tone={issueTone(s.late_settlements)}
        />
        <Tile
          label="Unmatched refunds"
          value={formatCount(s.unmatched_refunds)}
          detail={`${s.invalid_refunds} invalid refund(s)`}
          tone={issueTone(s.unmatched_refunds + s.invalid_refunds)}
        />
      </div>
    </section>
  )
}
