import { useState, useEffect, useCallback } from 'react'
import AppShell from '../components/AppShell'
import { Card, Skeleton, ConfirmModal, EmptyState } from '../components/UI'
import { api, ApiError } from '../api'
import { formatINR } from '../utils/format'

const CATEGORIES = [
  'Bills', 'Entertainment', 'Utilities', 'Food', 'Shopping',
  'Health', 'Education', 'Transport', 'Insurance', 'Other'
]

const FREQUENCIES = [
  { value: 'monthly', label: 'Monthly' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'yearly', label: 'Yearly' },
]

export default function RecurringPayments() {
  const [data, setData] = useState({
    total_monthly_commitment: '0.00',
    active_count: 0,
    detected_count: 0,
    upcoming_payments: [],
    items: [],
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [scanning, setScanning] = useState(false)
  const [scanMessage, setScanMessage] = useState(null)

  // Filter tab: 'active', 'detected', 'all'
  const [filterTab, setFilterTab] = useState('active')

  // Modals
  const [modalOpen, setModalOpen] = useState(false)
  const [editingPayment, setEditingPayment] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState(null)

  // Form states
  const [name, setName] = useState('')
  const [category, setCategory] = useState('Bills')
  const [amount, setAmount] = useState('')
  const [frequency, setFrequency] = useState('monthly')
  const [nextExpectedDate, setNextExpectedDate] = useState('')
  const [notes, setNotes] = useState('')

  const fetchRecurring = useCallback(async () => {
    try {
      setError(null)
      const res = await api('/recurring?include_inactive=true')
      setData(res || {
        total_monthly_commitment: '0.00',
        active_count: 0,
        detected_count: 0,
        upcoming_payments: [],
        items: [],
      })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load recurring payments')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let ignore = false
    api('/recurring?include_inactive=true')
      .then((res) => {
        if (!ignore) {
          setError(null)
          setData(res || {
            total_monthly_commitment: '0.00',
            active_count: 0,
            detected_count: 0,
            upcoming_payments: [],
            items: [],
          })
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err instanceof ApiError ? err.message : 'Failed to load recurring payments')
          setLoading(false)
        }
      })

    return () => {
      ignore = true
    }
  }, [])

  // Trigger scan
  async function handleScan() {
    try {
      setScanning(true)
      setScanMessage(null)
      const res = await api('/recurring/scan', { method: 'POST' })
      setScanMessage(
        `Scan complete: ${res.new_detected} new subscriptions detected, ${res.updated} updated.`
      )
      fetchRecurring()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Scan failed')
    } finally {
      setScanning(false)
    }
  }

  // Open Create Modal
  function handleOpenCreate() {
    setEditingPayment(null)
    setName('')
    setCategory('Bills')
    setAmount('')
    setFrequency('monthly')
    setNextExpectedDate('')
    setNotes('')
    setActionError(null)
    setModalOpen(true)
  }

  // Open Edit Modal
  function handleOpenEdit(item) {
    setEditingPayment(item)
    setName(item.name)
    setCategory(item.category || 'Bills')
    setAmount(String(item.average_amount))
    setFrequency(item.frequency || 'monthly')
    setNextExpectedDate(item.next_expected_date || '')
    setNotes(item.notes || '')
    setActionError(null)
    setModalOpen(true)
  }

  // Save (Create or Update)
  async function handleSave(e) {
    e.preventDefault()
    try {
      setActionLoading(true)
      setActionError(null)

      const payload = {
        name: name.trim(),
        category,
        average_amount: Number(amount),
        frequency,
        next_expected_date: nextExpectedDate || null,
        notes: notes.trim() || null,
      }

      if (editingPayment) {
        await api(`/recurring/${editingPayment.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      } else {
        await api('/recurring', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
      }

      setModalOpen(false)
      fetchRecurring()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Failed to save recurring payment')
    } finally {
      setActionLoading(false)
    }
  }

  // Status transitions
  async function handleConfirm(id) {
    try {
      await api(`/recurring/${id}/confirm`, { method: 'POST' })
      fetchRecurring()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to confirm subscription')
    }
  }

  async function handleReject(id) {
    try {
      await api(`/recurring/${id}/reject`, { method: 'POST' })
      fetchRecurring()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to reject subscription')
    }
  }

  async function handleTogglePause(item) {
    try {
      const endpoint = item.status === 'inactive' ? `/recurring/${item.id}/resume` : `/recurring/${item.id}/pause`
      await api(endpoint, { method: 'POST' })
      fetchRecurring()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update status')
    }
  }

  // Delete
  async function handleDelete() {
    if (!deleteTarget) return
    try {
      setActionLoading(true)
      await api(`/recurring/${deleteTarget.id}`, { method: 'DELETE' })
      setDeleteTarget(null)
      fetchRecurring()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete payment')
    } finally {
      setActionLoading(false)
    }
  }

  // Filter items
  const displayedItems = (data.items || []).filter((item) => {
    if (filterTab === 'active') return item.status === 'confirmed'
    if (filterTab === 'detected') return item.status === 'detected'
    return true
  })

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Recurring Payments & Subscriptions</h1>
            <p className="text-sm text-gray-400 mt-1">
              Track subscriptions, monitor estimated monthly commitments, and foresee upcoming bills.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleScan}
              disabled={scanning}
              className="px-4 py-2 bg-navy-light text-mint border border-mint/30 font-semibold text-sm rounded-xl hover:bg-mint/10 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {scanning ? (
                <>
                  <span className="w-4 h-4 border-2 border-mint border-t-transparent rounded-full animate-spin" />
                  <span>Scanning...</span>
                </>
              ) : (
                <>
                  <span>⚡ Scan History</span>
                </>
              )}
            </button>

            <button
              onClick={handleOpenCreate}
              className="px-4 py-2 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors shadow-sm"
            >
              + Add Recurring
            </button>
          </div>
        </div>

        {scanMessage && (
          <div className="p-3 bg-mint/10 border border-mint/30 rounded-xl text-mint text-xs flex items-center justify-between">
            <span>{scanMessage}</span>
            <button onClick={() => setScanMessage(null)} className="text-gray-400 hover:text-white">✕</button>
          </div>
        )}

        {error && (
          <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-sm">
            {error}
          </div>
        )}

        {/* Summary KPIs */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">Monthly Commitment</div>
            <div className="text-2xl font-bold text-mint mt-1">{formatINR(data.total_monthly_commitment)}</div>
            <div className="text-xs text-gray-500 mt-1">Across all confirmed subscriptions</div>
          </Card>

          <Card>
            <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">Active Subscriptions</div>
            <div className="text-2xl font-bold text-white mt-1">{data.active_count}</div>
            <div className="text-xs text-gray-500 mt-1">Confirmed recurring payments</div>
          </Card>

          <Card>
            <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">Pending Review</div>
            <div className="text-2xl font-bold text-amber-400 mt-1">{data.detected_count}</div>
            <div className="text-xs text-gray-500 mt-1">Auto-detected candidates to verify</div>
          </Card>

          <Card>
            <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">Bills in Next 30 Days</div>
            <div className="text-2xl font-bold text-white mt-1">{(data.upcoming_payments || []).length}</div>
            <div className="text-xs text-gray-500 mt-1">Due within the upcoming month</div>
          </Card>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-2 border-b border-navy/60 pb-2">
          <button
            onClick={() => setFilterTab('active')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
              filterTab === 'active' ? 'bg-mint text-navy' : 'text-gray-400 hover:text-white'
            }`}
          >
            Active ({data.active_count})
          </button>
          <button
            onClick={() => setFilterTab('detected')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 ${
              filterTab === 'detected' ? 'bg-amber-400 text-navy' : 'text-gray-400 hover:text-white'
            }`}
          >
            <span>Detected Candidates</span>
            {data.detected_count > 0 && (
              <span className="bg-amber-500/20 text-amber-300 text-[10px] px-1.5 py-0.2 rounded-full font-bold">
                {data.detected_count}
              </span>
            )}
          </button>
          <button
            onClick={() => setFilterTab('all')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
              filterTab === 'all' ? 'bg-navy-light text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            All ({(data.items || []).length})
          </button>
        </div>

        {/* List of Recurring Payments */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <Skeleton className="h-44 rounded-2xl" />
            <Skeleton className="h-44 rounded-2xl" />
            <Skeleton className="h-44 rounded-2xl" />
          </div>
        ) : displayedItems.length === 0 ? (
          <Card>
            <EmptyState
              title={
                filterTab === 'detected'
                  ? 'No Detected Subscriptions'
                  : 'No Recurring Payments Added'
              }
              description={
                filterTab === 'detected'
                  ? 'Click "Scan History" above to scan previous statement transactions for repeated charges like Netflix, Spotify, or gym dues.'
                  : 'Add your recurring bills and subscriptions or scan statement history to track monthly commitments.'
              }
              action={
                <button
                  onClick={handleScan}
                  className="px-5 py-2.5 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors shadow-sm"
                >
                  Scan Statement History
                </button>
              }
            />
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {displayedItems.map((item) => {
              const isDetected = item.status === 'detected'
              const isInactive = item.status === 'inactive'

              return (
                <Card key={item.id} className={`flex flex-col justify-between ${isInactive ? 'opacity-60' : ''}`}>
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="font-semibold text-white text-base truncate">{item.name}</h3>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-mint/80 bg-mint/10 px-2 py-0.5 rounded-full font-medium">
                            {item.category}
                          </span>
                          <span className="text-xs text-gray-400 capitalize">
                            • {item.frequency}
                          </span>
                        </div>
                      </div>

                      <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border ${
                        item.status === 'confirmed'
                          ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
                          : item.status === 'detected'
                          ? 'text-amber-400 bg-amber-500/10 border-amber-500/30'
                          : 'text-gray-400 bg-gray-500/10 border-gray-500/30'
                      }`}>
                        {item.status.toUpperCase()}
                      </span>
                    </div>

                    {item.notes && (
                      <p className="text-xs text-gray-400 mt-2 line-clamp-1">{item.notes}</p>
                    )}

                    <div className="mt-4 flex items-baseline justify-between">
                      <span className="text-xs text-gray-400">Amount:</span>
                      <span className="text-xl font-bold text-white">{formatINR(item.average_amount)}</span>
                    </div>

                    {item.next_expected_date && (
                      <div className="mt-2 text-xs text-gray-400 flex items-center justify-between">
                        <span>Next Due:</span>
                        <span className="font-medium text-gray-200">{item.next_expected_date}</span>
                      </div>
                    )}

                    {item.occurrence_count > 1 && (
                      <div className="mt-1 text-[11px] text-gray-500">
                        Observed {item.occurrence_count} times in transactions
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="mt-5 pt-3 border-t border-navy/60 flex items-center justify-between gap-2">
                    {isDetected ? (
                      <div className="flex items-center gap-2 w-full">
                        <button
                          onClick={() => handleConfirm(item.id)}
                          className="flex-1 py-1.5 bg-emerald-500 text-white font-semibold text-xs rounded-lg hover:bg-emerald-600 transition-colors shadow-sm"
                        >
                          ✓ Confirm
                        </button>
                        <button
                          onClick={() => handleReject(item.id)}
                          className="px-3 py-1.5 bg-navy text-gray-400 hover:text-rose-400 font-semibold text-xs rounded-lg transition-colors border border-navy/60"
                        >
                          Dismiss
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          onClick={() => handleTogglePause(item)}
                          className="text-xs text-gray-400 hover:text-white px-2 py-1 rounded bg-navy/60 border border-navy/60"
                        >
                          {isInactive ? 'Resume' : 'Pause'}
                        </button>

                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleOpenEdit(item)}
                            className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-navy transition-colors text-xs"
                            title="Edit"
                          >
                            ✎
                          </button>
                          <button
                            onClick={() => setDeleteTarget(item)}
                            className="p-1.5 text-rose-400 hover:text-white rounded-lg hover:bg-rose-500/20 transition-colors text-xs"
                            title="Delete"
                          >
                            ✕
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                </Card>
              )
            })}
          </div>
        )}

        {/* Create / Edit Modal */}
        {modalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-navy-light border border-navy/60 rounded-2xl max-w-md w-full p-6 shadow-2xl">
              <div className="flex items-center justify-between pb-3 border-b border-navy/60">
                <h3 className="text-lg font-bold text-white">
                  {editingPayment ? 'Edit Recurring Payment' : 'New Recurring Payment'}
                </h3>
                <button onClick={() => setModalOpen(false)} className="text-gray-400 hover:text-white">
                  ✕
                </button>
              </div>

              <form onSubmit={handleSave} className="py-4 space-y-4">
                {actionError && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-xs">
                    {actionError}
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                    Name *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Netflix, Wifi Bill, Gym"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                      Amount (₹) *
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="1"
                      required
                      placeholder="e.g. 649"
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                      className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                      Frequency
                    </label>
                    <select
                      value={frequency}
                      onChange={(e) => setFrequency(e.target.value)}
                      className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                    >
                      {FREQUENCIES.map((f) => (
                        <option key={f.value} value={f.value}>{f.label}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                      Category
                    </label>
                    <select
                      value={category}
                      onChange={(e) => setCategory(e.target.value)}
                      className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                    >
                      {CATEGORIES.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                      Next Due Date
                    </label>
                    <input
                      type="date"
                      value={nextExpectedDate}
                      onChange={(e) => setNextExpectedDate(e.target.value)}
                      className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                    Notes
                  </label>
                  <input
                    type="text"
                    placeholder="Optional notes"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  />
                </div>

                <div className="pt-3 flex justify-end gap-3 border-t border-navy/60">
                  <button
                    type="button"
                    onClick={() => setModalOpen(false)}
                    className="px-4 py-2 text-sm font-semibold text-gray-300 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="px-5 py-2 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors disabled:opacity-50"
                  >
                    {actionLoading ? 'Saving...' : 'Save Payment'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Delete Confirm Modal */}
        <ConfirmModal
          open={!!deleteTarget}
          title="Delete Recurring Payment"
          message={`Are you sure you want to remove "${deleteTarget?.name}"?`}
          confirmLabel="Delete"
          danger={true}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      </div>
    </AppShell>
  )
}

