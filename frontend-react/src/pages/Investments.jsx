import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import AppShell from '../components/AppShell'
import { Card, ConfirmModal, EmptyState, Skeleton, SkeletonCard, StatSkeleton } from '../components/UI'
import { AlertIcon, InfoIcon } from '../components/Icons'
import { ToastProvider } from '../components/Toast'
import { useToast } from '../components/ToastContext'
import { api } from '../api'
import { formatINR, formatINRCompact } from '../utils/format'

const REALITY_CHECK_DISCLAIMER =
  "This is an informational calculation based on the data you've entered — not financial advice, and not a recommendation to keep, switch, or surrender anything. It uses approximations (a reconstructed premium schedule and, for policies still running, an estimated current value) and is not a substitute for your policy's official benefit illustration."

function formatXIRR(pct) {
  return pct === null || pct === undefined ? "—" : `${pct.toFixed(2)}%`
}

/* ------------------------------------------------------------------ */
/* Reality Check: expandable per-policy section (calls the backend      */
/* reality-check endpoint when first opened, then caches the result).   */
/* ------------------------------------------------------------------ */
function RealityCheckSection({ investment }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  async function toggle() {
    const nextOpen = !open
    setOpen(nextOpen)

    if (nextOpen && !data && !loading) {
      setLoading(true)
      setError("")
      try {
        setData(await api(`/investments/${investment.id}/reality-check`))
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
  }

  return (
    <div className="mt-3">
      <button
        onClick={toggle}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 text-mint text-sm hover:underline"
      >
        <svg
          viewBox="0 0 12 12"
          fill="none"
          className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`}
          aria-hidden="true"
        >
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Reality Check
      </button>

      {open && (
        <div className="mt-3 bg-navy rounded-xl p-4">
          {loading && (
            <div className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
              </div>
              <Skeleton className="h-12 w-full" />
            </div>
          )}

          {!loading && error && (
            <p className="flex items-start gap-2 text-coral text-sm">
              <AlertIcon className="w-4 h-4 mt-0.5 shrink-0" />
              {error}
            </p>
          )}

          {!loading && !error && data && (
            <>
              {/* The backend couldn't compute anything usable - show its
                  message instead of empty number slots. */}
              {data.policy_xirr_pct === null && data.benchmark_xirr_pct === null && data.message ? (
                <p className="flex items-start gap-2 text-gray-300 text-sm">
                  <InfoIcon className="w-4 h-4 mt-0.5 shrink-0 text-mint" />
                  {data.message}
                </p>
              ) : (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="border border-gray-700 rounded-lg px-4 py-3">
                      <p className="text-gray-400 text-xs mb-1">This policy's annualized return (XIRR)</p>
                      <p className="text-2xl font-bold text-white">{formatXIRR(data.policy_xirr_pct)}</p>
                      <p className="text-gray-500 text-xs mt-1">
                        {data.num_premiums_counted} premium{data.num_premiums_counted === 1 ? "" : "s"} ·{" "}
                        {formatINR(data.total_premiums_paid)} paid
                      </p>
                    </div>
                    <div className="border border-gray-700 rounded-lg px-4 py-3">
                      <p className="text-gray-400 text-xs mb-1">
                        Same premiums in <span className="text-gray-300">{data.benchmark_fund_name}</span>
                      </p>
                      <p className="text-2xl font-bold text-white">{formatXIRR(data.benchmark_xirr_pct)}</p>
                      <p className="text-gray-500 text-xs mt-1">Annualized return (XIRR) on the same dates and amounts</p>
                    </div>
                  </div>

                  {data.is_estimated_current_value && (
                    <p className="flex items-start gap-2 text-gray-400 text-xs mt-3">
                      <span className="shrink-0 inline-flex items-center gap-1 bg-mint/10 text-mint border border-mint/30 rounded-full px-2 py-0.5 font-medium" title="The policy hasn't matured, so its current value is estimated as the total premiums paid. Actual surrender value is set by your insurer.">
                        <InfoIcon className="w-3 h-3" />
                        Estimated
                      </span>
                      The policy hasn't matured, so its current value is estimated as the total premiums paid — your insurer's actual surrender value will usually differ.
                    </p>
                  )}

                  {data.policy_xirr_pct !== null && data.benchmark_xirr_pct === null && data.message && (
                    <p className="text-gray-400 text-xs mt-2">{data.message}</p>
                  )}
                  {data.policy_xirr_pct === null && data.benchmark_xirr_pct !== null && data.message && (
                    <p className="text-gray-400 text-xs mt-2">{data.message}</p>
                  )}
                </>
              )}

              {/* Disclaimer always visible alongside the numbers */}
              <p className="text-gray-500 text-xs leading-relaxed mt-4 pt-3 border-t border-gray-800">
                {REALITY_CHECK_DISCLAIMER}
              </p>
            </>
          )}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Affordability stress test: premiums due over the next 12 months vs   */
/* the user's average monthly savings from their latest statement.      */
/* ------------------------------------------------------------------ */
function AffordabilityCard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const result = await api('/investments/affordability')
        if (!cancelled) setData(result)
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  if (loading) return <SkeletonCard lines={4} />

  if (error) {
    return (
      <Card title="Premium Affordability — Next 12 Months">
        <p className="flex items-start gap-2 text-coral text-sm">
          <AlertIcon className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </p>
      </Card>
    )
  }

  if (!data.has_statement) {
    return (
      <Card title="Premium Affordability — Next 12 Months">
        <p className="text-gray-400 text-sm leading-relaxed">{data.message}</p>
        <Link
          to="/dashboard"
          className="inline-block mt-4 bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl px-4 py-2 text-sm transition-colors"
        >
          Go to Dashboard
        </Link>
      </Card>
    )
  }

  const hasAnyPremiums = data.months.some((m) => m.premiums_due > 0)
  const thresholdAmount =
    data.average_monthly_savings !== null ? (data.average_monthly_savings * data.threshold_pct) / 100 : null

  return (
    <Card title="Premium Affordability — Next 12 Months">
      <p className="text-gray-400 text-sm mb-4">
        Premiums due each month, compared against your average monthly savings of{" "}
        <span className="text-white font-medium">{formatINR(data.average_monthly_savings)}</span> from your latest
        statement. Months where premiums exceed {data.threshold_pct}% of that are marked tight.
      </p>

      {!hasAnyPremiums ? (
        <p className="text-gray-400 text-sm">
          No upcoming premiums found on your policies — nothing to stress-test yet.
        </p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.months} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3350" />
              <XAxis dataKey="month_label" tick={{ fill: "#9ca3af", fontSize: 10 }} interval={0} angle={-35} textAnchor="end" height={50} />
              <YAxis tick={{ fill: "#9ca3af", fontSize: 11 }} width={45} tickFormatter={formatINRCompact} />
              <Tooltip
                contentStyle={{ background: "#1a2133", border: "1px solid #2a3350", borderRadius: 8 }}
                labelStyle={{ color: "#fff" }}
                formatter={(value) => [formatINR(value), "Premiums due"]}
              />
              {thresholdAmount !== null && thresholdAmount > 0 && (
                <ReferenceLine
                  y={thresholdAmount}
                  stroke="#7de3d1"
                  strokeDasharray="4 4"
                  label={{ value: `${data.threshold_pct}% of savings`, fill: "#7de3d1", fontSize: 10, position: "insideTopRight" }}
                />
              )}
              <Bar dataKey="premiums_due" radius={[6, 6, 0, 0]} maxBarSize={36}>
                {data.months.map((m, i) => (
                  <Cell key={i} fill={m.is_tight ? "#ea7bab" : "#4fc9b3"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          {data.tight_months_count > 0 && (
            <p className="text-gray-400 text-xs mt-3">
              <span className="text-coral font-medium">{data.tight_months_count} tight month{data.tight_months_count === 1 ? "" : "s"}</span>{" "}
              ahead — plan for those premiums in advance.
            </p>
          )}
          {data.policies_counted === 0 && (
            <p className="text-gray-500 text-xs mt-2">
              No policies had a complete premium schedule (amount + next due date), so nothing was counted.
            </p>
          )}
        </>
      )}
    </Card>
  )
}

/* A blank form, shared by both "add new" and "edit" - editing just
   pre-fills these same fields instead of starting from scratch. */
const emptyForm = {
  name: "",
  category: "market",
  invested_amount: "",
  investment_type: "mutual_fund",
  scheme_code: "",
  units: "",
  purchase_date: "",
  start_date: "",
  premium_amount: "",
  premium_frequency: "yearly",
  next_due_date: "",
  maturity_date: "",
  maturity_value: "",
}

function Investments() {
  const toast = useToast()

  const [investments, setInvestments] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null) // null = creating new, otherwise the id being edited
  const [formData, setFormData] = useState(emptyForm)
  const [saving, setSaving] = useState(false)

  // Deletion is confirmed through a styled modal instead of confirm().
  const [pendingDelete, setPendingDelete] = useState(null) // the investment object awaiting confirmation
  const [deleting, setDeleting] = useState(false)

  // Bumping refreshKey re-runs the fetch effect below. Add/Edit/Delete
  // handlers call refresh() instead of duplicating the fetch logic.
  const [refreshKey, setRefreshKey] = useState(0)
  function refresh() {
    setRefreshKey((k) => k + 1)
  }

  useEffect(() => {
    let cancelled = false

    async function fetchAll() {
      try {
        const [investmentsData, summaryData] = await Promise.all([
          api('/investments'),
          api('/investments/summary'),
        ])
        if (cancelled) return
        setInvestments(investmentsData)
        setSummary(summaryData)
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchAll()
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  function handleFieldChange(field, value) {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  function startAdd() {
    setFormData(emptyForm)
    setEditingId(null)
    setShowForm(true)
  }

  function startEdit(investment) {
    // Pre-fill the form with this investment's raw saved fields (not the
    // computed ones like current_value - those aren't editable, they're
    // derived fresh every time from units/scheme_code).
    setFormData({
      name: investment.name || "",
      category: investment.category,
      invested_amount: investment.invested_amount ?? "",
      investment_type: investment.investment_type || "mutual_fund",
      scheme_code: investment.scheme_code || "",
      units: investment.units ?? "",
      purchase_date: investment.purchase_date || "",
      start_date: investment.start_date || "",
      premium_amount: investment.premium_amount ?? "",
      premium_frequency: investment.premium_frequency || "yearly",
      next_due_date: investment.next_due_date || "",
      maturity_date: investment.maturity_date || "",
      maturity_value: investment.maturity_value ?? "",
    })
    setEditingId(investment.id)
    setShowForm(true)
  }

  // Builds the JSON body to send, stripping out fields that don't apply
  // to the chosen category and converting empty strings to null so we
  // don't send invested_amount: "" to a field the backend expects as a
  // number (or nothing at all).
  function buildPayload() {
    const isMarket = formData.category === "market"

    return {
      name: formData.name,
      category: formData.category,
      invested_amount: Number(formData.invested_amount),
      investment_type: isMarket ? formData.investment_type : null,
      scheme_code: isMarket ? formData.scheme_code || null : null,
      units: isMarket && formData.units !== "" ? Number(formData.units) : null,
      purchase_date: isMarket && formData.purchase_date ? formData.purchase_date : null,
      start_date: !isMarket && formData.start_date ? formData.start_date : null,
      premium_amount: !isMarket && formData.premium_amount !== "" ? Number(formData.premium_amount) : null,
      premium_frequency: !isMarket ? formData.premium_frequency : null,
      next_due_date: !isMarket && formData.next_due_date ? formData.next_due_date : null,
      maturity_date: !isMarket && formData.maturity_date ? formData.maturity_date : null,
      maturity_value: !isMarket && formData.maturity_value !== "" ? Number(formData.maturity_value) : null,
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError("")

    try {
      const isEditing = editingId !== null

      await api(isEditing ? `/investments/${editingId}` : '/investments', {
        method: isEditing ? 'PUT' : 'POST',
        body: buildPayload(),
      })

      setShowForm(false)
      toast.success(isEditing ? "Investment updated" : "Investment added")
      refresh() // re-fetch the list/summary with the new data
    } catch (err) {
      setError(err.message)
      toast.error(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id) {
    setDeleting(true)
    try {
      await api(`/investments/${id}`, { method: 'DELETE' })

      toast.success("Investment deleted")
      setPendingDelete(null)
      refresh()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white">Investments</h1>
            <p className="text-gray-400 mt-1">Track market investments and policies in one place</p>
          </div>
          <button
            onClick={startAdd}
            className="bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl px-4 py-2 text-sm transition-colors self-start sm:self-auto whitespace-nowrap"
          >
            + Add Investment
          </button>
        </div>

        {error && (
          <p className="flex items-start gap-2 text-coral text-sm bg-coral/10 border border-coral/30 rounded-lg px-4 py-2 mb-6">
            <AlertIcon className="w-4 h-4 mt-0.5 shrink-0" />
            {error}
          </p>
        )}

        {loading && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {[0, 1, 2, 3].map((i) => <StatSkeleton key={i} />)}
            </div>
            <SkeletonCard lines={4} />
          </div>
        )}

        {!loading && summary && (
          <>
            {/* Portfolio summary */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
              <div className="bg-navy-light rounded-2xl p-4 sm:p-6 shadow-lg">
                <p className="text-gray-400 text-sm mb-1">Net Worth</p>
                <p className="text-2xl font-bold text-white">{formatINR(summary.net_worth)}</p>
              </div>
              <div className="bg-navy-light rounded-2xl p-4 sm:p-6 shadow-lg">
                <p className="text-gray-400 text-sm mb-1">Total Invested</p>
                <p className="text-2xl font-bold text-white">{formatINR(summary.total_invested)}</p>
              </div>
              <div className="bg-navy-light rounded-2xl p-4 sm:p-6 shadow-lg">
                <p className="text-gray-400 text-sm mb-1">Gain / Loss</p>
                <p className={`text-2xl font-bold ${summary.total_gain_loss >= 0 ? "text-mint" : "text-coral"}`}>
                  {formatINR(summary.total_gain_loss)}
                </p>
              </div>
              <div className="bg-navy-light rounded-2xl p-4 sm:p-6 shadow-lg">
                <p className="text-gray-400 text-sm mb-1">Market / Policy</p>
                <p className="text-lg font-semibold text-white">
                  {formatINR(summary.breakdown_by_category.market)} / {formatINR(summary.breakdown_by_category.policy)}
                </p>
              </div>
            </div>

            {/* Upcoming dues reminder banner */}
            {summary.upcoming_dues.length > 0 && (
              <Card title="Upcoming Payments Due" className="mb-6 border border-coral/30">
                <ul className="space-y-2">
                  {summary.upcoming_dues.map((d) => (
                    <li key={d.id} className="flex flex-wrap justify-between items-center gap-x-4 gap-y-1 bg-navy rounded-xl px-4 py-3">
                      <span className="text-gray-200">{d.name}</span>
                      <span className={d.is_overdue ? "text-coral font-semibold" : "text-white"}>
                        {d.is_overdue
                          ? `Overdue by ${Math.abs(d.days_until_due)} day(s)`
                          : `Due in ${d.days_until_due} day(s)`} · {formatINR(d.premium_amount)}
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </>
        )}

        {/* Affordability stress test across all policies */}
        {!loading && <div className="mb-6"><AffordabilityCard /></div>}

        {/* Add/Edit form */}
        {showForm && (
          <Card title={editingId ? "Edit Investment" : "Add Investment"} className="mb-6">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-300 mb-1.5">Type</label>
                  {/* Disabled while editing - changing category on an existing
                      row would mix up which fields are meaningful, so we only
                      allow choosing it when creating new. */}
                  <select
                    value={formData.category}
                    onChange={(e) => handleFieldChange("category", e.target.value)}
                    disabled={editingId !== null}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white disabled:opacity-50"
                  >
                    <option value="market">Market Investment (stock / mutual fund)</option>
                    <option value="policy">Policy (insurance / recurring SIP)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm text-gray-300 mb-1.5">Name</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => handleFieldChange("name", e.target.value)}
                    required
                    placeholder={formData.category === "market" ? "HDFC Top 100 Fund" : "LIC Jeevan Anand"}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white placeholder-gray-500"
                  />
                </div>

                <div>
                  <label className="block text-sm text-gray-300 mb-1.5">Invested Amount (₹)</label>
                  <input
                    type="number"
                    value={formData.invested_amount}
                    onChange={(e) => handleFieldChange("invested_amount", e.target.value)}
                    required
                    className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white"
                  />
                </div>
              </div>

              {/* --- Market-only fields --- */}
              {formData.category === "market" && (
                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-300 mb-1.5">Investment Type</label>
                    <select
                      value={formData.investment_type}
                      onChange={(e) => handleFieldChange("investment_type", e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white"
                    >
                      <option value="mutual_fund">Mutual Fund</option>
                      <option value="stock">Stock</option>
                    </select>
                  </div>

                  {formData.investment_type === "mutual_fund" && (
                    <div>
                      <label className="block text-sm text-gray-300 mb-1.5">
                        AMFI Scheme Code
                        <span className="text-gray-500 font-normal"> (needed for live price - find it on mfapi.in)</span>
                      </label>
                      <input
                        type="text"
                        value={formData.scheme_code}
                        onChange={(e) => handleFieldChange("scheme_code", e.target.value)}
                        placeholder="125497"
                        className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white placeholder-gray-500"
                      />
                    </div>
                  )}

                  <div>
                    <label className="block text-sm text-gray-300 mb-1.5">Units</label>
                    <input
                      type="number"
                      value={formData.units}
                      onChange={(e) => handleFieldChange("units", e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white"
                    />
                  </div>

                  <div>
                    <label className="block text-sm text-gray-300 mb-1.5">Purchase Date</label>
                    <input
                      type="date"
                      value={formData.purchase_date}
                      onChange={(e) => handleFieldChange("purchase_date", e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white"
                    />
                  </div>
                </div>
              )}

              {/* --- Policy-only fields --- */}
              {formData.category === "policy" && (
                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-300 mb-1.5">Start Date</label>
                    <input
                      type="date"
                      value={formData.start_date}
                      onChange={(e) => handleFieldChange("start_date", e.target.value)}
                      required={editingId === null}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white"
                    />
                    <p className="text-gray-500 text-xs mt-1">
                      When the policy began - the Reality Check reconstructs your premium payments from this.
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm text-gray-300 mb-1.5">Premium Amount (₹)</label>
                    <input
                      type="number"
                      value={formData.premium_amount}
                      onChange={(e) => handleFieldChange("premium_amount", e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white"
                    />
                  </div>

                  <div>
                    <label className="block text-sm text-gray-300 mb-1.5">Premium Frequency</label>
                    <select
                      value={formData.premium_frequency}
                      onChange={(e) => handleFieldChange("premium_frequency", e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white"
                    >
                      <option value="monthly">Monthly</option>
                      <option value="quarterly">Quarterly</option>
                      <option value="yearly">Yearly</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm text-gray-300 mb-1.5">Next Due Date</label>
                    <input
                      type="date"
                      value={formData.next_due_date}
                      onChange={(e) => handleFieldChange("next_due_date", e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white"
                    />
                  </div>

                  <div>
                    <label className="block text-sm text-gray-300 mb-1.5">Maturity Date</label>
                    <input
                      type="date"
                      value={formData.maturity_date}
                      onChange={(e) => handleFieldChange("maturity_date", e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white"
                    />
                  </div>

                  <div>
                    <label className="block text-sm text-gray-300 mb-1.5">Maturity Value (₹)</label>
                    <input
                      type="number"
                      value={formData.maturity_value}
                      onChange={(e) => handleFieldChange("maturity_value", e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-4 py-2.5 text-white"
                    />
                  </div>
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl px-6 py-2.5 transition-colors disabled:opacity-60"
                >
                  {saving ? "Saving..." : editingId ? "Save Changes" : "Add Investment"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="bg-navy border border-gray-700 hover:border-gray-500 text-gray-300 rounded-xl px-6 py-2.5 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </form>
          </Card>
        )}

        {/* Investment list */}
        {!loading && investments.length === 0 && !showForm && (
          <Card>
            <EmptyState
              icon={
                <svg viewBox="0 0 48 48" fill="none" className="w-12 h-12" aria-hidden="true">
                  <path d="M6 36l10-11 7 6 12-14" stroke="#7de3d1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M28 17h7v7" stroke="#7de3d1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M6 42h36" stroke="#2a3350" strokeWidth="2" strokeLinecap="round" />
                </svg>
              }
              title="No investments yet"
              description="Add the mutual funds, stocks, and insurance policies you already own to see them in one place, with live prices and premium reminders."
              action={
                <button
                  onClick={startAdd}
                  className="bg-mint hover:bg-mint-dark text-navy font-semibold rounded-xl px-5 py-2.5 text-sm transition-colors"
                >
                  + Add your first investment
                </button>
              }
            />
          </Card>
        )}

        {!loading && investments.length > 0 && (
          <Card title="Your Investments">
            <ul className="space-y-3">
              {investments.map((inv) => (
                <li key={inv.id} className="bg-navy rounded-xl px-4 py-4">
                  <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-2">
                    <div>
                      <p className="text-white font-medium">{inv.name}</p>
                      <p className="text-gray-500 text-sm">
                        {inv.category === "market" ? inv.investment_type : "Policy"}
                        {inv.category === "policy" && inv.next_due_date && (
                          <span className={inv.is_overdue ? "text-coral" : ""}>
                            {" · "}
                            {inv.is_overdue
                              ? `Overdue by ${Math.abs(inv.days_until_due)} day(s)`
                              : `Due in ${inv.days_until_due} day(s)`}
                          </span>
                        )}
                      </p>
                    </div>
                    <div className="sm:text-right">
                      {inv.category === "market" ? (
                        <>
                          <p className="text-white font-semibold">
                            {inv.current_value !== null ? formatINR(inv.current_value) : formatINR(inv.invested_amount)}
                          </p>
                          {inv.gain_loss !== null && (
                            <p className={`text-sm ${inv.gain_loss >= 0 ? "text-mint" : "text-coral"}`}>
                              {inv.gain_loss >= 0 ? "+" : ""}{formatINR(inv.gain_loss)} ({inv.gain_loss_pct}%)
                            </p>
                          )}
                        </>
                      ) : (
                        <p className="text-white font-semibold">{formatINR(inv.invested_amount)} invested</p>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-3">
                    <button
                      onClick={() => startEdit(inv)}
                      className="text-mint text-sm hover:underline"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => setPendingDelete(inv)}
                      className="text-coral text-sm hover:underline"
                    >
                      Delete
                    </button>
                    {inv.category === "policy" && <RealityCheckSection investment={inv} />}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {/* Styled delete confirmation (replaces the native confirm() dialog) */}
      <ConfirmModal
        open={pendingDelete !== null}
        title="Delete investment?"
        message={
          pendingDelete
            ? `"${pendingDelete.name}" will be permanently removed from your portfolio. This can't be undone.`
            : ""
        }
        confirmLabel={deleting ? "Deleting..." : "Delete"}
        danger
        onConfirm={() => handleDelete(pendingDelete.id)}
        onCancel={() => setPendingDelete(null)}
      />
    </AppShell>
  )
}

/* ToastProvider lives at the page level so the useToast hook works here
   without adding a global wrapper to App.jsx. */
export default function InvestmentsPage() {
  return (
    <ToastProvider>
      <Investments />
    </ToastProvider>
  )
}
