import { useRef, useState } from 'react'

function FileDrop({ id, label, hint, file, onChange }) {
  const input = useRef(null)
  const [dragging, setDragging] = useState(false)

  const accept = (files) => {
    if (files?.[0]) onChange(files[0])
  }

  return (
    <div
      className={`filedrop${dragging ? ' is-dragging' : ''}${file ? ' has-file' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); accept(e.dataTransfer.files) }}
    >
      <label htmlFor={id} className="filedrop-label">{label}</label>
      <input
        ref={input}
        id={id}
        type="file"
        accept=".csv,text/csv"
        className="visually-hidden"
        onChange={(e) => accept(e.target.files)}
      />
      <button type="button" className="btn btn-secondary" onClick={() => input.current?.click()}>
        {file ? 'Replace file' : 'Choose CSV'}
      </button>
      <span className="filedrop-name" title={file?.name}>
        {file ? `${file.name} · ${(file.size / 1024).toFixed(1)} KB` : hint}
      </span>
    </div>
  )
}

export default function UploadPanel({ values, onChange, onSubmit, loading }) {
  const { platformFile, bankFile, cutoffDate, threshold } = values
  const ready = platformFile && bankFile && !loading

  return (
    <form
      className="panel upload-panel"
      onSubmit={(e) => { e.preventDefault(); if (ready) onSubmit() }}
    >
      <FileDrop
        id="platform-file"
        label="Platform transactions"
        hint="platform_transactions.csv"
        file={platformFile}
        onChange={(f) => onChange({ platformFile: f })}
      />
      <FileDrop
        id="bank-file"
        label="Bank settlements"
        hint="bank_settlements.csv"
        file={bankFile}
        onChange={(f) => onChange({ bankFile: f })}
      />
      <div className="field">
        <label htmlFor="cutoff">Reconciliation cutoff</label>
        <input
          id="cutoff"
          type="date"
          value={cutoffDate}
          onChange={(e) => onChange({ cutoffDate: e.target.value })}
        />
        <span className="field-hint">Recorded on/before, settled after = late</span>
      </div>
      <div className="field field-narrow">
        <label htmlFor="threshold">Rounding threshold (₹)</label>
        <input
          id="threshold"
          type="text"
          inputMode="decimal"
          value={threshold}
          onChange={(e) => onChange({ threshold: e.target.value })}
        />
        <span className="field-hint">Aggregate materiality</span>
      </div>
      <button type="submit" className="btn btn-primary run-btn" disabled={!ready}>
        {loading ? 'Reconciling…' : 'Run reconciliation'}
      </button>
    </form>
  )
}
