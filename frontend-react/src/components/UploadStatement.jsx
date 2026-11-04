/*
Phase 1 upload UX — a single self-contained component that owns the whole
statement-import flow against the ingest endpoints:

  1. Pick/drag a .csv/.xlsx/.xls/.pdf file (10 MB client-side cap; the
     backend enforces the same limit again).
  2. POST /upload-statement/preview — parse only, nothing saved. Shows a
     preview table, the detected column mapping and any parser warnings.
  3. Structured error codes drive recovery UI:
        password_required / wrong_password -> password prompt (cleared
          after a successful parse; never stored anywhere)
        mapping_required                   -> column-mapping modal fed by
          the backend's headers + sample_rows
        scanned_pdf                        -> plain-language explanation
  4. Confirm -> POST /upload-statement (full analysis, saved) and a green
     import-summary banner with the file's date range.

The parent only receives the finished analysis via onImported(result) —
all intermediate states live here. Old saved statements (no ingest_report)
render unchanged because this component never touches the results area.
*/

import { useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { useToast } from '../components/ToastContext'
import { Card } from '../components/UI'

const ACCEPTED_EXT = ['.csv', '.xlsx', '.xls', '.pdf']
const MAX_BYTES = 10 * 1024 * 1024 // 10 MB — must match the backend cap

/* Canonical ingest fields -> labels shown in the mapping modal. The three
   with * are what the backend requires (date, description + any amount
   column); the rest are optional refinements. */
const MAPPING_FIELDS = [
  ['date', 'Date *'],
  ['description', 'Description *'],
  ['debit', 'Debit / Withdrawal'],
  ['credit', 'Credit / Deposit'],
  ['amount', 'Amount (single column)'],
  ['dr_cr', 'Dr/Cr indicator'],
  ['balance', 'Balance'],
  ['reference', 'Ref / Cheque No.'],
]

function formatBytes(n) {
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.max(1, Math.round(n / 1024))} KB`
}

function formatINR(value) {
  return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function LockIcon({ className = 'w-4 h-4' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <rect x="5" y="10" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
      <path d="M8 10V7a4 4 0 018 0v3" stroke="currentColor" strokeWidth="2" />
    </svg>
  )
}

export default function UploadStatement({ onImported }) {
  const toast = useToast()
  const inputRef = useRef(null)

  const [file, setFile] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [preview, setPreview] = useState(null) // { preview_rows, report, total_rows, mapping_used }
  const [importSummary, setImportSummary] = useState(null)
  const [error, setError] = useState(null) // { message, code }

  // Recovery state. The password lives in memory only for the current
  // attempt and is cleared the moment parsing succeeds — it is never
  // stored, logged or sent anywhere except this one request.
  const [password, setPassword] = useState('')
  const [passwordFor, setPasswordFor] = useState(null) // 'password_required' | 'wrong_password'
  const [mappingOpen, setMappingOpen] = useState(false)
  const [mappingMeta, setMappingMeta] = useState(null) // { headers, sample_rows }
  const [mappingDraft, setMappingDraft] = useState({})

  function resetFileState() {
    setFile(null)
    setPreview(null)
    setError(null)
    setPassword('')
    setPasswordFor(null)
    setMappingOpen(false)
    setMappingMeta(null)
    setMappingDraft({})
    if (inputRef.current) inputRef.current.value = ''
  }

  function resetAll() {
    resetFileState()
    setImportSummary(null)
  }

  function buildForm() {
    const formData = new FormData()
    formData.append('file', file)
    if (password) formData.append('password', password)
    // column_mapping travels as a JSON string form field (see main.py).
    if (Object.keys(mappingDraft).length > 0) {
      formData.append('column_mapping', JSON.stringify(mappingDraft))
    }
    return formData
  }

  function pickFile(f) {
    if (!f) return
    const ext = `.${(f.name.split('.').pop() || '').toLowerCase()}`
    if (!ACCEPTED_EXT.includes(ext)) {
      setError({ code: 'unsupported_format', message: 'Unsupported file type. Accepted: CSV, XLSX, XLS or PDF.' })
      return
    }
    if (f.size > MAX_BYTES) {
      setError({ code: 'file_too_large', message: 'File is larger than the 10 MB limit.' })
      return
    }
    resetFileState()
    setFile(f)
  }

  async function runPreview() {
    if (!file) return
    setPreviewing(true)
    setError(null)
    try {
      const result = await api('/upload-statement/preview', { method: 'POST', body: buildForm() })
      // Success: clear the one-shot password so it can't leak into retries.
      setPassword('')
      setPasswordFor(null)
      setPreview(result)
    } catch (err) {
      const code = err instanceof ApiError ? err.data?.detail?.code : null
      const detail = err instanceof ApiError ? err.data?.detail : null
      if (code === 'password_required' || code === 'wrong_password') {
        setPasswordFor(code)
        setPreview(null)
      } else if (code === 'mapping_required') {
        setMappingMeta({ headers: detail.headers || [], sample_rows: detail.sample_rows || [] })
        setMappingDraft({})
        setMappingOpen(true)
        setPreview(null)
      } else {
        setError({ code: code || 'error', message: err.message })
        setPreview(null)
      }
    } finally {
      setPreviewing(false)
    }
  }

  async function runImport() {
    setImporting(true)
    setError(null)
    try {
      const result = await api('/upload-statement', { method: 'POST', body: buildForm() })
      const report = result.ingest_report || {}
      setImportSummary({
        filename: file?.name,
        total_rows: report.rows_parsed ?? result.savings_summary?.transactions_analyzed,
        date_range: report.date_range,
        warnings: report.warnings || [],
        rows_skipped: report.rows_skipped ?? 0,
      })
      setPassword('')
      setPasswordFor(null)
      setPreview(null)
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
      toast.success('Statement imported')
      onImported?.(result)
    } catch (err) {
      setError({ code: null, message: err.message })
    } finally {
      setImporting(false)
    }
  }

  const report = preview?.report || {}
  const warnings = report.warnings || []

  return (
    <Card className="mb-6">
      {/* -------------------------------------------------- drop zone */}
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload a bank statement"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click() }}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          pickFile(e.dataTransfer.files?.[0])
        }}
        className={`cursor-pointer rounded-2xl border-2 border-dashed px-6 py-8 text-center transition-colors ${
          dragOver ? 'border-mint bg-mint/5' : 'border-gray-700 hover:border-gray-500'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx,.xls,.pdf"
          className="hidden"
          onChange={(e) => pickFile(e.target.files?.[0])}
        />
        {file ? (
          <div className="flex flex-wrap items-center justify-center gap-3">
            <span className="text-white font-medium">{file.name}</span>
            <span className="text-gray-500 text-sm">{formatBytes(file.size)}</span>
            <button
              type="button"
              className="text-coral text-sm hover:underline"
              onClick={(e) => { e.stopPropagation(); resetFileState() }}
            >
              Remove
            </button>
          </div>
        ) : (
          <>
            <p className="text-white font-medium">Drag &amp; drop your bank statement here</p>
            <p className="text-gray-500 text-sm mt-1">or click to browse — CSV, XLSX, XLS or PDF, up to 10 MB</p>
          </>
        )}
      </div>

      {/* -------------------------------------------------- actions */}
      <div className="flex flex-wrap items-center gap-3 mt-4">
        <button
          type="button"
          onClick={runPreview}
          disabled={!file || previewing || importing || mappingOpen}
          className="bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl px-6 py-3 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {previewing ? 'Reading statement…' : 'Preview import'}
        </button>
        <button
          type="button"
          onClick={resetAll}
          className="text-gray-400 hover:text-gray-200 text-sm"
        >
          Start over
        </button>
      </div>

      {/* -------------------------------------------------- privacy note */}
      <p className="flex items-start gap-2 text-gray-500 text-xs mt-3">
        <LockIcon className="w-4 h-4 mt-0.5 shrink-0" />
        <span>
          Your file is processed in memory and never stored — only the derived insights are
          saved. Passwords are never kept, and transaction details are never logged.
        </span>
      </p>

      {/* -------------------------------------------------- sample files */}
      <div className="mt-3 text-xs text-gray-500">
        No statement handy? Try a sample:{' '}
        <a className="text-mint hover:underline" href={`${import.meta.env.BASE_URL}samples/sample_statement.csv`} download>CSV</a>
        {' · '}
        <a className="text-mint hover:underline" href={`${import.meta.env.BASE_URL}samples/sample_statement_alt_format.csv`} download>alt-format CSV</a>
        {' · '}
        <a className="text-mint hover:underline" href={`${import.meta.env.BASE_URL}samples/sample_statement_alt_format_2.csv`} download>overlap CSV</a>
        {' · '}
        <a className="text-mint hover:underline" href={`${import.meta.env.BASE_URL}samples/sample_statement.pdf`} download>PDF</a>
      </div>

      {/* -------------------------------------------------- error banner */}
      {error && (
        <p className="flex items-start gap-2 text-coral text-sm bg-coral/10 border border-coral/30 rounded-lg px-4 py-2 mt-4">
          {error.code === 'scanned_pdf'
            ? 'This PDF looks like a scan or photo — it has no readable text, so it can\'t be parsed. Try exporting a text PDF from your bank, or upload a CSV.'
            : error.message}
        </p>
      )}

      {/* -------------------------------------------------- password prompt */}
      {passwordFor && (
        <div className="bg-navy border border-gray-700 rounded-xl p-4 mt-4">
          <p className="text-gray-300 text-sm">
            {passwordFor === 'wrong_password'
              ? 'That password didn\'t unlock the PDF. Try again:'
              : 'This PDF is password-protected. Enter the password your bank uses (usually your name + DOB or PAN):'}
          </p>
          <form
            className="flex flex-col sm:flex-row gap-3 mt-3"
            onSubmit={(e) => { e.preventDefault(); runPreview() }}
          >
            <input
              type="password"
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="PDF password"
              className="flex-1 bg-navy-light border border-gray-700 rounded-xl px-4 py-2 text-white text-sm focus:border-mint focus:outline-none"
            />
            <button
              type="submit"
              disabled={!password || previewing}
              className="bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl px-5 py-2 text-sm transition-colors disabled:opacity-60"
            >
              {previewing ? 'Trying…' : 'Unlock & preview'}
            </button>
          </form>
        </div>
      )}

      {/* -------------------------------------------------- mapping modal */}
      {mappingOpen && mappingMeta && (
        <div
          className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 px-4 overflow-y-auto py-8"
          onClick={() => setMappingOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Map statement columns"
        >
          <div
            className="bg-navy-light border border-gray-700 rounded-2xl p-6 shadow-2xl w-full max-w-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-white font-semibold text-lg">Map the statement columns</h3>
            <p className="text-gray-400 text-sm mt-1">
              We couldn\'t identify the columns automatically. Tell us which header is which —
              Date, Description and at least one amount column are required.
            </p>

            <div className="grid sm:grid-cols-2 gap-3 mt-4">
              {MAPPING_FIELDS.map(([field, label]) => (
                <label key={field} className="block">
                  <span className="text-gray-400 text-xs">{label}</span>
                  <select
                    value={mappingDraft[field] || ''}
                    onChange={(e) => setMappingDraft((d) => ({ ...d, [field]: e.target.value }))}
                    className="mt-1 w-full bg-navy border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:border-mint focus:outline-none"
                  >
                    <option value="">— not used —</option>
                    {mappingMeta.headers.map((h, i) => (
                      <option key={i} value={h}>{h}</option>
                    ))}
                  </select>
                </label>
              ))}
            </div>

            {mappingMeta.sample_rows.length > 0 && (
              <div className="mt-4 overflow-x-auto">
                <p className="text-gray-500 text-xs mb-2">First rows from your file:</p>
                <table className="w-full text-xs text-gray-300">
                  <tbody>
                    {mappingMeta.sample_rows.map((row, r) => (
                      <tr key={r} className="border-b border-gray-800">
                        {mappingMeta.headers.map((_, c) => (
                          <td key={c} className="px-2 py-1 whitespace-nowrap max-w-[160px] truncate">
                            {String(row[c] ?? '')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex justify-end gap-3 mt-6">
              <button
                type="button"
                onClick={() => setMappingOpen(false)}
                className="bg-navy border border-gray-700 hover:border-gray-500 text-gray-300 rounded-xl px-4 py-2 text-sm transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={async () => {
                  setMappingOpen(false)
                  await runPreview()
                }}
                className="bg-mint hover:bg-mint-dark text-navy rounded-xl px-4 py-2 text-sm font-semibold transition-colors"
              >
                Use these columns
              </button>
            </div>
          </div>
        </div>
      )}

      {/* -------------------------------------------------- preview table */}
      {preview && (
        <div className="mt-5 border border-gray-700 rounded-2xl p-4 bg-navy">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mb-3">
            <p className="text-white font-semibold">
              {preview.total_rows} transaction{preview.total_rows === 1 ? '' : 's'} found
            </p>
            {report.source_format && (
              <span className="text-xs bg-navy-light text-gray-400 rounded-full px-2 py-0.5 uppercase">{report.source_format}</span>
            )}
            {report.date_range?.from && (
              <span className="text-gray-500 text-sm">
                {report.date_range.from} → {report.date_range.to}
              </span>
            )}
          </div>

          {(warnings.length > 0 || report.rows_skipped > 0) && (
            <ul className="text-xs text-yellow-200/90 bg-yellow-400/10 border border-yellow-400/20 rounded-lg px-4 py-2 mb-3 space-y-1">
              {warnings.map((w, i) => <li key={i}>{w}</li>)}
              {report.rows_skipped > 0 && <li>{report.rows_skipped} row(s) skipped (unreadable or not transactions).</li>}
            </ul>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs text-left">
                  <th className="py-2 pr-4">Date</th>
                  <th className="py-2 pr-4">Description</th>
                  <th className="py-2 pr-4 text-right">Amount</th>
                  <th className="py-2 text-right">Balance</th>
                </tr>
              </thead>
              <tbody>
                {preview.preview_rows.map((r, i) => (
                  <tr key={i} className="border-t border-gray-800">
                    <td className="py-2 pr-4 text-gray-400 whitespace-nowrap">{r.date}</td>
                    <td className="py-2 pr-4 text-gray-200 max-w-[280px] truncate">{r.description}</td>
                    <td className={`py-2 pr-4 text-right font-medium whitespace-nowrap ${r.type === 'credit' ? 'text-mint' : 'text-gray-200'}`}>
                      {r.type === 'credit' ? '+' : '−'}{formatINR(r.amount)}
                    </td>
                    <td className="py-2 text-right text-gray-500 whitespace-nowrap">
                      {r.balance == null ? '—' : formatINR(r.balance)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {report.mapping_used?.method && (
            <p className="text-gray-500 text-xs mt-3">
              Columns detected via {report.mapping_used.method.replace(/_/g, ' ')}
              {report.mapping_used.columns && Object.keys(report.mapping_used.columns).length > 0 && (
                <> — {Object.entries(report.mapping_used.columns).map(([k, v]) => `${k} → ${v}`).join(', ')}</>
              )}
            </p>
          )}

          <div className="flex flex-wrap gap-3 mt-4">
            <button
              type="button"
              onClick={runImport}
              disabled={importing}
              className="bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl px-6 py-2.5 text-sm transition-colors disabled:opacity-60"
            >
              {importing ? 'Importing…' : 'Confirm & analyze'}
            </button>
            <button
              type="button"
              onClick={resetAll}
              className="bg-navy border border-gray-700 hover:border-gray-500 text-gray-300 rounded-xl px-4 py-2.5 text-sm transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* -------------------------------------------------- import summary */}
      {importSummary && (
        <div className="bg-mint/10 border border-mint/30 rounded-xl px-4 py-3 mt-4" role="status">
          <p className="text-mint text-sm font-semibold">
            Imported {importSummary.total_rows} transactions from {importSummary.filename}
            {importSummary.date_range?.from && (
              <> ({importSummary.date_range.from} → {importSummary.date_range.to})</>
            )}
            . Insights below are updated.
          </p>
          {(importSummary.warnings.length > 0 || importSummary.rows_skipped > 0) && (
            <ul className="text-gray-300 text-xs mt-2 space-y-1">
              {importSummary.rows_skipped > 0 && (
                <li>{importSummary.rows_skipped} row(s) skipped (unreadable or not transactions).</li>
              )}
              {/* Parser notes render one per line — this is where the
                  date-overlap and duplicate-count warnings appear when an
                  upload overlaps a previously imported statement. */}
              {importSummary.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  )
}
