import { useState, useEffect } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend,
} from 'recharts'
import AppShell from '../components/AppShell'
import { SkeletonCard } from '../components/UI'
import { useToast } from '../components/ToastContext'
import { api } from '../api'
import { API_BASE } from '../config'
import { formatINR, formatINRCompact } from '../utils/format'

const PRESETS = [
  { id: 'this_month', label: 'This Month' },
  { id: 'last_month', label: 'Last Month' },
  { id: 'last_30_days', label: 'Last 30 Days' },
  { id: 'last_90_days', label: 'Last 90 Days' },
  { id: 'this_year', label: 'This Year' },
  { id: 'custom', label: 'Custom' },
]

function getPresetDates(presetId) {
  const today = new Date()
  const year = today.getFullYear()
  const month = today.getMonth() // 0-indexed

  if (presetId === 'this_month') {
    const start = new Date(year, month, 1)
    return {
      start: start.toISOString().split('T')[0],
      end: today.toISOString().split('T')[0],
    }
  }

  if (presetId === 'last_month') {
    const start = new Date(year, month - 1, 1)
    const end = new Date(year, month, 0)
    return {
      start: start.toISOString().split('T')[0],
      end: end.toISOString().split('T')[0],
    }
  }

  if (presetId === 'last_30_days') {
    const start = new Date(today)
    start.setDate(today.getDate() - 30)
    return {
      start: start.toISOString().split('T')[0],
      end: today.toISOString().split('T')[0],
    }
  }

  if (presetId === 'last_90_days') {
    const start = new Date(today)
    start.setDate(today.getDate() - 90)
    return {
      start: start.toISOString().split('T')[0],
      end: today.toISOString().split('T')[0],
    }
  }

  if (presetId === 'this_year') {
    const start = new Date(year, 0, 1)
    return {
      start: start.toISOString().split('T')[0],
      end: today.toISOString().split('T')[0],
    }
  }

  return {
    start: new Date(year, month, 1).toISOString().split('T')[0],
    end: today.toISOString().split('T')[0],
  }
}

const CATEGORY_PALETTE = [
  '#7de3d1', '#f5a3c7', '#4fc9b3', '#ea7bab', '#a3c9f5', '#e3d17d',
  '#c7a3f5', '#7de3a3', '#f5b8a3', '#a3f5e3', '#f5a3a3', '#d17de3',
]

export default function Reports() {
  const toast = useToast()
  const [activePreset, setActivePreset] = useState('this_month')
  const defaultDates = getPresetDates('this_month')
  const [startDate, setStartDate] = useState(defaultDates.start)
  const [endDate, setEndDate] = useState(defaultDates.end)

  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)
  const [downloadingCsv, setDownloadingCsv] = useState(false)
  const [downloadingPdf, setDownloadingPdf] = useState(false)

  useEffect(() => {
    let ignore = false
    api(`/reports/summary?start_date=${startDate}&end_date=${endDate}`)
      .then((res) => {
        if (!ignore) {
          setData(res)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!ignore) {
          toast.error(err.message || 'Failed to generate financial report')
          setLoading(false)
        }
      })
    return () => {
      ignore = true
    }
  }, [startDate, endDate, toast])

  function handlePresetClick(presetId) {
    setActivePreset(presetId)
    if (presetId !== 'custom') {
      const dates = getPresetDates(presetId)
      setLoading(true)
      setStartDate(dates.start)
      setEndDate(dates.end)
    }
  }

  async function handleDownloadCsv() {
    setDownloadingCsv(true)
    try {
      const token = localStorage.getItem('token')
      const url = `${API_BASE}/reports/export/csv?start_date=${startDate}&end_date=${endDate}`
      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!resp.ok) throw new Error('CSV export failed')
      const blob = await resp.blob()
      const downloadUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = `paisaclarity_transactions_${startDate}_${endDate}.csv`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(downloadUrl)
      toast.success('Transaction CSV exported successfully')
    } catch (err) {
      toast.error(err.message || 'Failed to download CSV')
    } finally {
      setDownloadingCsv(false)
    }
  }

  async function handleDownloadPdf() {
    setDownloadingPdf(true)
    try {
      const token = localStorage.getItem('token')
      const url = `${API_BASE}/reports/export/pdf?start_date=${startDate}&end_date=${endDate}`
      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!resp.ok) throw new Error('PDF export failed')
      const blob = await resp.blob()
      const downloadUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = `paisaclarity_financial_report_${startDate}_${endDate}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(downloadUrl)
      toast.success('Executive Financial Report PDF downloaded')
    } catch (err) {
      toast.error(err.message || 'Failed to download PDF')
    } finally {
      setDownloadingPdf(false)
    }
  }

  return (
    <AppShell>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Top Header & Export Action Buttons */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white tracking-tight">Financial Reports</h1>
            <p className="text-gray-400 mt-1">
              Consolidated, server-verified income, expense, cash flow, and asset reports.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleDownloadCsv}
              disabled={downloadingCsv || loading}
              className="inline-flex items-center gap-2 px-4 py-2 bg-navy-light hover:bg-navy-light/80 text-white border border-gray-700 font-medium rounded-xl text-sm transition-colors disabled:opacity-50"
            >
              <svg className="w-4 h-4 text-mint" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              {downloadingCsv ? 'Exporting...' : 'Export CSV'}
            </button>

            <button
              type="button"
              onClick={handleDownloadPdf}
              disabled={downloadingPdf || loading}
              className="inline-flex items-center gap-2 px-4 py-2 bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl text-sm transition-colors disabled:opacity-50 shadow-md"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
              </svg>
              {downloadingPdf ? 'Generating PDF...' : 'Download PDF Report'}
            </button>
          </div>
        </div>

        {/* Date Filter Bar & Presets */}
        <div className="bg-navy-light rounded-2xl p-5 border border-gray-800 shadow-lg space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-wider font-semibold text-gray-400 mr-2">
              Period Preset:
            </span>
            {PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => handlePresetClick(p.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  activePreset === p.id
                    ? 'bg-mint text-navy font-semibold'
                    : 'bg-navy/70 text-gray-300 hover:bg-navy hover:text-white'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-4 pt-2 border-t border-gray-800/80">
            <div className="flex items-center gap-2">
              <label htmlFor="report-start" className="text-xs text-gray-400">
                From:
              </label>
              <input
                id="report-start"
                type="date"
                value={startDate}
                onChange={(e) => {
                  setLoading(true)
                  setStartDate(e.target.value)
                  setActivePreset('custom')
                }}
                className="bg-navy border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
              />
            </div>

            <div className="flex items-center gap-2">
              <label htmlFor="report-end" className="text-xs text-gray-400">
                To:
              </label>
              <input
                id="report-end"
                type="date"
                value={endDate}
                onChange={(e) => {
                  setLoading(true)
                  setEndDate(e.target.value)
                  setActivePreset('custom')
                }}
                className="bg-navy border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
              />
            </div>

            {data?.period && (
              <span className="text-xs text-gray-400 ml-auto">
                Selected: <b className="text-gray-200">{data.period.days_count} days</b> ({data.period.start_date} to {data.period.end_date})
              </span>
            )}
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <SkeletonCard lines={2} />
              <SkeletonCard lines={2} />
              <SkeletonCard lines={2} />
              <SkeletonCard lines={2} />
            </div>
            <SkeletonCard lines={6} />
          </div>
        )}

        {/* Content */}
        {!loading && data && (
          <>
            {/* Executive KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-navy-light rounded-2xl p-5 border border-gray-800 shadow-sm">
                <p className="text-xs uppercase tracking-wider font-semibold text-gray-400 mb-1">
                  Total Income
                </p>
                <p className="text-2xl font-bold text-mint">
                  {formatINR(data.summary.total_income)}
                </p>
                <p className="text-xs text-gray-400 mt-2">Verified credits</p>
              </div>

              <div className="bg-navy-light rounded-2xl p-5 border border-gray-800 shadow-sm">
                <p className="text-xs uppercase tracking-wider font-semibold text-gray-400 mb-1">
                  Total Expenses
                </p>
                <p className="text-2xl font-bold text-white">
                  {formatINR(data.summary.total_expenses)}
                </p>
                <p className="text-xs text-gray-400 mt-2">
                  Excludes transfers & overlaps ({data.summary.transaction_count} txns)
                </p>
              </div>

              <div className="bg-navy-light rounded-2xl p-5 border border-gray-800 shadow-sm">
                <p className="text-xs uppercase tracking-wider font-semibold text-gray-400 mb-1">
                  Net Cash Flow
                </p>
                <p
                  className={`text-2xl font-bold ${
                    data.summary.net_cash_flow >= 0 ? 'text-mint' : 'text-coral'
                  }`}
                >
                  {formatINR(data.summary.net_cash_flow)}
                </p>
                <p className="text-xs text-gray-400 mt-2">
                  Savings rate:{' '}
                  <b className="text-white">{data.summary.savings_rate_pct}%</b>
                </p>
              </div>

              <div className="bg-navy-light rounded-2xl p-5 border border-gray-800 shadow-sm">
                <div className="flex items-center justify-between">
                  <p className="text-xs uppercase tracking-wider font-semibold text-gray-400 mb-1">
                    Liquid Net Worth
                  </p>
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-mint/10 text-mint font-semibold">
                    Verified
                  </span>
                </div>
                <p className="text-2xl font-bold text-mint">
                  {formatINR(data.net_worth.verified_liquid_balance)}
                </p>
                {data.net_worth.unreconciled_placeholder_balance > 0 && (
                  <p className="text-[11px] text-amber-400 mt-1" title="Unreconciled balances are excluded from verified net worth">
                    ⚠ {formatINR(data.net_worth.unreconciled_placeholder_balance)} unverified
                  </p>
                )}
              </div>
            </div>

            {/* Financial Transparency Callout Banner */}
            <div className="bg-navy-light/60 border border-gray-800 rounded-2xl p-4 text-xs text-gray-400 flex items-start gap-3">
              <svg className="w-5 h-5 text-mint shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="font-semibold text-gray-200">Financial Data Transparency Note</p>
                <p className="mt-0.5 text-gray-400 leading-relaxed">
                  All figures shown above are computed from server-side verified transactions. Internal transfers between your own accounts and duplicate statement entries are excluded to prevent double-counting. Unreconciled imported account balances are strictly isolated from your verified net worth.
                </p>
              </div>
            </div>

            {/* Category Spending Breakdown Chart & Table */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-7 bg-navy-light rounded-2xl p-6 border border-gray-800 shadow-sm flex flex-col">
                <h2 className="text-lg font-bold text-white mb-1">Category Spending</h2>
                <p className="text-xs text-gray-400 mb-6">Distribution of expenses across categories</p>

                {data.category_breakdown.length > 0 ? (
                  <div className="w-full h-80 min-h-[320px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={data.category_breakdown.slice(0, 8)}
                        layout="vertical"
                        margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="#2a3350" horizontal={false} />
                        <XAxis
                          type="number"
                          tickFormatter={(v) => formatINRCompact(v)}
                          stroke="#6b7280"
                          tick={{ fill: '#9ca3af', fontSize: 11 }}
                        />
                        <YAxis
                          type="category"
                          dataKey="category"
                          stroke="#6b7280"
                          tick={{ fill: '#d1d5db', fontSize: 11 }}
                          width={90}
                        />
                        <Tooltip
                          content={({ active, payload }) => {
                            if (active && payload && payload.length) {
                              const item = payload[0].payload
                              return (
                                <div className="bg-navy border border-gray-700 p-2.5 rounded-lg text-xs shadow-xl">
                                  <p className="font-semibold text-white">{item.category}</p>
                                  <p className="text-mint">{formatINR(item.amount)} ({item.percentage}%)</p>
                                  <p className="text-gray-400">{item.count} transactions</p>
                                </div>
                              )
                            }
                            return null
                          }}
                        />
                        <Bar dataKey="amount" radius={[0, 6, 6, 0]}>
                          {data.category_breakdown.slice(0, 8).map((_, i) => (
                            <Cell key={`cell-${i}`} fill={CATEGORY_PALETTE[i % CATEGORY_PALETTE.length]} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="flex-1 flex items-center justify-center p-8">
                    <p className="text-sm text-gray-400">No expense transactions recorded in this period.</p>
                  </div>
                )}
              </div>

              {/* Category Table */}
              <div className="lg:col-span-5 bg-navy-light rounded-2xl p-6 border border-gray-800 shadow-sm flex flex-col">
                <h2 className="text-lg font-bold text-white mb-1">Breakdown Table</h2>
                <p className="text-xs text-gray-400 mb-4">Detailed category allocations</p>

                <div className="flex-1 overflow-y-auto max-h-80 pr-1 space-y-2">
                  {data.category_breakdown.map((c, i) => (
                    <div
                      key={c.category}
                      className="flex items-center justify-between p-2.5 rounded-xl bg-navy/60 hover:bg-navy text-xs transition-colors"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span
                          className="w-3 h-3 rounded-full shrink-0"
                          style={{ backgroundColor: CATEGORY_PALETTE[i % CATEGORY_PALETTE.length] }}
                        />
                        <span className="font-medium text-gray-200 truncate">{c.category}</span>
                        <span className="text-[10px] text-gray-400">({c.count})</span>
                      </div>
                      <div className="text-right shrink-0">
                        <span className="font-semibold text-white block">{formatINR(c.amount)}</span>
                        <span className="text-[10px] text-gray-400">{c.percentage}%</span>
                      </div>
                    </div>
                  ))}
                  {data.category_breakdown.length === 0 && (
                    <p className="text-sm text-gray-400 text-center py-8">No categorized expenses.</p>
                  )}
                </div>
              </div>
            </div>

            {/* Cash Flow Trends */}
            {data.monthly_trends.length > 1 && (
              <div className="bg-navy-light rounded-2xl p-6 border border-gray-800 shadow-sm">
                <h2 className="text-lg font-bold text-white mb-1">Monthly Cash Flow Trend</h2>
                <p className="text-xs text-gray-400 mb-6">Income vs Expenses over the selected period</p>

                <div className="w-full h-72 min-h-[280px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.monthly_trends} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#2a3350" vertical={false} />
                      <XAxis dataKey="month" stroke="#6b7280" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                      <YAxis stroke="#6b7280" tickFormatter={(v) => formatINRCompact(v)} tick={{ fill: '#9ca3af', fontSize: 11 }} />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (active && payload && payload.length) {
                            const d = payload[0].payload
                            return (
                              <div className="bg-navy border border-gray-700 p-2.5 rounded-lg text-xs shadow-xl">
                                <p className="font-semibold text-white mb-1">{d.month}</p>
                                <p className="text-mint">Income: {formatINR(d.income)}</p>
                                <p className="text-coral">Expenses: {formatINR(d.expense)}</p>
                                <p className="text-gray-300 font-semibold mt-1">Net: {formatINR(d.net)}</p>
                              </div>
                            )
                          }
                          return null
                        }}
                      />
                      <Legend
                        wrapperStyle={{ fontSize: 12, paddingTop: 10 }}
                        formatter={(val) => <span className="text-gray-300 capitalize">{val}</span>}
                      />
                      <Bar dataKey="income" fill="#7de3d1" name="Income" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="expense" fill="#f5a3c7" name="Expenses" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Budgets & Savings Goals Section */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Budgets */}
              <div className="bg-navy-light rounded-2xl p-6 border border-gray-800 shadow-sm flex flex-col">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-bold text-white">Budget Performance</h2>
                  <span className="text-xs text-gray-400">{data.budgets.length} budget(s) in range</span>
                </div>

                <div className="space-y-4 flex-1">
                  {data.budgets.map((b) => (
                    <div key={b.budget_id} className="p-4 rounded-xl bg-navy/60 border border-gray-800 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-white">
                          Budget {b.year}-{String(b.month).padStart(2, '0')}
                        </span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                            b.is_over_budget
                              ? 'bg-coral/10 text-coral'
                              : 'bg-mint/10 text-mint'
                          }`}
                        >
                          {b.total_utilization_pct}% utilized
                        </span>
                      </div>
                      <div className="w-full bg-navy rounded-full h-2 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            b.is_over_budget ? 'bg-coral' : 'bg-mint'
                          }`}
                          style={{ width: `${Math.min(100, b.total_utilization_pct)}%` }}
                        />
                      </div>
                      <div className="flex justify-between text-xs text-gray-400">
                        <span>Spent: {formatINR(b.total_actual_spent)}</span>
                        <span>Limit: {formatINR(b.total_budget_limit)}</span>
                      </div>
                    </div>
                  ))}
                  {data.budgets.length === 0 && (
                    <p className="text-xs text-gray-400 text-center py-6">
                      No active monthly budgets in this date range.
                    </p>
                  )}
                </div>
              </div>

              {/* Savings Goals */}
              <div className="bg-navy-light rounded-2xl p-6 border border-gray-800 shadow-sm flex flex-col">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-bold text-white">Savings Goals</h2>
                  <span className="text-xs text-mint font-semibold">{data.savings_goals.progress_pct}% overall</span>
                </div>

                <div className="space-y-4 flex-1">
                  {data.savings_goals.goals.map((g) => (
                    <div key={g.id} className="p-4 rounded-xl bg-navy/60 border border-gray-800 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-white">{g.name}</span>
                        <span className="text-xs text-mint font-semibold">{g.progress_percentage}%</span>
                      </div>
                      <div className="w-full bg-navy rounded-full h-2 overflow-hidden">
                        <div
                          className="h-full bg-mint rounded-full transition-all"
                          style={{ width: `${Math.min(100, g.progress_percentage)}%` }}
                        />
                      </div>
                      <div className="flex justify-between text-xs text-gray-400">
                        <span>Saved: {formatINR(g.total_saved)}</span>
                        <span>Target: {formatINR(g.target_amount)}</span>
                      </div>
                    </div>
                  ))}
                  {data.savings_goals.goals.length === 0 && (
                    <p className="text-xs text-gray-400 text-center py-6">
                      No active savings goals found.
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Subscriptions & Investments */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Subscriptions */}
              <div className="bg-navy-light rounded-2xl p-6 border border-gray-800 shadow-sm">
                <h2 className="text-lg font-bold text-white mb-1">Recurring Commitments</h2>
                <p className="text-xs text-gray-400 mb-4">Confirmed subscriptions & detected bills</p>

                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="p-3 bg-navy/60 rounded-xl border border-gray-800">
                    <span className="text-[10px] uppercase font-semibold text-gray-400 block">Monthly Commitments</span>
                    <span className="text-lg font-bold text-white block mt-0.5">
                      {formatINR(data.recurring_payments.total_monthly_commitment)}
                    </span>
                  </div>
                  <div className="p-3 bg-navy/60 rounded-xl border border-gray-800">
                    <span className="text-[10px] uppercase font-semibold text-gray-400 block">Status Breakdown</span>
                    <span className="text-xs text-mint block mt-1">
                      {data.recurring_payments.confirmed_count} Confirmed
                    </span>
                    <span className="text-xs text-amber-400 block">
                      {data.recurring_payments.detected_count} Pending Review
                    </span>
                  </div>
                </div>
              </div>

              {/* Investments */}
              <div className="bg-navy-light rounded-2xl p-6 border border-gray-800 shadow-sm">
                <h2 className="text-lg font-bold text-white mb-1">Investment Portfolio</h2>
                <p className="text-xs text-gray-400 mb-4">Total invested across markets and policies</p>

                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="p-3 bg-navy/60 rounded-xl border border-gray-800">
                    <span className="text-[10px] uppercase font-semibold text-gray-400 block">Total Invested</span>
                    <span className="text-lg font-bold text-white block mt-0.5">
                      {formatINR(data.investments.total_invested)}
                    </span>
                  </div>
                  <div className="p-3 bg-navy/60 rounded-xl border border-gray-800">
                    <span className="text-[10px] uppercase font-semibold text-gray-400 block">Asset Allocation</span>
                    <span className="text-xs text-mint block mt-1">
                      Market: {formatINR(data.investments.market_total)}
                    </span>
                    <span className="text-xs text-purple-400 block">
                      Insurance: {formatINR(data.investments.policy_total)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </AppShell>
  )
}
