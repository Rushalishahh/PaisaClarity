import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { Card, Skeleton, ConfirmModal, EmptyState } from '../components/UI'
import { api, ApiError } from '../api'
import { formatINR } from '../utils/format'

const ACCOUNT_TYPES = [
  { value: 'savings', label: 'Savings Account' },
  { value: 'checking', label: 'Checking Account' },
  { value: 'credit_card', label: 'Credit Card' },
  { value: 'wallet', label: 'Digital Wallet / Cash' },
  { value: 'investment', label: 'Investment Account' },
  { value: 'other', label: 'Other Account' },
]

export default function Accounts() {
  const navigate = useNavigate()
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showArchived, setShowArchived] = useState(false)

  // Modal states
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [editAccount, setEditAccount] = useState(null)
  const [reconcileAccount, setReconcileAccount] = useState(null)
  const [deleteAccountTarget, setDeleteAccountTarget] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState(null)

  // Form states
  const [name, setName] = useState('')
  const [accountType, setAccountType] = useState('savings')
  const [openingBalance, setOpeningBalance] = useState('0.00')
  const [maskedIdentifier, setMaskedIdentifier] = useState('')

  // Reconcile Form states
  const [reconcileMode, setReconcileMode] = useState('inplace') // 'inplace' or 'merge'
  const [reconName, setReconName] = useState('')
  const [reconType, setReconType] = useState('savings')
  const [reconMask, setReconMask] = useState('')
  const [mergeTargetId, setMergeTargetId] = useState('')

  const fetchAccounts = useCallback(async () => {
    try {
      const data = await api(`/accounts?include_archived=${showArchived}&include_imported=true`)
      setError(null)
      setAccounts(data || [])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load accounts')
    } finally {
      setLoading(false)
    }
  }, [showArchived])

  useEffect(() => {
    let ignore = false
    api(`/accounts?include_archived=${showArchived}&include_imported=true`)
      .then((data) => {
        if (!ignore) {
          setError(null)
          setAccounts(data || [])
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err instanceof ApiError ? err.message : 'Failed to load accounts')
          setLoading(false)
        }
      })
    return () => {
      ignore = true
    }
  }, [showArchived])

  // Summary Metrics
  const verifiedAccounts = accounts.filter((a) => a.is_reconciled && a.account_type !== 'imported' && !a.is_archived)
  const unreconciledAccounts = accounts.filter((a) => !a.is_reconciled || a.account_type === 'imported')
  const totalVerifiedNetWorth = verifiedAccounts.reduce((acc, a) => {
    const bal = a.calculated_balance !== null ? Number(a.calculated_balance) : 0
    return acc + bal
  }, 0)

  // Open Create Modal
  function handleOpenCreate() {
    setName('')
    setAccountType('savings')
    setOpeningBalance('0.00')
    setMaskedIdentifier('')
    setActionError(null)
    setCreateModalOpen(true)
  }

  // Submit Create
  async function handleCreate(e) {
    e.preventDefault()
    try {
      setActionLoading(true)
      setActionError(null)
      await api('/accounts', {
        method: 'POST',
        body: {
          name: name.trim(),
          account_type: accountType,
          opening_balance: openingBalance || '0.00',
          masked_identifier: maskedIdentifier.trim() || null,
        },
      })
      setCreateModalOpen(false)
      fetchAccounts()
    } catch (err) {
      setActionError(err.message || 'Failed to create account')
    } finally {
      setActionLoading(false)
    }
  }

  // Open Edit Modal
  function handleOpenEdit(acc) {
    setEditAccount(acc)
    setName(acc.name)
    setAccountType(acc.account_type === 'imported' ? 'savings' : acc.account_type)
    setOpeningBalance(acc.opening_balance || '0.00')
    setMaskedIdentifier(acc.masked_identifier || '')
    setActionError(null)
  }

  // Submit Edit
  async function handleEdit(e) {
    e.preventDefault()
    if (!editAccount) return
    try {
      setActionLoading(true)
      setActionError(null)
      await api(`/accounts/${editAccount.id}`, {
        method: 'PUT',
        body: {
          name: name.trim(),
          account_type: accountType,
          opening_balance: openingBalance,
          masked_identifier: maskedIdentifier.trim() || null,
        },
      })
      setEditAccount(null)
      fetchAccounts()
    } catch (err) {
      setActionError(err.message || 'Failed to update account')
    } finally {
      setActionLoading(false)
    }
  }

  // Open Reconcile Modal
  function handleOpenReconcile(acc) {
    setReconcileAccount(acc)
    setReconcileMode('inplace')
    setReconName(acc.name === 'Imported Statements' ? 'My Primary Bank' : acc.name)
    setReconType('savings')
    setReconMask(acc.masked_identifier || '')
    const otherAcc = verifiedAccounts.find((a) => a.id !== acc.id)
    setMergeTargetId(otherAcc ? String(otherAcc.id) : '')
    setActionError(null)
  }

  // Submit Reconcile
  async function handleReconcile(e) {
    e.preventDefault()
    if (!reconcileAccount) return
    try {
      setActionLoading(true)
      setActionError(null)
      const body =
        reconcileMode === 'merge'
          ? { merge_into_account_id: Number(mergeTargetId) }
          : {
              name: reconName.trim(),
              account_type: reconType,
              masked_identifier: reconMask.trim() || null,
            }

      await api(`/accounts/${reconcileAccount.id}/reconcile`, {
        method: 'POST',
        body,
      })
      setReconcileAccount(null)
      fetchAccounts()
    } catch (err) {
      setActionError(err.message || 'Failed to reconcile account')
    } finally {
      setActionLoading(false)
    }
  }

  // Archive / Unarchive
  async function handleToggleArchive(acc) {
    try {
      const endpoint = acc.is_archived ? `/accounts/${acc.id}/unarchive` : `/accounts/${acc.id}/archive`
      await api(endpoint, { method: 'POST' })
      fetchAccounts()
    } catch (err) {
      alert(err.message || 'Failed to change archive status')
    }
  }

  // Delete Account
  async function handleDeleteConfirm() {
    if (!deleteAccountTarget) return
    try {
      setActionLoading(true)
      await api(`/accounts/${deleteAccountTarget.id}`, { method: 'DELETE' })
      setDeleteAccountTarget(null)
      fetchAccounts()
    } catch (err) {
      alert(err.message || 'Failed to delete account')
      setDeleteAccountTarget(null)
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Financial Accounts</h1>
            <p className="text-gray-400 text-sm mt-1">
              Manage bank accounts, cards, and tracked balances with verified reconciliation.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
                className="rounded border-gray-700 bg-navy text-mint focus:ring-mint focus:ring-offset-navy"
              />
              <span>Show Archived</span>
            </label>
            <button
              onClick={handleOpenCreate}
              className="bg-mint hover:bg-mint-dark text-navy font-semibold px-4 py-2 rounded-xl text-sm transition-colors flex items-center gap-2 shadow-sm"
            >
              <span>+ Add Account</span>
            </button>
          </div>
        </div>

        {/* Unreconciled Warning Banner */}
        {unreconciledAccounts.length > 0 && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-amber-200">
            <div className="flex items-center gap-3">
              <span className="text-xl">⚠️</span>
              <div>
                <p className="font-semibold text-sm">
                  {unreconciledAccounts.length} Unreconciled Imported Account(s)
                </p>
                <p className="text-xs text-amber-300/80 mt-0.5">
                  Transactions imported from statements are stored safely, but excluded from verified net worth until reconciled.
                </p>
              </div>
            </div>
            <button
              onClick={() => handleOpenReconcile(unreconciledAccounts[0])}
              className="bg-amber-500 hover:bg-amber-400 text-navy font-semibold text-xs px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap"
            >
              Reconcile Now
            </button>
          </div>
        )}

        {/* Stats Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card className="p-5">
            <p className="text-gray-400 text-xs uppercase tracking-wider font-semibold">Total Verified Net Worth</p>
            <p className="text-2xl font-bold text-mint mt-2">{formatINR(totalVerifiedNetWorth)}</p>
            <p className="text-xs text-gray-400 mt-1">Calculated from verified accounts</p>
          </Card>
          <Card className="p-5">
            <p className="text-gray-400 text-xs uppercase tracking-wider font-semibold">Verified Accounts</p>
            <p className="text-2xl font-bold text-white mt-2">{verifiedAccounts.length}</p>
            <p className="text-xs text-gray-400 mt-1">Active bank and wallet accounts</p>
          </Card>
          <Card className="p-5">
            <p className="text-gray-400 text-xs uppercase tracking-wider font-semibold">Pending Reconciliation</p>
            <p className="text-2xl font-bold text-amber-400 mt-2">{unreconciledAccounts.length}</p>
            <p className="text-xs text-gray-400 mt-1">Imported placeholder accounts</p>
          </Card>
        </div>

        {/* Content Area */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <Skeleton className="h-44 w-full" />
            <Skeleton className="h-44 w-full" />
            <Skeleton className="h-44 w-full" />
          </div>
        ) : error ? (
          <div className="bg-coral/10 border border-coral/30 rounded-2xl p-6 text-center text-coral">
            <p>{error}</p>
            <button onClick={fetchAccounts} className="mt-3 text-sm underline font-semibold">
              Retry
            </button>
          </div>
        ) : accounts.length === 0 ? (
          <Card className="py-12">
            <EmptyState
              title="No Accounts Found"
              description="Add your bank accounts, credit cards, or digital wallets to start tracking balances and movements."
              action={
                <button
                  onClick={handleOpenCreate}
                  className="bg-mint text-navy font-semibold px-4 py-2 rounded-xl text-sm"
                >
                  Create Your First Account
                </button>
              }
            />
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {accounts.map((acc) => {
              const isVerified = acc.is_reconciled && acc.account_type !== 'imported'
              return (
                <div
                  key={acc.id}
                  className={`bg-navy-light border rounded-2xl p-5 flex flex-col justify-between transition-all ${
                    acc.is_archived
                      ? 'border-gray-800 opacity-60'
                      : isVerified
                      ? 'border-gray-700/60 hover:border-mint/40 shadow-lg'
                      : 'border-amber-500/40 bg-navy-light/90'
                  }`}
                >
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="text-white font-semibold text-base flex items-center gap-2">
                          {acc.name}
                          {acc.is_archived && (
                            <span className="text-[10px] uppercase font-bold bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">
                              Archived
                            </span>
                          )}
                        </h3>
                        <p className="text-gray-400 text-xs capitalize mt-0.5">
                          {acc.account_type.replace('_', ' ')}
                          {acc.masked_identifier ? ` •••• ${acc.masked_identifier}` : ''}
                        </p>
                      </div>

                      {/* Reconciliation Badge */}
                      {isVerified ? (
                        <span className="text-[10px] font-semibold bg-mint/15 text-mint border border-mint/30 px-2 py-0.5 rounded-full">
                          Verified
                        </span>
                      ) : (
                        <span className="text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded-full">
                          Unreconciled
                        </span>
                      )}
                    </div>

                    {/* Balance Display */}
                    <div className="mt-4 pt-3 border-t border-gray-800/80">
                      <p className="text-xs text-gray-400">Calculated Balance</p>
                      {isVerified ? (
                        <p className="text-xl font-bold text-white mt-0.5">
                          {formatINR(acc.calculated_balance)}
                        </p>
                      ) : (
                        <p className="text-sm font-semibold text-amber-300/80 mt-0.5">
                          Pending Reconciliation
                        </p>
                      )}
                      <p className="text-[11px] text-gray-400 mt-1">
                        {acc.transaction_count} transaction(s) tracked
                      </p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="mt-5 pt-3 border-t border-gray-800 flex items-center justify-between gap-2 text-xs">
                    <button
                      onClick={() => navigate(`/transactions?account_id=${acc.id}`)}
                      className="text-mint hover:underline font-semibold"
                    >
                      View Txns
                    </button>
                    <div className="flex items-center gap-2">
                      {!isVerified && (
                        <button
                          onClick={() => handleOpenReconcile(acc)}
                          className="text-amber-400 hover:text-amber-300 font-semibold"
                        >
                          Reconcile
                        </button>
                      )}
                      <button
                        onClick={() => handleOpenEdit(acc)}
                        className="text-gray-300 hover:text-white"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleToggleArchive(acc)}
                        className="text-gray-400 hover:text-gray-300"
                      >
                        {acc.is_archived ? 'Unarchive' : 'Archive'}
                      </button>
                      <button
                        onClick={() => setDeleteAccountTarget(acc)}
                        className="text-coral-light hover:text-coral"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Create Account Modal */}
      {createModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="bg-navy-light border border-gray-700 rounded-2xl p-6 shadow-2xl w-full max-w-md">
            <h3 className="text-white font-semibold text-lg">Add Financial Account</h3>
            <p className="text-gray-400 text-xs mt-1">
              Add a verified account to track balance movements and transactions.
            </p>

            {actionError && (
              <div className="bg-coral/10 border border-coral/30 rounded-xl p-3 text-coral text-xs mt-3">
                {actionError}
              </div>
            )}

            <form onSubmit={handleCreate} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-300 mb-1">Account Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. HDFC Salary, SBI Savings"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-300 mb-1">Account Type</label>
                <select
                  value={accountType}
                  onChange={(e) => setAccountType(e.target.value)}
                  className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                >
                  {ACCOUNT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Opening Balance (₹)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={openingBalance}
                    onChange={(e) => setOpeningBalance(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Mask (optional)</label>
                  <input
                    type="text"
                    maxLength={10}
                    placeholder="e.g. 1234"
                    value={maskedIdentifier}
                    onChange={(e) => setMaskedIdentifier(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-gray-800">
                <button
                  type="button"
                  onClick={() => setCreateModalOpen(false)}
                  className="bg-navy border border-gray-700 hover:border-gray-600 text-gray-300 px-4 py-2 rounded-xl text-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="bg-mint hover:bg-mint-dark text-navy font-semibold px-4 py-2 rounded-xl text-sm transition-colors"
                >
                  {actionLoading ? 'Saving...' : 'Create Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Account Modal */}
      {editAccount && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="bg-navy-light border border-gray-700 rounded-2xl p-6 shadow-2xl w-full max-w-md">
            <h3 className="text-white font-semibold text-lg">Edit Account</h3>
            <p className="text-gray-400 text-xs mt-1">Update account name, type, or identifier.</p>

            {actionError && (
              <div className="bg-coral/10 border border-coral/30 rounded-xl p-3 text-coral text-xs mt-3">
                {actionError}
              </div>
            )}

            <form onSubmit={handleEdit} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-300 mb-1">Account Name *</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-300 mb-1">Account Type</label>
                <select
                  value={accountType}
                  onChange={(e) => setAccountType(e.target.value)}
                  className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                >
                  {ACCOUNT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Opening Balance (₹)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={openingBalance}
                    onChange={(e) => setOpeningBalance(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Mask (optional)</label>
                  <input
                    type="text"
                    maxLength={10}
                    value={maskedIdentifier}
                    onChange={(e) => setMaskedIdentifier(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-gray-800">
                <button
                  type="button"
                  onClick={() => setEditAccount(null)}
                  className="bg-navy border border-gray-700 hover:border-gray-600 text-gray-300 px-4 py-2 rounded-xl text-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="bg-mint hover:bg-mint-dark text-navy font-semibold px-4 py-2 rounded-xl text-sm transition-colors"
                >
                  {actionLoading ? 'Saving...' : 'Update Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reconcile Modal */}
      {reconcileAccount && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="bg-navy-light border border-gray-700 rounded-2xl p-6 shadow-2xl w-full max-w-md">
            <h3 className="text-white font-semibold text-lg">Reconcile Imported Account</h3>
            <p className="text-gray-400 text-xs mt-1">
              Choose how to reconcile transactions from &quot;{reconcileAccount.name}&quot;.
            </p>

            {actionError && (
              <div className="bg-coral/10 border border-coral/30 rounded-xl p-3 text-coral text-xs mt-3">
                {actionError}
              </div>
            )}

            <div className="mt-4 flex rounded-xl bg-navy p-1 border border-gray-700 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setReconcileMode('inplace')}
                className={`flex-1 py-1.5 rounded-lg transition-colors ${
                  reconcileMode === 'inplace' ? 'bg-mint text-navy' : 'text-gray-400 hover:text-white'
                }`}
              >
                Verify In-Place
              </button>
              <button
                type="button"
                onClick={() => setReconcileMode('merge')}
                className={`flex-1 py-1.5 rounded-lg transition-colors ${
                  reconcileMode === 'merge' ? 'bg-mint text-navy' : 'text-gray-400 hover:text-white'
                }`}
              >
                Merge Into Verified Account
              </button>
            </div>

            <form onSubmit={handleReconcile} className="mt-4 space-y-4">
              {reconcileMode === 'inplace' ? (
                <>
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">
                      Real Bank Account Name *
                    </label>
                    <input
                      type="text"
                      required
                      value={reconName}
                      onChange={(e) => setReconName(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">Account Type</label>
                    <select
                      value={reconType}
                      onChange={(e) => setReconType(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                    >
                      {ACCOUNT_TYPES.filter((t) => t.value !== 'imported').map((t) => (
                        <option key={t.value} value={t.value}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">
                      Masked Identifier (e.g. 5678)
                    </label>
                    <input
                      type="text"
                      maxLength={10}
                      value={reconMask}
                      onChange={(e) => setReconMask(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                    />
                  </div>
                </>
              ) : (
                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">
                    Select Target Verified Account *
                  </label>
                  {verifiedAccounts.length === 0 ? (
                    <p className="text-xs text-amber-300">
                      No verified accounts available to merge into. Please use &quot;Verify In-Place&quot; instead.
                    </p>
                  ) : (
                    <select
                      value={mergeTargetId}
                      onChange={(e) => setMergeTargetId(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                    >
                      {verifiedAccounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name} ({a.account_type})
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-3 border-t border-gray-800">
                <button
                  type="button"
                  onClick={() => setReconcileAccount(null)}
                  className="bg-navy border border-gray-700 hover:border-gray-600 text-gray-300 px-4 py-2 rounded-xl text-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || (reconcileMode === 'merge' && !mergeTargetId)}
                  className="bg-mint hover:bg-mint-dark text-navy font-semibold px-4 py-2 rounded-xl text-sm transition-colors"
                >
                  {actionLoading ? 'Reconciling...' : 'Confirm Reconciliation'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        open={Boolean(deleteAccountTarget)}
        title="Delete Account"
        message={
          deleteAccountTarget
            ? `Are you sure you want to delete '${deleteAccountTarget.name}'? Only accounts with 0 transactions can be deleted. Accounts with financial history must be archived instead.`
            : ''
        }
        danger
        confirmLabel={actionLoading ? 'Deleting...' : 'Delete'}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteAccountTarget(null)}
      />
    </AppShell>
  )
}
