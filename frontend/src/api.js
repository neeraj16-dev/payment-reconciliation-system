const API_BASE = import.meta.env.VITE_API_URL ?? ''

export class ValidationFailure extends Error {
  constructor(detail) {
    super(detail.message)
    this.detail = detail
  }
}

export async function runReconciliation({ platformFile, bankFile, cutoffDate, threshold }) {
  const form = new FormData()
  form.append('platform_file', platformFile)
  form.append('bank_file', bankFile)
  if (cutoffDate) form.append('cutoff_date', cutoffDate)
  if (threshold) form.append('materiality_threshold', threshold)

  let response
  try {
    response = await fetch(`${API_BASE}/api/reconcile`, { method: 'POST', body: form })
  } catch {
    throw new Error('Cannot reach the reconciliation service. Is the backend running on port 8000?')
  }

  const body = await response.json().catch(() => null)
  if (response.ok) return body
  if (response.status === 422 && body?.detail?.errors) throw new ValidationFailure(body.detail)
  throw new Error(body?.detail?.message ?? `Request failed (${response.status}).`)
}
