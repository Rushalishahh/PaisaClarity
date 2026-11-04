import { useState, useEffect } from 'react'
import AppShell from '../components/AppShell'
import { Card, EmptyState, SkeletonCard } from '../components/UI'
import { ToastProvider } from '../components/Toast'
import { useToast } from '../components/ToastContext'
import { api } from '../api'
import { formatINR } from '../utils/format'

function formatDate(isoString) {
  // The backend sends timestamps like "2026-07-19T14:19:26.089249+00:00"
  // (ISO 8601 format). The built-in Date object parses that automatically,
  // and toLocaleString() converts it to a readable, local-timezone string.
  return new Date(isoString).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

function StatementIcon({ className = "w-12 h-12" }) {
  return (
    <svg viewBox="0 0 48 48" fill="none" className={className} aria-hidden="true">
      <path d="M12 6h16l8 8v28H12V6z" stroke="#7de3d1" strokeWidth="2" strokeLinejoin="round" />
      <path d="M28 6v8h8" stroke="#7de3d1" strokeWidth="2" strokeLinejoin="round" />
      <path d="M18 22h12M18 28h12M18 34h8" stroke="#2a3350" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function History() {
  const toast = useToast()

  const [statements, setStatements] = useState([])
  const [selectedStatement, setSelectedStatement] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    async function fetchStatements() {
      try {
        // api() handles the auth header and the 401 -> /login redirect.
        const result = await api("/statements")
        setStatements(result)
      } catch (err) {
        setError(err.message)
        toast.error(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchStatements()
    // toast is a stable useMemo'd object from the provider (see Toast.jsx),
    // so listing it doesn't cause re-runs - it satisfies the deps lint rule.
  }, [toast])

  async function handleSelectStatement(id) {
    setError("")
    try {
      const result = await api(`/statements/${id}`)
      setSelectedStatement(result)
    } catch (err) {
      setError(err.message)
      toast.error(err.message)
    }
  }

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white">Statement History</h1>
          <p className="text-gray-400 mt-1">Your past uploads and their analysis</p>
        </div>

        {error && (
          <p className="text-coral text-sm bg-coral/10 border border-coral/30 rounded-lg px-4 py-2 mb-6">
            {error}
          </p>
        )}

        {/* Loading skeleton: two list-shaped cards */}
        {loading && (
          <div className="space-y-6">
            <SkeletonCard lines={4} />
            <SkeletonCard lines={2} />
          </div>
        )}

        {/* Empty state: fetch finished, but there's nothing to show */}
        {!loading && statements.length === 0 && (
          <Card>
            <EmptyState
              icon={<StatementIcon />}
              title="No uploads yet"
              description="Every statement you analyze is saved here so you can revisit its full breakdown anytime."
              action={
                <a
                  href="/dashboard"
                  className="bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl px-5 py-2.5 text-sm transition-colors"
                >
                  Upload your first statement
                </a>
              }
            />
          </Card>
        )}

        {/* The list of past uploads */}
        {!loading && statements.length > 0 && (
          <Card title="Past Uploads">
            <ul className="space-y-2">
              {statements.map((s) => (
                <li key={s.id}>
                  <button
                    onClick={() => handleSelectStatement(s.id)}
                    className="w-full flex flex-wrap justify-between items-center gap-x-4 gap-y-1 bg-navy hover:bg-navy/60 rounded-xl px-4 py-3 text-left transition-colors"
                  >
                    <span className="text-gray-200 break-all">{s.filename}</span>
                    <span className="text-gray-500 text-sm">{formatDate(s.uploaded_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        )}

        {/* Detail view: only appears once the user has clicked something */}
        {selectedStatement && (
          <Card title={`Details: ${selectedStatement.filename}`} className="mt-6">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
              <div>
                <p className="text-gray-400 text-sm mb-1">Income</p>
                <p className="text-mint text-xl font-bold">
                  {formatINR(selectedStatement.result.savings_summary.total_income)}
                </p>
              </div>
              <div>
                <p className="text-gray-400 text-sm mb-1">Spend</p>
                <p className="text-coral text-xl font-bold">
                  {formatINR(selectedStatement.result.savings_summary.total_spend)}
                </p>
              </div>
              <div>
                <p className="text-gray-400 text-sm mb-1">Saved</p>
                <p className="text-white text-xl font-bold">
                  {formatINR(selectedStatement.result.savings_summary.total_saved)}
                </p>
              </div>
              <div>
                <p className="text-gray-400 text-sm mb-1">Savings Rate</p>
                <p className="text-mint text-xl font-bold">
                  {selectedStatement.result.savings_summary.savings_rate_pct}%
                </p>
              </div>
            </div>

            <h3 className="text-gray-300 font-medium mb-2">Category Breakdown</h3>
            <ul className="space-y-2">
              {Object.entries(selectedStatement.result.category_totals).map(([category, amount]) => (
                <li key={category} className="flex justify-between bg-navy rounded-xl px-4 py-3">
                  <span className="text-gray-300">{category}</span>
                  <span className="text-white font-medium">{formatINR(amount)}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </AppShell>
  )
}

export default function HistoryPage() {
  return (
    <ToastProvider>
      <History />
    </ToastProvider>
  )
}
