import { Fragment, useMemo, useState } from 'react'
import { formatINR, ISSUE_TYPES, issueLabel, issueSlot } from '../format'

const PAGE_SIZE = 50
const typeOrder = Object.keys(ISSUE_TYPES)

const COLUMNS = [
  { key: 'discrepancy_id', label: 'ID' },
  { key: 'issue_type', label: 'Issue' },
  { key: 'transaction_id', label: 'Transaction' },
  { key: 'source_dataset', label: 'Source' },
  { key: 'transaction_date', label: 'Txn date' },
  { key: 'settlement_date', label: 'Settled' },
  { key: 'platform_amount', label: 'Platform', numeric: true },
  { key: 'bank_amount', label: 'Bank', numeric: true },
  { key: 'amount_difference', label: 'Difference', numeric: true },
]

function compare(a, b, key, numeric) {
  const va = a[key]
  const vb = b[key]
  if (va == null && vb == null) return 0
  if (va == null) return 1
  if (vb == null) return -1
  if (key === 'issue_type') return typeOrder.indexOf(va) - typeOrder.indexOf(vb)
  if (numeric) return Number(va) - Number(vb) // ordering only; display uses exact strings
  return String(va).localeCompare(String(vb))
}

export default function DiscrepancyTable({ discrepancies, activeType, onSelectType }) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState({ key: 'discrepancy_id', dir: 1 })
  const [expanded, setExpanded] = useState(null)
  const [limit, setLimit] = useState(PAGE_SIZE)

  const presentTypes = useMemo(
    () => typeOrder.filter((t) => discrepancies.some((d) => d.issue_type === t)),
    [discrepancies],
  )

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    const filtered = discrepancies.filter((d) => {
      if (activeType !== 'ALL' && d.issue_type !== activeType) return false
      if (!q) return true
      return [d.transaction_id, d.settlement_id, d.discrepancy_id, d.classification, ...d.related_transaction_ids]
        .some((v) => v && v.toLowerCase().includes(q))
    })
    const col = COLUMNS.find((c) => c.key === sort.key)
    return [...filtered].sort((a, b) => sort.dir * compare(a, b, sort.key, col?.numeric))
  }, [discrepancies, activeType, query, sort])

  const toggleSort = (key) => setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: 1 }))

  return (
    <section className="panel" aria-labelledby="detail-heading">
      <div className="panel-head">
        <h2 id="detail-heading">Discrepancy detail</h2>
        <div className="table-controls">
          <select
            aria-label="Filter by issue type"
            value={activeType}
            onChange={(e) => { onSelectType(e.target.value); setLimit(PAGE_SIZE) }}
          >
            <option value="ALL">All issues ({discrepancies.length})</option>
            {presentTypes.map((t) => (
              <option key={t} value={t}>{issueLabel(t)}</option>
            ))}
          </select>
          <input
            type="search"
            placeholder="Search transaction / settlement ID"
            aria-label="Search by ID"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setLimit(PAGE_SIZE) }}
          />
        </div>
      </div>

      <div className="table-wrap">
        <table className="detail-table">
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  className={c.numeric ? 'num' : undefined}
                  aria-sort={sort.key === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}
                >
                  <button type="button" className="th-btn" onClick={() => toggleSort(c.key)}>
                    {c.label}
                    <span className="sort-ind" aria-hidden="true">
                      {sort.key === c.key ? (sort.dir === 1 ? '▲' : '▼') : ''}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={COLUMNS.length} className="empty">No discrepancies match.</td></tr>
            )}
            {rows.slice(0, limit).map((d) => {
              const open = expanded === d.discrepancy_id
              return (
                <Fragment key={d.discrepancy_id}>
                  <tr
                    className={`data-row${open ? ' is-open' : ''}`}
                    onClick={() => setExpanded(open ? null : d.discrepancy_id)}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(open ? null : d.discrepancy_id) }
                    }}
                    aria-expanded={open}
                  >
                    <td className="mono">{d.discrepancy_id}</td>
                    <td>
                      <span className="issue-tag">
                        <span className={`dot slot-${issueSlot(d.issue_type)}`} aria-hidden="true" />
                        {issueLabel(d.issue_type)}
                      </span>
                    </td>
                    <td className="mono">
                      {d.transaction_id ?? (d.related_transaction_ids.length
                        ? `${d.related_transaction_ids.length} transactions`
                        : '—')}
                    </td>
                    <td>{d.source_dataset}</td>
                    <td className="mono">{d.transaction_date ?? '—'}</td>
                    <td className="mono">{d.settlement_date ?? '—'}</td>
                    <td className="num">{formatINR(d.platform_amount)}</td>
                    <td className="num">{formatINR(d.bank_amount)}</td>
                    <td className="num">{formatINR(d.amount_difference, { sign: true })}</td>
                  </tr>
                  <tr className={`detail-row${open ? '' : ' is-collapsed'}`}>
                    <td colSpan={COLUMNS.length}>
                      <p className="explanation">{d.explanation}</p>
                      <dl className="trace">
                        <dt>Classification</dt><dd>{d.classification}</dd>
                        {d.settlement_id && (<><dt>Settlement</dt><dd className="mono">{d.settlement_id}</dd></>)}
                        {d.platform_rows.length > 0 && (<><dt>Platform CSV lines</dt><dd className="mono">{d.platform_rows.join(', ')}</dd></>)}
                        {d.bank_rows.length > 0 && (<><dt>Bank CSV lines</dt><dd className="mono">{d.bank_rows.join(', ')}</dd></>)}
                        {d.related_transaction_ids.length > 0 && (
                          <><dt>Related</dt><dd className="mono">{d.related_transaction_ids.join(', ')}</dd></>
                        )}
                      </dl>
                    </td>
                  </tr>
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="table-foot">
        <span className="muted">
          Showing {Math.min(limit, rows.length)} of {rows.length} · click a row for the explanation and source lines
        </span>
        {rows.length > limit && (
          <button type="button" className="btn btn-secondary" onClick={() => setLimit((l) => l + PAGE_SIZE)}>
            Show more
          </button>
        )}
      </div>
    </section>
  )
}
