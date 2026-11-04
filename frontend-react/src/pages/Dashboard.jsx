import { useEffect, useState } from 'react'
import { api } from '../api'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import AppShell from '../components/AppShell'
import { Card, EmptyState } from '../components/UI'
import { ToastProvider } from '../components/Toast'
import { useToast } from '../components/ToastContext'
import UploadStatement from '../components/UploadStatement'
import { formatINR, formatINRCompact } from '../utils/format'

const CATEGORY_COLORS = {
  Rent: "#a3f5e3",
  "EMI & Loans": "#f5a3a3",
  Investments: "#d17de3",
  Health: "#7de3a3",
  Education: "#f5b8a3",
  Travel: "#a3c9f5",
  "Cash Withdrawal": "#e3a3c9",
  Transfers: "#a3e37d",
  Insurance: "#7da3f5",
  Food: "#7de3d1",
  Groceries: "#4fc9b3",
  Shopping: "#f5a3c7",
  Transport: "#ea7bab",
  Bills: "#e3d17d",
  Entertainment: "#c7a3f5",
  Income: "#7de3d1",
  Other: "#9ca3af",
}

const CATEGORY_COLOR_PALETTE = [
  "#7de3d1", "#f5a3c7", "#4fc9b3", "#ea7bab", "#a3c9f5", "#e3d17d", "#c7a3f5", "#7de3a3",
  "#f5b8a3", "#a3f5e3", "#f5a3a3", "#d17de3", "#7da3f5", "#e3a3c9", "#a3e37d", "#f5e3a3",
]

function StatCard({ label, value, accent = "text-white" }) {
  return (
    <div className="bg-navy-light rounded-2xl p-6 shadow-lg">
      <p className="text-gray-400 text-sm mb-1">{label}</p>
      <p className={`text-2xl font-bold ${accent}`}>{value}</p>
    </div>
  )
}

function UploadIcon({ className = "w-12 h-12" }) {
  return (
    <svg viewBox="0 0 48 48" fill="none" className={className} aria-hidden="true">
      <rect x="6" y="10" width="36" height="28" rx="4" stroke="#7de3d1" strokeWidth="2" />
      <path d="M14 18h20M14 24h20M14 30h12" stroke="#2a3350" strokeWidth="2" strokeLinecap="round" />
      <path d="M24 32v-8m0 0l-3.5 3.5M24 24l3.5 3.5" stroke="#f5a3c7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function Dashboard() {
  const toast = useToast()
  const [data, setData] = useState(null)

  // Insights scope: 'all' merges every statement (de-duplicated), 'latest'
  // uses only the newest upload. On mount we fetch the combined view so the
  // dashboard is populated from saved statements without re-uploading.
  const [scope, setScope] = useState('all')
  const [txCount, setTxCount] = useState(null)
  const [insightsMessage, setInsightsMessage] = useState("")
  const [switchingScope, setSwitchingScope] = useState(false)

  async function loadInsights(nextScope) {
    setSwitchingScope(true)
    try {
      const res = await api(`/insights?scope=${nextScope}`)
      if (res.analysis) {
        setData(res.analysis)
        setTxCount(res.transactions_count)
        setInsightsMessage("")
      } else {
        setData(null)
        setTxCount(0)
        setInsightsMessage(res.message || "No transactions available for this scope.")
      }
      setScope(nextScope)
    } catch (err) {
      toast.error(err.message)
    } finally {
      setSwitchingScope(false)
    }
  }

  useEffect(() => {
    loadInsights('all')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const chartData = data
    ? Object.entries(data.category_totals).map(([category, amount]) => ({ category, amount }))
    : []

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white">Dashboard</h1>
            <p className="text-gray-400 mt-1">Upload a statement to see your spending insights</p>
          </div>

          {/* All statements (merged + de-duplicated) vs newest upload only */}
          <div className="flex items-center gap-3">
            {txCount !== null && (
              <span className="text-gray-500 text-sm">
                {txCount} transaction{txCount === 1 ? "" : "s"}
              </span>
            )}
            <div
              className="inline-flex rounded-xl border border-gray-700 overflow-hidden text-sm"
              role="group"
              aria-label="Insights scope"
            >
              <button
                type="button"
                onClick={() => loadInsights('all')}
                disabled={switchingScope}
                aria-pressed={scope === 'all'}
                className={`px-4 py-2 transition-colors disabled:opacity-60 ${
                  scope === 'all'
                    ? 'bg-mint text-navy font-semibold'
                    : 'bg-navy text-gray-300 hover:text-white'
                }`}
              >
                All statements
              </button>
              <button
                type="button"
                onClick={() => loadInsights('latest')}
                disabled={switchingScope}
                aria-pressed={scope === 'latest'}
                className={`px-4 py-2 transition-colors disabled:opacity-60 ${
                  scope === 'latest'
                    ? 'bg-mint text-navy font-semibold'
                    : 'bg-navy text-gray-300 hover:text-white'
                }`}
              >
                Latest only
              </button>
            </div>
          </div>
        </div>

        {/* Statement upload: drag-drop, preview-confirm, password & mapping recovery */}
        <UploadStatement onImported={setData} />

        {!data && insightsMessage && (
          <Card>
            <p className="text-gray-400">{insightsMessage}</p>
          </Card>
        )}

        {!data && !insightsMessage && (
          <Card>
            <EmptyState
              icon={<UploadIcon />}
              title="No statement analyzed yet"
              description="Upload a bank statement above — CSV, Excel or PDF — and you'll see where your money goes, month by month, with categories sorted automatically."
            />
          </Card>
        )}

        {data && (
          <div className="space-y-6">
            {/* Savings summary */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <StatCard label="Income" value={formatINR(data.savings_summary.total_income)} accent="text-mint" />
              <StatCard label="Spend" value={formatINR(data.savings_summary.total_spend)} accent="text-coral" />
              <StatCard label="Saved" value={formatINR(data.savings_summary.total_saved)} />
              <StatCard label="Savings Rate" value={`${data.savings_summary.savings_rate_pct}%`} accent="text-mint" />
            </div>

            {/* Category chart */}
            <Card title="Spending by Category">
              {chartData.length === 0 ? (
                <p className="text-gray-400">No categorized spending yet.</p>
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2a3350" />
                    {/* interval={0} keeps every category label visible; short
                        labels wrap to two lines on 375px-wide screens. */}
                    <XAxis dataKey="category" tick={{ fill: "#9ca3af", fontSize: 11 }} interval={0} angle={chartData.length > 5 ? -30 : 0} textAnchor={chartData.length > 5 ? "end" : "middle"} height={chartData.length > 5 ? 60 : 30} />
                    <YAxis tick={{ fill: "#9ca3af", fontSize: 12 }} width={45} tickFormatter={formatINRCompact} />
                    <Tooltip
                      contentStyle={{ background: "#1a2133", border: "1px solid #2a3350", borderRadius: 8 }}
                      labelStyle={{ color: "#fff" }}
                      formatter={(value) => [formatINR(value), "Spent"]}
                    />
                    <Bar dataKey="amount" radius={[6, 6, 0, 0]} maxBarSize={48}>
                      {chartData.map((entry, i) => (
                        <Cell key={i} fill={CATEGORY_COLORS[entry.category] || CATEGORY_COLOR_PALETTE[i % CATEGORY_COLOR_PALETTE.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Card>

            <div className="grid sm:grid-cols-2 gap-6">
              {/* Forecast */}
              <Card title="Next Month Forecast">
                {data.forecast.error ? (
                  <p className="text-gray-400">{data.forecast.error}</p>
                ) : (
                  <div>
                    <p className="text-3xl font-bold text-white mb-1">
                      {formatINR(data.forecast.predicted_next_month_spend)}
                    </p>
                    <p className="text-gray-400 text-sm">
                      Based on {data.forecast.based_on_months} months of data
                      {data.forecast.low_confidence && " — low confidence, more data will improve this"}
                    </p>
                  </div>
                )}
              </Card>

              {/* Uncategorized */}
              <Card title="Uncategorized Transactions">
                <p className="text-gray-300">{data.uncategorized.message}</p>
              </Card>
            </div>

            {/* Anomalies */}
            {data.anomalies.length > 0 && (
              <Card title="Anomalies">
                <ul className="space-y-2">
                  {data.anomalies.map((a, i) => (
                    <li key={i} className="flex flex-wrap justify-between items-center gap-x-4 gap-y-1 bg-navy rounded-xl px-4 py-3">
                      <span className="text-gray-300">
                        {a.category} — {a.month}
                      </span>
                      <span className="text-coral font-semibold">
                        {formatINR(a.amount)} (+{a.pct_increase}% vs avg)
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            {/* Month-over-month trend */}
            {data.month_over_month_trend.length > 0 && (
              <Card title="Month-over-Month Trend">
                <ul className="space-y-2">
                  {data.month_over_month_trend.map((t, i) => (
                    <li key={i} className="flex flex-wrap justify-between items-center gap-x-4 gap-y-1 bg-navy rounded-xl px-4 py-3">
                      <span className="text-gray-300">{t.category}</span>
                      <span className={t.pct_change >= 0 ? "text-coral font-semibold" : "text-mint font-semibold"}>
                        {t.pct_change >= 0 ? "+" : ""}{t.pct_change}% ({formatINR(t.previous_amount)} → {formatINR(t.latest_amount)})
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            {/* Recurring subscriptions */}
            {data.subscriptions.length > 0 && (
              <Card title="Recurring Subscriptions & Bills">
                <ul className="space-y-2">
                  {data.subscriptions.map((s, i) => (
                    <li key={i} className="flex flex-wrap justify-between items-center gap-x-4 gap-y-1 bg-navy rounded-xl px-4 py-3">
                      <div>
                        <span className="text-gray-200 font-medium">{s.merchant}</span>
                        <span className="text-gray-500 text-sm ml-2">{s.category}</span>
                      </div>
                      <div className="text-right">
                        <p className="text-white font-semibold">{formatINR(s.average_amount)}/mo</p>
                        <p className="text-gray-500 text-xs">{formatINR(s.estimated_annual_cost)}/yr</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            {/* Suggestions */}
            <Card title="Suggestions">
              <ul className="space-y-2">
                {data.suggestions.map((s, i) => (
                  <li key={i} className="text-gray-300 bg-navy rounded-xl px-4 py-3">
                    {s}
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        )}
      </div>
    </AppShell>
  )
}

/* ToastProvider lives at the page level so the useToast hook works here
   without adding a global wrapper to App.jsx. */
export default function DashboardPage() {
  return (
    <ToastProvider>
      <Dashboard />
    </ToastProvider>
  )
}
