import { useState, useEffect, useCallback } from 'react'
import AppShell from '../components/AppShell'
import { Card, Skeleton, ConfirmModal, EmptyState } from '../components/UI'
import { api, ApiError } from '../api'
import { formatINR } from '../utils/format'

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
]

const DEFAULT_CATEGORIES = [
  'Food', 'Groceries', 'Rent', 'Utilities', 'Bills', 'Shopping',
  'Transport', 'Travel', 'Entertainment', 'Health', 'Education', 'Other'
]

export default function Budgets() {
  const today = new Date()
  const [selectedMonth, setSelectedMonth] = useState(today.getMonth() + 1)
  const [selectedYear, setSelectedYear] = useState(today.getFullYear())

  const [budget, setBudget] = useState(null)
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Modal states
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState(null)

  // Form states
  const [totalLimit, setTotalLimit] = useState('')
  const [warningThreshold, setWarningThreshold] = useState('80')
  const [allocations, setAllocations] = useState([])

  // Load categories
  useEffect(() => {
    async function loadCategories() {
      try {
        const data = await api('/categories')
        if (data && data.length > 0) {
          const expenseCats = data.filter((c) => c.category_type === 'expense').map((c) => c.name)
          setCategories(expenseCats.length > 0 ? expenseCats : DEFAULT_CATEGORIES)
        } else {
          setCategories(DEFAULT_CATEGORIES)
        }
      } catch {
        setCategories(DEFAULT_CATEGORIES)
      }
    }
    loadCategories()
  }, [])

  // Fetch Budget for selected month/year
  const fetchBudget = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await api(`/budgets?month=${selectedMonth}&year=${selectedYear}`)
      if (data && data.length > 0) {
        setBudget(data[0])
      } else {
        setBudget(null)
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load budget')
    } finally {
      setLoading(false)
    }
  }, [selectedMonth, selectedYear])

  useEffect(() => {
    let ignore = false
    api(`/budgets?month=${selectedMonth}&year=${selectedYear}`)
      .then((data) => {
        if (!ignore) {
          setError(null)
          if (data && data.length > 0) {
            setBudget(data[0])
          } else {
            setBudget(null)
          }
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err instanceof ApiError ? err.message : 'Failed to load budget')
          setLoading(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [selectedMonth, selectedYear])

  // Navigation handlers
  function handlePrevMonth() {
    if (selectedMonth === 1) {
      setSelectedMonth(12)
      setSelectedYear((y) => y - 1)
    } else {
      setSelectedMonth((m) => m - 1)
    }
  }

  function handleNextMonth() {
    if (selectedMonth === 12) {
      setSelectedMonth(1)
      setSelectedYear((y) => y + 1)
    } else {
      setSelectedMonth((m) => m + 1)
    }
  }

  // Open Create / Edit Modal
  function handleOpenModal() {
    setActionError(null)
    if (budget) {
      setTotalLimit(budget.total_budget_limit ? String(budget.total_budget_limit) : '')
      setWarningThreshold(budget.warning_threshold ? String(budget.warning_threshold) : '80')
      setAllocations(
        budget.allocations.map((a) => ({
          category_name: a.category_name,
          allocated_amount: String(a.allocated_amount),
          notes: a.notes || '',
        }))
      )
    } else {
      setTotalLimit('')
      setWarningThreshold('80')
      setAllocations([
        { category_name: 'Food', allocated_amount: '10000', notes: '' },
        { category_name: 'Rent', allocated_amount: '20000', notes: '' },
        { category_name: 'Utilities', allocated_amount: '5000', notes: '' },
      ])
    }
    setEditModalOpen(true)
  }

  function handleAddAllocationRow() {
    const existing = new Set(allocations.map((a) => a.category_name.toLowerCase()))
    const nextCat = categories.find((c) => !existing.has(c.toLowerCase())) || 'Other'
    setAllocations([...allocations, { category_name: nextCat, allocated_amount: '0', notes: '' }])
  }

  function handleRemoveAllocationRow(index) {
    setAllocations(allocations.filter((_, i) => i !== index))
  }

  function handleAllocationChange(index, field, value) {
    const updated = [...allocations]
    updated[index][field] = value
    setAllocations(updated)
  }

  // Submit Create or Update
  async function handleSaveBudget(e) {
    e.preventDefault()
    try {
      setActionLoading(true)
      setActionError(null)

      const payload = {
        total_budget_limit: totalLimit.trim() ? Number(totalLimit) : null,
        warning_threshold: Number(warningThreshold) || 80,
        allocations: allocations.map((a) => ({
          category_name: a.category_name.trim(),
          allocated_amount: Number(a.allocated_amount) || 0,
          notes: a.notes?.trim() || null,
        })),
      }

      if (budget) {
        await api(`/budgets/${budget.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      } else {
        await api('/budgets', {
          method: 'POST',
          body: JSON.stringify({
            month: selectedMonth,
            year: selectedYear,
            ...payload,
          }),
        })
      }

      setEditModalOpen(false)
      fetchBudget()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Failed to save budget')
    } finally {
      setActionLoading(false)
    }
  }

  // Delete budget
  async function handleDeleteBudget() {
    if (!budget) return
    try {
      setActionLoading(true)
      await api(`/budgets/${budget.id}`, { method: 'DELETE' })
      setDeleteModalOpen(false)
      fetchBudget()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete budget')
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header and Month Navigator */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Monthly Budgets</h1>
            <p className="text-sm text-gray-400 mt-1">
              Plan category spending limits and monitor utilization in real-time.
            </p>
          </div>

          <div className="flex items-center gap-3">
            {/* Month / Year Selector Controls */}
            <div className="flex items-center bg-navy-light rounded-xl p-1 border border-navy/60">
              <button
                onClick={handlePrevMonth}
                className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-navy transition-colors"
                title="Previous Month"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <div className="px-3 py-1 text-sm font-semibold text-white whitespace-nowrap">
                {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
              </div>
              <button
                onClick={handleNextMonth}
                className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-navy transition-colors"
                title="Next Month"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>

            {budget ? (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleOpenModal}
                  className="px-4 py-2 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors shadow-sm"
                >
                  Edit Budget
                </button>
                <button
                  onClick={() => setDeleteModalOpen(true)}
                  className="p-2 text-rose-400 hover:text-white hover:bg-rose-500/20 rounded-xl transition-colors"
                  title="Delete Budget"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            ) : (
              <button
                onClick={handleOpenModal}
                className="px-4 py-2 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors shadow-sm"
              >
                + Create Budget
              </button>
            )}
          </div>
        </div>

        {error && (
          <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Skeleton className="h-28 rounded-2xl" />
            <Skeleton className="h-28 rounded-2xl" />
            <Skeleton className="h-28 rounded-2xl" />
            <Skeleton className="h-28 rounded-2xl" />
          </div>
        ) : budget ? (
          <>
            {/* Top KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <Card>
                <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                  {budget.total_budget_limit ? 'Total Budget Cap' : 'Total Allocated'}
                </div>
                <div className="text-2xl font-bold text-white mt-1">
                  {formatINR(budget.total_budget_limit || budget.total_allocated)}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Allocations sum: {formatINR(budget.total_allocated)}
                </div>
              </Card>

              <Card>
                <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Total Spent
                </div>
                <div className="text-2xl font-bold text-white mt-1">
                  {formatINR(budget.total_spent)}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  All verified expenses this month
                </div>
              </Card>

              <Card>
                <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Remaining Budget
                </div>
                <div className={`text-2xl font-bold mt-1 ${budget.total_remaining < 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                  {formatINR(budget.total_remaining)}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {budget.overall_is_exceeded ? 'Over limit' : 'Under limit'}
                </div>
              </Card>

              <Card>
                <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Overall Utilization
                </div>
                <div className="flex items-baseline gap-2 mt-1">
                  <span className={`text-2xl font-bold ${
                    budget.overall_is_exceeded
                      ? 'text-rose-400'
                      : budget.overall_utilization_pct >= Number(budget.warning_threshold)
                      ? 'text-amber-400'
                      : 'text-mint'
                  }`}>
                    {budget.overall_utilization_pct}%
                  </span>
                  <span className="text-xs text-gray-400">
                    alert threshold: {Number(budget.warning_threshold)}%
                  </span>
                </div>
                {/* Progress bar */}
                <div className="w-full bg-navy rounded-full h-2 mt-3 overflow-hidden">
                  <div
                    className={`h-2 rounded-full transition-all duration-500 ${
                      budget.overall_is_exceeded
                        ? 'bg-rose-500'
                        : budget.overall_utilization_pct >= Number(budget.warning_threshold)
                        ? 'bg-amber-400'
                        : 'bg-mint'
                    }`}
                    style={{ width: `${Math.min(100, Math.max(0, budget.overall_utilization_pct))}%` }}
                  />
                </div>
              </Card>
            </div>

            {/* Warnings list if any allocations exceeded or near limit */}
            {budget.allocations.some((a) => a.is_exceeded || a.is_warning) && (
              <div className="p-4 bg-navy-light border border-amber-500/30 rounded-2xl flex items-start gap-3">
                <span className="text-amber-400 text-lg">⚠️</span>
                <div>
                  <h4 className="text-sm font-semibold text-white">Budget Alerts</h4>
                  <div className="text-xs text-gray-300 mt-1 space-y-1">
                    {budget.allocations
                      .filter((a) => a.is_exceeded)
                      .map((a) => (
                        <div key={a.id} className="text-rose-400 font-medium">
                          • {a.category_name} has exceeded its limit ({a.utilization_pct}% spent - {formatINR(a.actual_spent)} / {formatINR(a.allocated_amount)})
                        </div>
                      ))}
                    {budget.allocations
                      .filter((a) => a.is_warning)
                      .map((a) => (
                        <div key={a.id} className="text-amber-300">
                          • {a.category_name} is nearing its limit ({a.utilization_pct}% spent - {formatINR(a.actual_spent)} / {formatINR(a.allocated_amount)})
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            )}

            {/* Category Allocations Grid */}
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white">Category Spending Allocations</h2>
              {budget.allocations.length === 0 ? (
                <Card>
                  <p className="text-sm text-gray-400 text-center py-6">
                    No category allocations set for this budget yet. Click "Edit Budget" to allocate spending.
                  </p>
                </Card>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {budget.allocations.map((alloc) => {
                    const pct = Math.min(100, Math.max(0, alloc.utilization_pct))
                    const statusColor = alloc.is_exceeded
                      ? 'text-rose-400 bg-rose-500/10 border-rose-500/30'
                      : alloc.is_warning
                      ? 'text-amber-400 bg-amber-500/10 border-amber-500/30'
                      : 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'

                    const barColor = alloc.is_exceeded
                      ? 'bg-rose-500'
                      : alloc.is_warning
                      ? 'bg-amber-400'
                      : 'bg-emerald-400'

                    return (
                      <Card key={alloc.id} className="relative flex flex-col justify-between">
                        <div>
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-semibold text-white text-base truncate">
                              {alloc.category_name}
                            </span>
                            <span className={`text-xs px-2.5 py-0.5 rounded-full border font-medium ${statusColor}`}>
                              {alloc.is_exceeded ? 'Exceeded' : alloc.is_warning ? 'Warning' : 'Healthy'}
                            </span>
                          </div>

                          {alloc.notes && (
                            <p className="text-xs text-gray-400 mt-1 line-clamp-1">{alloc.notes}</p>
                          )}

                          <div className="mt-4 flex items-baseline justify-between text-sm">
                            <span className="text-gray-400">Spent:</span>
                            <span className="font-semibold text-white">{formatINR(alloc.actual_spent)}</span>
                          </div>
                          <div className="flex items-baseline justify-between text-sm mt-1">
                            <span className="text-gray-400">Allocated:</span>
                            <span className="text-gray-300 font-medium">{formatINR(alloc.allocated_amount)}</span>
                          </div>
                          <div className="flex items-baseline justify-between text-sm mt-1">
                            <span className="text-gray-400">Remaining:</span>
                            <span className={`font-semibold ${alloc.remaining < 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                              {formatINR(alloc.remaining)}
                            </span>
                          </div>
                        </div>

                        <div className="mt-5">
                          <div className="flex justify-between text-xs text-gray-400 mb-1.5 font-medium">
                            <span>Utilization</span>
                            <span className={alloc.is_exceeded ? 'text-rose-400 font-bold' : ''}>
                              {alloc.utilization_pct}%
                            </span>
                          </div>
                          <div className="w-full bg-navy rounded-full h-2 overflow-hidden">
                            <div
                              className={`h-2 rounded-full transition-all duration-500 ${barColor}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      </Card>
                    )
                  })}
                </div>
              )}
            </div>
          </>
        ) : (
          <Card>
            <EmptyState
              title={`No Budget for ${MONTH_NAMES[selectedMonth - 1]} ${selectedYear}`}
              description="Setting a monthly budget helps you control spending, track limits by category, and stay on top of your financial health."
              action={
                <button
                  onClick={handleOpenModal}
                  className="px-5 py-2.5 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors shadow-sm"
                >
                  Create Budget for {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
                </button>
              }
            />
          </Card>
        )}

        {/* Create / Edit Budget Modal */}
        {editModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-navy-light border border-navy/60 rounded-2xl max-w-lg w-full p-6 shadow-2xl max-h-[90vh] flex flex-col">
              <div className="flex items-center justify-between pb-4 border-b border-navy/60">
                <h3 className="text-lg font-bold text-white">
                  {budget ? `Edit Budget (${MONTH_NAMES[selectedMonth - 1]} ${selectedYear})` : `New Budget (${MONTH_NAMES[selectedMonth - 1]} ${selectedYear})`}
                </h3>
                <button
                  onClick={() => setEditModalOpen(false)}
                  className="text-gray-400 hover:text-white"
                >
                  ✕
                </button>
              </div>

              <form onSubmit={handleSaveBudget} className="flex-1 overflow-y-auto py-4 space-y-4">
                {actionError && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-xs">
                    {actionError}
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                      Total Monthly Cap (₹)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="Optional total limit"
                      value={totalLimit}
                      onChange={(e) => setTotalLimit(e.target.value)}
                      className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-mint"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                      Alert Warning Threshold (%)
                    </label>
                    <input
                      type="number"
                      step="1"
                      min="1"
                      max="100"
                      value={warningThreshold}
                      onChange={(e) => setWarningThreshold(e.target.value)}
                      className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                    />
                  </div>
                </div>

                <div className="space-y-3 pt-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
                      Category Allocations
                    </label>
                    <button
                      type="button"
                      onClick={handleAddAllocationRow}
                      className="text-xs text-mint hover:underline font-semibold"
                    >
                      + Add Category
                    </button>
                  </div>

                  {allocations.map((alloc, idx) => (
                    <div key={idx} className="flex items-center gap-2 bg-navy/60 p-2.5 rounded-xl border border-navy/40">
                      <select
                        value={alloc.category_name}
                        onChange={(e) => handleAllocationChange(idx, 'category_name', e.target.value)}
                        className="bg-navy text-white text-xs rounded-lg px-2.5 py-2 border border-navy/60 focus:outline-none focus:border-mint flex-1"
                      >
                        {categories.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>

                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder="Amount"
                        value={alloc.allocated_amount}
                        onChange={(e) => handleAllocationChange(idx, 'allocated_amount', e.target.value)}
                        className="w-28 bg-navy text-white text-xs rounded-lg px-2.5 py-2 border border-navy/60 focus:outline-none focus:border-mint text-right"
                      />

                      <button
                        type="button"
                        onClick={() => handleRemoveAllocationRow(idx)}
                        className="p-1.5 text-gray-400 hover:text-rose-400 transition-colors"
                        title="Remove category"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>

                <div className="pt-4 flex justify-end gap-3 border-t border-navy/60">
                  <button
                    type="button"
                    onClick={() => setEditModalOpen(false)}
                    className="px-4 py-2 text-sm font-semibold text-gray-300 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="px-5 py-2 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors disabled:opacity-50"
                  >
                    {actionLoading ? 'Saving...' : 'Save Budget'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
        <ConfirmModal
          open={deleteModalOpen}
          title="Delete Budget"
          message={`Are you sure you want to delete the budget for ${MONTH_NAMES[selectedMonth - 1]} ${selectedYear}? This will delete all category allocations for this month.`}
          confirmLabel="Delete"
          danger={true}
          onConfirm={handleDeleteBudget}
          onCancel={() => setDeleteModalOpen(false)}
        />
      </div>
    </AppShell>
  )
}

