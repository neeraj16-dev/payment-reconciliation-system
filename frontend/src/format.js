// Amounts arrive from the API as decimal strings. They are formatted by string
// manipulation only, so no precision is lost to floating point.
export function formatINR(value, { sign = false } = {}) {
  if (value === null || value === undefined || value === '') return '—'
  const str = String(value)
  const negative = str.startsWith('-')
  const [intPart, frac] = str.replace(/^[-+]/, '').split('.')
  const grouped = BigInt(intPart || '0').toLocaleString('en-IN')
  const body = `₹${grouped}${frac !== undefined ? `.${frac}` : ''}`
  const isZero = /^0*(\.0*)?$/.test(str.replace(/^[-+]/, ''))
  if (negative && !isZero) return `−${body}`
  if (sign && !isZero) return `+${body}`
  return body
}

export function isZeroAmount(value) {
  return value !== null && value !== undefined && /^[-+]?0*(\.0*)?$/.test(String(value))
}

export function formatCount(n) {
  return Number(n).toLocaleString('en-IN')
}

// Groups map onto categorical slots 1–5 (fixed order); "info" is neutral.
export const ISSUE_GROUPS = {
  integrity: { label: 'Data integrity', slot: 1 },
  matching: { label: 'Matching', slot: 2 },
  timing: { label: 'Timing', slot: 3 },
  amount: { label: 'Amounts', slot: 4 },
  refund: { label: 'Refunds', slot: 5 },
  info: { label: 'Informational', slot: 0 },
}

export const ISSUE_TYPES = {
  DUPLICATE_ENTRY: { label: 'Duplicate entry', group: 'integrity' },
  MISSING_SETTLEMENT: { label: 'Missing settlement', group: 'matching' },
  UNMATCHED_SETTLEMENT: { label: 'Unmatched settlement', group: 'matching' },
  LATE_SETTLEMENT: { label: 'Late settlement', group: 'timing' },
  AMOUNT_MISMATCH: { label: 'Amount mismatch', group: 'amount' },
  TYPE_MISMATCH: { label: 'Type mismatch', group: 'amount' },
  AGGREGATE_ROUNDING_DIFFERENCE: { label: 'Aggregate rounding', group: 'amount' },
  SUB_PAISE_VARIANCE: { label: 'Sub-paise variance', group: 'amount' },
  UNMATCHED_REFUND: { label: 'Unmatched refund', group: 'refund' },
  INVALID_REFUND: { label: 'Invalid refund', group: 'refund' },
  OUT_OF_PERIOD: { label: 'Out of period', group: 'info' },
}

export function issueLabel(type) {
  return ISSUE_TYPES[type]?.label ?? type
}

export function issueSlot(type) {
  return ISSUE_GROUPS[ISSUE_TYPES[type]?.group]?.slot ?? 0
}
