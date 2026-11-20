const DETAIL_COLUMNS = [
  'discrepancy_id', 'issue_type', 'classification', 'source_dataset', 'transaction_id',
  'settlement_id', 'transaction_date', 'settlement_date', 'platform_amount', 'bank_amount',
  'amount_difference', 'explanation', 'platform_rows', 'bank_rows', 'related_transaction_ids',
]

const NUMERIC = /^-?\d+(\.\d+)?$/

function csvCell(value) {
  if (value === null || value === undefined) return ''
  let text = Array.isArray(value) ? value.join(' ') : String(value)
  // Block spreadsheet formula injection, but leave signed numbers alone.
  if (/^[=+\-@\t\r]/.test(text) && !NUMERIC.test(text)) text = `'${text}`
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function download(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function baseName(report) {
  return `reconciliation_${report.parameters.cutoff_date}`
}

export function exportCsv(report) {
  const lines = [DETAIL_COLUMNS.join(',')]
  for (const d of report.discrepancies) lines.push(DETAIL_COLUMNS.map((c) => csvCell(d[c])).join(','))

  // Summary section appended after a blank line, as key,value pairs.
  lines.push('', 'summary_metric,value')
  for (const [k, v] of Object.entries(report.parameters)) lines.push(`${csvCell(k)},${csvCell(v)}`)
  for (const [k, v] of Object.entries(report.summary)) lines.push(`${csvCell(k)},${csvCell(v)}`)
  lines.push('', 'variance_component,amount,record_count')
  for (const c of report.cutoff_variance_breakdown) lines.push([c.key, c.amount, c.record_count].map(csvCell).join(','))

  download(`${baseName(report)}.csv`, '﻿' + lines.join('\r\n'), 'text/csv;charset=utf-8')
}

export function exportJson(report) {
  download(`${baseName(report)}.json`, JSON.stringify(report, null, 2), 'application/json')
}
