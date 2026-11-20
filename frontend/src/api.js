const API_BASE = import.meta.env.VITE_API_URL ?? ''

export const KEEP_ALIVE_INTERVAL_MS = 10 * 60 * 1000

// Lightweight request that keeps the hosted backend from idling out.
// Failures are ignored: a missed ping must never disturb the user.
export async function pingBackend() {
  try {
    await fetch(`${API_BASE}/api/health`, { method: 'GET', cache: 'no-store' })
  } catch {
    // ignore
  }
}

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
