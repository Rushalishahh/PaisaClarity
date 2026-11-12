import { useState, useEffect, useCallback } from 'react'
import AppShell from '../components/AppShell'
import { Card, Skeleton, ConfirmModal, EmptyState } from '../components/UI'
import { api, ApiError } from '../api'
import { formatINR } from '../utils/format'

const GOAL_CATEGORIES = [
  'Emergency Fund', 'Travel', 'Vehicle', 'Gadget', 'Real Estate',
  'Wedding', 'Education', 'Retirement', 'Investment', 'Other'
]

export default function SavingsGoals() {
  const [goals, setGoals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [includeArchived, setIncludeArchived] = useState(false)

  // Modals
  const [goalModalOpen, setGoalModalOpen] = useState(false)
  const [editingGoal, setEditingGoal] = useState(null)
  const [contribModalOpen, setContribModalOpen] = useState(false)
  const [activeGoalForContrib, setActiveGoalForContrib] = useState(null)
  const [historyModalOpen, setHistoryModalOpen] = useState(false)
  const [activeGoalForHistory, setActiveGoalForHistory] = useState(null)
  const [deleteGoalTarget, setDeleteGoalTarget] = useState(null)

  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState(null)

  // Goal Form State
  const [name, setName] = useState('')
  const [targetAmount, setTargetAmount] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [category, setCategory] = useState('Emergency Fund')
  const [notes, setNotes] = useState('')

  // Contribution Form State
  const [contribAmount, setContribAmount] = useState('')
  const [contribDate, setContribDate] = useState(new Date().toISOString().split('T')[0])
  const [contribType, setContribType] = useState('deposit')
  const [contribNotes, setContribNotes] = useState('')

  const fetchGoals = useCallback(async () => {
    try {
      setError(null)
      const data = await api(`/goals?include_archived=${includeArchived}`)
      setGoals(data || [])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load savings goals')
    } finally {
      setLoading(false)
    }
  }, [includeArchived])

  useEffect(() => {
    let ignore = false
    api(`/goals?include_archived=${includeArchived}`)
      .then((data) => {
        if (!ignore) {
          setError(null)
          setGoals(data || [])
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err instanceof ApiError ? err.message : 'Failed to load savings goals')
          setLoading(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [includeArchived])

  // Summary Metrics
  const activeGoals = goals.filter((g) => !g.is_archived)
  const totalSaved = activeGoals.reduce((sum, g) => sum + Number(g.total_saved || 0), 0)
  const totalTarget = activeGoals.reduce((sum, g) => sum + Number(g.target_amount || 0), 0)
  const overallProgress = totalTarget > 0 ? Math.min(100, Math.round((totalSaved / totalTarget) * 100)) : 0

  // Open Create Modal
  function handleOpenCreateGoal() {
    setEditingGoal(null)
    setName('')
    setTargetAmount('')
    setTargetDate('')
    setCategory('Emergency Fund')
    setNotes('')
    setActionError(null)
    setGoalModalOpen(true)
  }

  // Open Edit Modal
  function handleOpenEditGoal(g) {
    setEditingGoal(g)
    setName(g.name)
    setTargetAmount(String(g.target_amount))
    setTargetDate(g.target_date || '')
    setCategory(g.category || 'Other')
    setNotes(g.notes || '')
    setActionError(null)
    setGoalModalOpen(true)
  }

  // Submit Create or Edit Goal
  async function handleSaveGoal(e) {
    e.preventDefault()
    try {
      setActionLoading(true)
      setActionError(null)

      const payload = {
        name: name.trim(),
        target_amount: Number(targetAmount),
        target_date: targetDate || null,
        category: category || null,
        notes: notes.trim() || null,
      }

      if (editingGoal) {
        await api(`/goals/${editingGoal.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      } else {
        await api('/goals', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
      }

      setGoalModalOpen(false)
      fetchGoals()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Failed to save goal')
    } finally {
      setActionLoading(false)
    }
  }

  // Open Add Contribution Modal
  function handleOpenContrib(g) {
    setActiveGoalForContrib(g)
    setContribAmount('')
    setContribDate(new Date().toISOString().split('T')[0])
    setContribType('deposit')
    setContribNotes('')
    setActionError(null)
    setContribModalOpen(true)
  }

  // Submit Contribution
  async function handleSaveContrib(e) {
    e.preventDefault()
    if (!activeGoalForContrib) return
    try {
      setActionLoading(true)
      setActionError(null)

      const amt = Number(contribAmount)
      if (contribType === 'withdrawal' && amt > Number(activeGoalForContrib.total_saved)) {
        setActionError(`Withdrawal (₹${amt}) cannot exceed current saved balance of ₹${activeGoalForContrib.total_saved}`)
        setActionLoading(false)
        return
      }

      await api(`/goals/${activeGoalForContrib.id}/contributions`, {
        method: 'POST',
        body: JSON.stringify({
          amount: amt,
          contribution_date: contribDate,
          contribution_type: contribType,
          notes: contribNotes.trim() || null,
        }),
      })

      setContribModalOpen(false)
      fetchGoals()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Failed to record contribution')
    } finally {
      setActionLoading(false)
    }
  }

  // Open History Ledger Modal
  async function handleOpenHistory(g) {
    try {
      const full = await api(`/goals/${g.id}`)
      setActiveGoalForHistory(full)
      setHistoryModalOpen(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load contribution history')
    }
  }

  // Delete Contribution from History Ledger
  async function handleDeleteContrib(contribId) {
    if (!activeGoalForHistory) return
    try {
      await api(`/goals/${activeGoalForHistory.id}/contributions/${contribId}`, { method: 'DELETE' })
      const updated = await api(`/goals/${activeGoalForHistory.id}`)
      setActiveGoalForHistory(updated)
      fetchGoals()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Failed to delete contribution')
    }
  }

  // Toggle Archive
  async function handleToggleArchive(g) {
    try {
      const endpoint = g.is_archived ? `/goals/${g.id}/unarchive` : `/goals/${g.id}/archive`
      await api(endpoint, { method: 'POST' })
      fetchGoals()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to change archive status')
    }
  }

  // Delete Goal
  async function handleDeleteGoal() {
    if (!deleteGoalTarget) return
    try {
      setActionLoading(true)
      await api(`/goals/${deleteGoalTarget.id}`, { method: 'DELETE' })
      setDeleteGoalTarget(null)
      fetchGoals()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete goal')
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Savings Goals</h1>
            <p className="text-sm text-gray-400 mt-1">
              Set dedicated savings targets, track deposit/withdrawal history, and reach your milestones.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer bg-navy-light px-3 py-2 rounded-xl border border-navy/60 hover:text-white">
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(e) => setIncludeArchived(e.target.checked)}
                className="rounded bg-navy border-navy/60 text-mint focus:ring-0"
              />
              <span>Show Archived</span>
            </label>

            <button
              onClick={handleOpenCreateGoal}
              className="px-4 py-2 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors shadow-sm whitespace-nowrap"
            >
              + New Goal
            </button>
          </div>
        </div>

        {error && (
          <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-sm">
            {error}
          </div>
        )}

        {/* Top KPI Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">Active Goals</div>
            <div className="text-2xl font-bold text-white mt-1">{activeGoals.length}</div>
            <div className="text-xs text-gray-500 mt-1">
              {goals.filter((g) => g.is_completed && !g.is_archived).length} reached 100%
            </div>
          </Card>

          <Card>
            <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">Total Saved</div>
            <div className="text-2xl font-bold text-mint mt-1">{formatINR(totalSaved)}</div>
            <div className="text-xs text-gray-500 mt-1">Net accumulated ledger balance</div>
          </Card>

          <Card>
            <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">Total Target</div>
            <div className="text-2xl font-bold text-white mt-1">{formatINR(totalTarget)}</div>
            <div className="text-xs text-gray-500 mt-1">Combined target for active goals</div>
          </Card>

          <Card>
            <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">Overall Progress</div>
            <div className="text-2xl font-bold text-white mt-1">{overallProgress}%</div>
            <div className="w-full bg-navy rounded-full h-2 mt-3 overflow-hidden">
              <div
                className="h-2 rounded-full bg-mint transition-all duration-500"
                style={{ width: `${overallProgress}%` }}
              />
            </div>
          </Card>
        </div>

        {/* Goals List */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <Skeleton className="h-56 rounded-2xl" />
            <Skeleton className="h-56 rounded-2xl" />
            <Skeleton className="h-56 rounded-2xl" />
          </div>
        ) : goals.length === 0 ? (
          <Card>
            <EmptyState
              title="No Savings Goals Set Yet"
              description="Create a savings goal for an emergency fund, vacation, or major purchase to stay motivated and track your deposits."
              action={
                <button
                  onClick={handleOpenCreateGoal}
                  className="px-5 py-2.5 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors shadow-sm"
                >
                  Create Your First Goal
                </button>
              }
            />
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {goals.map((g) => {
              const isDone = g.is_completed || g.completion_pct >= 100
              const progressPct = Math.min(100, Math.max(0, g.completion_pct))

              return (
                <Card key={g.id} className={`flex flex-col justify-between ${g.is_archived ? 'opacity-60' : ''}`}>
                  <div>
                    {/* Header: Title and Badge */}
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-white text-base">{g.name}</h3>
                          {g.is_archived && (
                            <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-gray-500/20 text-gray-400">
                              Archived
                            </span>
                          )}
                        </div>
                        {g.category && (
                          <span className="inline-block mt-1 text-xs text-mint/80 font-medium bg-mint/10 px-2 py-0.5 rounded-full">
                            {g.category}
                          </span>
                        )}
                      </div>

                      {isDone && (
                        <span className="text-xs font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-0.5 rounded-full">
                          ✓ Achieved
                        </span>
                      )}
                    </div>

                    {g.notes && (
                      <p className="text-xs text-gray-400 mt-2 line-clamp-2">{g.notes}</p>
                    )}

                    {/* Progress Bar & Amounts */}
                    <div className="mt-5 space-y-2">
                      <div className="flex justify-between items-baseline text-sm">
                        <span className="text-gray-400 text-xs">Saved</span>
                        <span className="font-bold text-mint text-lg">{formatINR(g.total_saved)}</span>
                      </div>

                      <div className="w-full bg-navy rounded-full h-2.5 overflow-hidden">
                        <div
                          className={`h-2.5 rounded-full transition-all duration-500 ${isDone ? 'bg-emerald-400' : 'bg-mint'}`}
                          style={{ width: `${progressPct}%` }}
                        />
                      </div>

                      <div className="flex justify-between text-xs text-gray-400">
                        <span>Target: {formatINR(g.target_amount)}</span>
                        <span className="font-semibold text-white">{g.completion_pct}%</span>
                      </div>
                    </div>

                    {/* Monthly Need Advice */}
                    {g.monthly_savings_needed && !isDone && !g.is_archived && (
                      <div className="mt-3 p-2 bg-navy/80 rounded-xl border border-navy/60 text-xs text-gray-300 flex items-center justify-between">
                        <span className="text-gray-400">Estimated monthly pace:</span>
                        <span className="font-semibold text-mint">{formatINR(g.monthly_savings_needed)} / mo</span>
                      </div>
                    )}

                    {g.target_date && (
                      <div className="mt-2 text-[11px] text-gray-500 flex items-center gap-1">
                        <span>Deadline:</span>
                        <span className="text-gray-300 font-medium">{g.target_date}</span>
                      </div>
                    )}
                  </div>

                  {/* Actions Footer */}
                  <div className="mt-5 pt-3 border-t border-navy/60 flex items-center justify-between gap-2">
                    <button
                      onClick={() => handleOpenContrib(g)}
                      className="px-3 py-1.5 bg-mint/10 text-mint hover:bg-mint hover:text-navy font-semibold text-xs rounded-lg transition-colors"
                    >
                      + Contribute
                    </button>

                    <button
                      onClick={() => handleOpenHistory(g)}
                      className="px-2.5 py-1.5 text-xs text-gray-300 hover:text-white hover:bg-navy rounded-lg transition-colors"
                    >
                      History
                    </button>

                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleOpenEditGoal(g)}
                        className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-navy transition-colors"
                        title="Edit Goal"
                      >
                        ✎
                      </button>
                      <button
                        onClick={() => handleToggleArchive(g)}
                        className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-navy transition-colors text-xs"
                        title={g.is_archived ? 'Restore Goal' : 'Archive Goal'}
                      >
                        {g.is_archived ? 'Restore' : 'Archive'}
                      </button>
                      <button
                        onClick={() => setDeleteGoalTarget(g)}
                        className="p-1.5 text-rose-400 hover:text-white rounded-lg hover:bg-rose-500/20 transition-colors"
                        title="Delete Goal"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                </Card>
              )
            })}
          </div>
        )}

        {/* Create / Edit Goal Modal */}
        {goalModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-navy-light border border-navy/60 rounded-2xl max-w-md w-full p-6 shadow-2xl">
              <div className="flex items-center justify-between pb-3 border-b border-navy/60">
                <h3 className="text-lg font-bold text-white">
                  {editingGoal ? 'Edit Savings Goal' : 'New Savings Goal'}
                </h3>
                <button onClick={() => setGoalModalOpen(false)} className="text-gray-400 hover:text-white">
                  ✕
                </button>
              </div>

              <form onSubmit={handleSaveGoal} className="py-4 space-y-4">
                {actionError && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-xs">
                    {actionError}
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                    Goal Name *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Emergency Fund, Japan Trip"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                      Target Amount (₹) *
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="1"
                      required
                      placeholder="e.g. 100000"
                      value={targetAmount}
                      onChange={(e) => setTargetAmount(e.target.value)}
                      className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                      Target Date
                    </label>
                    <input
                      type="date"
                      value={targetDate}
                      onChange={(e) => setTargetDate(e.target.value)}
                      className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                    Category
                  </label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  >
                    {GOAL_CATEGORIES.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                    Notes
                  </label>
                  <textarea
                    rows={2}
                    placeholder="Optional notes or details"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  />
                </div>

                <div className="pt-3 flex justify-end gap-3 border-t border-navy/60">
                  <button
                    type="button"
                    onClick={() => setGoalModalOpen(false)}
                    className="px-4 py-2 text-sm font-semibold text-gray-300 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="px-5 py-2 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors disabled:opacity-50"
                  >
                    {actionLoading ? 'Saving...' : 'Save Goal'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Add Contribution Modal */}
        {contribModalOpen && activeGoalForContrib && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-navy-light border border-navy/60 rounded-2xl max-w-sm w-full p-6 shadow-2xl">
              <div className="flex items-center justify-between pb-3 border-b border-navy/60">
                <div>
                  <h3 className="text-base font-bold text-white">Record Contribution</h3>
                  <p className="text-xs text-gray-400">{activeGoalForContrib.name}</p>
                </div>
                <button onClick={() => setContribModalOpen(false)} className="text-gray-400 hover:text-white">
                  ✕
                </button>
              </div>

              <form onSubmit={handleSaveContrib} className="py-4 space-y-4">
                {actionError && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-xs">
                    {actionError}
                  </div>
                )}

                <div className="flex rounded-xl bg-navy p-1 border border-navy/60">
                  <button
                    type="button"
                    onClick={() => setContribType('deposit')}
                    className={`flex-1 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                      contribType === 'deposit' ? 'bg-mint text-navy shadow-sm' : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    + Deposit
                  </button>
                  <button
                    type="button"
                    onClick={() => setContribType('withdrawal')}
                    className={`flex-1 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                      contribType === 'withdrawal' ? 'bg-rose-500 text-white shadow-sm' : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    − Withdrawal
                  </button>
                </div>

                {contribType === 'withdrawal' && (
                  <div className="text-xs text-amber-300 bg-amber-500/10 p-2.5 rounded-xl border border-amber-500/20">
                    Current balance: {formatINR(activeGoalForContrib.total_saved)}. Withdrawals cannot exceed this amount.
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                    Amount (₹) *
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    required
                    placeholder="Amount in ₹"
                    value={contribAmount}
                    onChange={(e) => setContribAmount(e.target.value)}
                    className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                    Date *
                  </label>
                  <input
                    type="date"
                    required
                    value={contribDate}
                    onChange={(e) => setContribDate(e.target.value)}
                    className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                    Notes
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Monthly salary savings"
                    value={contribNotes}
                    onChange={(e) => setContribNotes(e.target.value)}
                    className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  />
                </div>

                <div className="pt-3 flex justify-end gap-3 border-t border-navy/60">
                  <button
                    type="button"
                    onClick={() => setContribModalOpen(false)}
                    className="px-4 py-2 text-sm font-semibold text-gray-300 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="px-5 py-2 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors disabled:opacity-50"
                  >
                    {actionLoading ? 'Saving...' : 'Add Contribution'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Contribution History Ledger Modal */}
        {historyModalOpen && activeGoalForHistory && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-navy-light border border-navy/60 rounded-2xl max-w-lg w-full p-6 shadow-2xl max-h-[85vh] flex flex-col">
              <div className="flex items-center justify-between pb-3 border-b border-navy/60">
                <div>
                  <h3 className="text-base font-bold text-white">Contribution Ledger</h3>
                  <p className="text-xs text-gray-400">{activeGoalForHistory.name} — Balance: {formatINR(activeGoalForHistory.total_saved)}</p>
                </div>
                <button onClick={() => setHistoryModalOpen(false)} className="text-gray-400 hover:text-white">
                  ✕
                </button>
              </div>

              <div className="flex-1 overflow-y-auto py-3">
                {activeGoalForHistory.contributions.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-8">
                    No contributions recorded for this goal yet.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {activeGoalForHistory.contributions.map((c) => (
                      <div
                        key={c.id}
                        className="flex items-center justify-between p-3 rounded-xl bg-navy/60 border border-navy/40"
                      >
                        <div className="flex items-center gap-3">
                          <span className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold ${
                            c.contribution_type === 'withdrawal'
                              ? 'bg-rose-500/20 text-rose-400'
                              : 'bg-emerald-500/20 text-emerald-400'
                          }`}>
                            {c.contribution_type === 'withdrawal' ? '−' : '+'}
                          </span>
                          <div>
                            <div className="text-sm font-semibold text-white">
                              {c.contribution_type === 'withdrawal' ? '−' : '+'}{formatINR(c.amount)}
                            </div>
                            <div className="text-[11px] text-gray-400">
                              {c.contribution_date} {c.notes ? `• ${c.notes}` : ''}
                            </div>
                          </div>
                        </div>

                        <button
                          onClick={() => handleDeleteContrib(c.id)}
                          className="p-1 text-gray-400 hover:text-rose-400 transition-colors text-xs"
                          title="Delete entry"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="pt-3 border-t border-navy/60 flex justify-end">
                <button
                  onClick={() => setHistoryModalOpen(false)}
                  className="px-4 py-2 text-sm font-semibold text-gray-300 hover:text-white"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Delete Goal Modal */}
        <ConfirmModal
          open={!!deleteGoalTarget}
          title="Delete Savings Goal"
          message={`Are you sure you want to delete "${deleteGoalTarget?.name}"? All recorded contributions and history for this goal will be permanently removed.`}
          confirmLabel="Delete Goal"
          danger={true}
          onConfirm={handleDeleteGoal}
          onCancel={() => setDeleteGoalTarget(null)}
        />
      </div>
    </AppShell>
  )
}

