import { useState } from 'react'
import { runReconciliation, ValidationFailure } from './api'
import Breakdown from './components/Breakdown'
import DiscrepancyTable from './components/DiscrepancyTable'
import SummaryCards from './components/SummaryCards'
import UploadPanel from './components/UploadPanel'
import ValidationErrors from './components/ValidationErrors'
import { exportCsv, exportJson } from './export'

// Month-end close: default the cutoff to the last day of the previous month.
function previousMonthEnd() {
  const now = new Date()
  const d = new Date(now.getFullYear(), now.getMonth(), 0)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export default function App() {
  const [inputs, setInputs] = useState({
    platformFile: null,
    bankFile: null,
    cutoffDate: previousMonthEnd(),
    threshold: '0.10',
  })
  const [report, setReport] = useState(null)
  const [validation, setValidation] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [activeType, setActiveType] = useState('ALL')

  const submit = async () => {
    setLoading(true)
    setError(null)
    setValidation(null)
    try {
      const result = await runReconciliation(inputs)
      setReport(result)
      setActiveType('ALL')
    } catch (e) {
      setReport(null)
      if (e instanceof ValidationFailure) setValidation(e.detail)
      else setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Payment Reconciliation</h1>
          <p className="muted">Platform transactions vs. bank settlements</p>
        </div>
        {report && (
          <div className="header-actions">
            <span className="run-meta muted">
              Cutoff <strong>{report.parameters.cutoff_date}</strong>
              {report.parameters.cutoff_source === 'derived' ? ' (derived)' : ''} · {report.parameters.bank_rounding_mode}
            </span>
            <button type="button" className="btn btn-secondary" onClick={() => exportCsv(report)}>Export CSV</button>
            <button type="button" className="btn btn-secondary" onClick={() => exportJson(report)}>Export JSON</button>
          </div>
        )}
      </header>

      <main>
        <UploadPanel
          values={inputs}
          onChange={(patch) => setInputs((v) => ({ ...v, ...patch }))}
          onSubmit={submit}
          loading={loading}
        />

        {error && (
          <div className="panel alert" role="alert">
            <span className="status-icon" aria-hidden="true">!</span> {error}
          </div>
        )}
        {validation && <ValidationErrors detail={validation} />}

        {report && (
          <>
            <SummaryCards report={report} />
            <Breakdown report={report} activeType={activeType} onSelectType={setActiveType} />
            <DiscrepancyTable
              discrepancies={report.discrepancies}
              activeType={activeType}
              onSelectType={setActiveType}
            />
          </>
        )}

        {!report && !validation && !error && (
          <div className="panel placeholder">
            Upload both CSV files, choose a cutoff date, and run the reconciliation.
          </div>
        )}
      </main>
    </div>
  )
}
