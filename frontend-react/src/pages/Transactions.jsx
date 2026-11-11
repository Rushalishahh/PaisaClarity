import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import AppShell from '../components/AppShell'
import { Card, Skeleton, ConfirmModal, EmptyState } from '../components/UI'
import { api, ApiError } from '../api'
import { formatINR } from '../utils/format'

export default function Transactions() {
  const [searchParams] = useSearchParams()
  const initialAccountId = searchParams.get('account_id') || ''

  // Data states
  const [transactions, setTransactions] = useState([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Lookups
  const [accounts, setAccounts] = useState([])
  const [categories, setCategories] = useState([])

  // Filters
  const [search, setSearch] = useState('')
  const [selectedAccount, setSelectedAccount] = useState(initialAccountId)
  const [selectedCategory, setSelectedCategory] = useState('')
  const [selectedType, setSelectedType] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [sortBy, setSortBy] = useState('date')
  const [sortOrder, setSortOrder] = useState('desc')

  // Modals
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [addTab, setAddTab] = useState('manual') // 'manual' or 'transfer'
  const [editTx, setEditTx] = useState(null)
  const [categoryCorrectionTx, setCategoryCorrectionTx] = useState(null)
  const [deleteTx, setDeleteTx] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState(null)

  // Manual Tx Form
  const [txDate, setTxDate] = useState(new Date().toISOString().slice(0, 10))
  const [txDesc, setTxDesc] = useState('')
  const [txMerchant, setTxMerchant] = useState('')
  const [txAmount, setTxAmount] = useState('')
  const [txType, setTxType] = useState('debit')
  const [txAccountId, setTxAccountId] = useState('')
  const [txCategoryId, setTxCategoryId] = useState('')

  // Transfer Form
  const [transferFromId, setTransferFromId] = useState('')
  const [transferToId, setTransferToId] = useState('')
  const [transferAmount, setTransferAmount] = useState('')
  const [transferDate, setTransferDate] = useState(new Date().toISOString().slice(0, 10))
  const [transferDesc, setTransferDesc] = useState('Account Transfer')

  // Quick Category Form
  const [newCategoryId, setNewCategoryId] = useState('')

  // Fetch Lookups (Accounts and Categories)
  useEffect(() => {
    async function loadLookups() {
      try {
        const [accs, cats] = await Promise.all([
          api('/accounts?include_archived=false&include_imported=true'),
          api('/categories'),
        ])
        setAccounts(accs || [])
        setCategories(cats || [])
        if (accs && accs.length > 0 && !txAccountId) {
          setTxAccountId(String(accs[0].id))
        }
        if (accs && accs.length >= 2) {
          setTransferFromId(String(accs[0].id))
          setTransferToId(String(accs[1].id))
        }
      } catch {
        // Non-fatal lookup error
      }
    }
    loadLookups()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Fetch Transactions
  const fetchTransactions = useCallback(async () => {
    try {
      setError(null)
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
        sort_by: sortBy,
        sort_order: sortOrder,
      })
      if (search.trim()) params.append('search', search.trim())
      if (selectedAccount) params.append('account_id', selectedAccount)
      if (selectedCategory) params.append('category', selectedCategory)
      if (selectedType) params.append('type', selectedType)
      if (startDate) params.append('start_date', startDate)
      if (endDate) params.append('end_date', endDate)

      const res = await api(`/transactions?${params.toString()}`)
      setTransactions(res.items || [])
      setTotal(res.total || 0)
      setPages(res.pages || 1)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load transactions')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, sortBy, sortOrder, search, selectedAccount, selectedCategory, selectedType, startDate, endDate])

  useEffect(() => {
    fetchTransactions()
  }, [fetchTransactions])

  // Reset pagination on filter change
  function handleFilterChange(setter, val) {
    setter(val)
    setPage(1)
  }

  // Open Add Modal
  function handleOpenAdd() {
    setTxDate(new Date().toISOString().slice(0, 10))
    setTxDesc('')
    setTxMerchant('')
    setTxAmount('')
    setTxType('debit')
    if (accounts.length > 0) setTxAccountId(String(accounts[0].id))
    setTxCategoryId('')
    setActionError(null)
    setAddModalOpen(true)
  }

  // Submit Manual Transaction
  async function handleCreateTx(e) {
    e.preventDefault()
    try {
      setActionLoading(true)
      setActionError(null)
      await api('/transactions', {
        method: 'POST',
        body: {
          date: txDate,
          description: txDesc.trim(),
          merchant: txMerchant.trim() || null,
          amount: txAmount,
          type: txType,
          account_id: txAccountId ? Number(txAccountId) : null,
          category_id: txCategoryId ? Number(txCategoryId) : null,
        },
      })
      setAddModalOpen(false)
      fetchTransactions()
    } catch (err) {
      setActionError(err.message || 'Failed to create transaction')
    } finally {
      setActionLoading(false)
    }
  }

  // Submit Transfer
  async function handleCreateTransfer(e) {
    e.preventDefault()
    try {
      setActionLoading(true)
      setActionError(null)
      await api('/transactions/transfer', {
        method: 'POST',
        body: {
          from_account_id: Number(transferFromId),
          to_account_id: Number(transferToId),
          date: transferDate,
          amount: transferAmount,
          description: transferDesc.trim() || 'Account Transfer',
        },
      })
      setAddModalOpen(false)
      fetchTransactions()
    } catch (err) {
      setActionError(err.message || 'Failed to execute transfer')
    } finally {
      setActionLoading(false)
    }
  }

  // Open Edit Modal
  function handleOpenEdit(tx) {
    setEditTx(tx)
    setTxDate(tx.date)
    setTxDesc(tx.description)
    setTxMerchant(tx.merchant || '')
    setTxAmount(String(tx.amount))
    setTxType(tx.type)
    setTxAccountId(tx.account_id ? String(tx.account_id) : '')
    setTxCategoryId(tx.category_id ? String(tx.category_id) : '')
    setActionError(null)
  }

  // Submit Edit
  async function handleEditTx(e) {
    e.preventDefault()
    if (!editTx) return
    try {
      setActionLoading(true)
      setActionError(null)
      await api(`/transactions/${editTx.id}`, {
        method: 'PUT',
        body: {
          date: txDate,
          description: txDesc.trim(),
          merchant: txMerchant.trim() || null,
          amount: txAmount,
          type: txType,
          account_id: txAccountId ? Number(txAccountId) : null,
          category_id: txCategoryId ? Number(txCategoryId) : null,
        },
      })
      setEditTx(null)
      fetchTransactions()
    } catch (err) {
      setActionError(err.message || 'Failed to update transaction')
    } finally {
      setActionLoading(false)
    }
  }

  // Open Category Correction
  function handleOpenCategoryCorrection(tx) {
    setCategoryCorrectionTx(tx)
    setNewCategoryId(tx.category_id ? String(tx.category_id) : '')
    setActionError(null)
  }

  // Submit Quick Category Correction
  async function handleCategoryCorrectionSubmit(e) {
    e.preventDefault()
    if (!categoryCorrectionTx) return
    try {
      setActionLoading(true)
      await api(`/transactions/${categoryCorrectionTx.id}/category`, {
        method: 'PATCH',
        body: {
          category_id: newCategoryId ? Number(newCategoryId) : null,
        },
      })
      setCategoryCorrectionTx(null)
      fetchTransactions()
    } catch (err) {
      setActionError(err.message || 'Failed to update category')
    } finally {
      setActionLoading(false)
    }
  }

  // Submit Delete
  async function handleDeleteConfirm() {
    if (!deleteTx) return
    try {
      setActionLoading(true)
      await api(`/transactions/${deleteTx.id}?delete_paired_transfer=true`, {
        method: 'DELETE',
      })
      setDeleteTx(null)
      fetchTransactions()
    } catch (err) {
      alert(err.message || 'Failed to delete transaction')
      setDeleteTx(null)
    } finally {
      setActionLoading(false)
    }
  }

  // Account lookup map: id -> name
  const accountMap = accounts.reduce((acc, a) => {
    acc[a.id] = a.name
    return acc
  }, {})

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Transactions</h1>
            <p className="text-gray-400 text-sm mt-1">
              Search, filter, categorize, and reconcile your normalized transactions.
            </p>
          </div>
          <button
            onClick={handleOpenAdd}
            className="bg-mint hover:bg-mint-dark text-navy font-semibold px-4 py-2 rounded-xl text-sm transition-colors flex items-center gap-2 self-start sm:self-auto shadow-sm"
          >
            <span>+ Add Transaction</span>
          </button>
        </div>

        {/* Filter Bar */}
        <Card className="p-4 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Search */}
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-gray-400 mb-1">
                Search
              </label>
              <input
                type="text"
                placeholder="Description or merchant..."
                value={search}
                onChange={(e) => handleFilterChange(setSearch, e.target.value)}
                className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-mint"
              />
            </div>

            {/* Account Filter */}
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-gray-400 mb-1">
                Account
              </label>
              <select
                value={selectedAccount}
                onChange={(e) => handleFilterChange(setSelectedAccount, e.target.value)}
                className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
              >
                <option value="">All Accounts</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Category Filter */}
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-gray-400 mb-1">
                Category
              </label>
              <select
                value={selectedCategory}
                onChange={(e) => handleFilterChange(setSelectedCategory, e.target.value)}
                className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
              >
                <option value="">All Categories</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Type Filter */}
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-gray-400 mb-1">
                Type
              </label>
              <select
                value={selectedType}
                onChange={(e) => handleFilterChange(setSelectedType, e.target.value)}
                className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
              >
                <option value="">All Types</option>
                <option value="debit">Debits (Spend)</option>
                <option value="credit">Credits (Income)</option>
              </select>
            </div>
          </div>

          {/* Date Range & Sorting */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t border-gray-800">
            <div>
              <label className="block text-[11px] text-gray-400 mb-1">From Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => handleFilterChange(setStartDate, e.target.value)}
                className="w-full bg-navy border border-gray-700 rounded-xl px-2 py-1 text-xs text-white focus:outline-none focus:border-mint"
              />
            </div>
            <div>
              <label className="block text-[11px] text-gray-400 mb-1">To Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => handleFilterChange(setEndDate, e.target.value)}
                className="w-full bg-navy border border-gray-700 rounded-xl px-2 py-1 text-xs text-white focus:outline-none focus:border-mint"
              />
            </div>
            <div>
              <label className="block text-[11px] text-gray-400 mb-1">Sort By</label>
              <select
                value={sortBy}
                onChange={(e) => handleFilterChange(setSortBy, e.target.value)}
                className="w-full bg-navy border border-gray-700 rounded-xl px-2 py-1 text-xs text-white focus:outline-none focus:border-mint"
              >
                <option value="date">Date</option>
                <option value="amount">Amount</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] text-gray-400 mb-1">Order</label>
              <select
                value={sortOrder}
                onChange={(e) => handleFilterChange(setSortOrder, e.target.value)}
                className="w-full bg-navy border border-gray-700 rounded-xl px-2 py-1 text-xs text-white focus:outline-none focus:border-mint"
              >
                <option value="desc">Descending</option>
                <option value="asc">Ascending</option>
              </select>
            </div>
          </div>
        </Card>

        {/* Transactions Table Area */}
        {loading ? (
          <Card className="p-6">
            <Skeleton className="h-6 w-1/4 mb-4" />
            <div className="space-y-3">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          </Card>
        ) : error ? (
          <div className="bg-coral/10 border border-coral/30 rounded-2xl p-6 text-center text-coral">
            <p>{error}</p>
            <button onClick={fetchTransactions} className="mt-3 text-sm underline font-semibold">
              Retry
            </button>
          </div>
        ) : transactions.length === 0 ? (
          <Card className="py-12">
            <EmptyState
              title="No Transactions Found"
              description="No transactions match your current filters. Try resetting filters or adding a new manual transaction."
              action={
                <button onClick={handleOpenAdd} className="bg-mint text-navy font-semibold px-4 py-2 rounded-xl text-sm">
                  Add Transaction
                </button>
              }
            />
          </Card>
        ) : (
          <Card className="overflow-hidden p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-navy/70 border-b border-gray-800 text-gray-400 uppercase tracking-wider text-[11px]">
                  <tr>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Description</th>
                    <th className="px-4 py-3">Account</th>
                    <th className="px-4 py-3">Category</th>
                    <th className="px-4 py-3 text-right">Amount</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800 text-gray-300">
                  {transactions.map((tx) => {
                    const isCredit = tx.type === 'credit'
                    const isTransfer = tx.classification === 'transfer'
                    const isOverlap = tx.import_metadata?.is_overlap === true
                    return (
                      <tr key={tx.id} className="hover:bg-navy/40 transition-colors">
                        <td className="px-4 py-3 whitespace-nowrap font-mono text-gray-400">
                          {tx.date}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-white truncate max-w-xs sm:max-w-md block">
                              {tx.description}
                            </span>
                            {isTransfer && (
                              <span className="bg-purple-500/20 text-purple-300 border border-purple-500/30 text-[10px] px-1.5 py-0.5 rounded">
                                Transfer
                              </span>
                            )}
                            {isOverlap && (
                              <span className="bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px] px-1.5 py-0.5 rounded">
                                Overlap Duplicate
                              </span>
                            )}
                          </div>
                          {tx.merchant && (
                            <p className="text-[11px] text-gray-500 capitalize">{tx.merchant}</p>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-gray-400">
                          {tx.account_id ? accountMap[tx.account_id] || 'Account' : '—'}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <button
                            onClick={() => handleOpenCategoryCorrection(tx)}
                            title="Click to change category"
                            className="bg-navy border border-gray-700 hover:border-mint text-gray-300 hover:text-white px-2 py-0.5 rounded-lg text-xs transition-colors flex items-center gap-1.5"
                          >
                            <span>{tx.category}</span>
                            <span className="text-[10px] text-gray-500">✎</span>
                          </button>
                        </td>
                        <td className={`px-4 py-3 whitespace-nowrap text-right font-semibold font-mono text-sm ${
                          isCredit ? 'text-mint' : 'text-white'
                        }`}>
                          {isCredit ? '+' : '−'}
                          {formatINR(tx.amount)}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right space-x-2">
                          <button
                            onClick={() => handleOpenEdit(tx)}
                            className="text-gray-400 hover:text-white transition-colors"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => setDeleteTx(tx)}
                            className="text-coral-light hover:text-coral transition-colors"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="bg-navy/70 border-t border-gray-800 px-4 py-3 flex items-center justify-between text-xs text-gray-400">
              <div>
                Showing <span className="font-semibold text-white">{transactions.length}</span> of{' '}
                <span className="font-semibold text-white">{total}</span> transactions
              </div>
              <div className="flex items-center gap-3">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-2.5 py-1 rounded-lg border border-gray-700 bg-navy hover:border-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <span>
                  Page <span className="font-semibold text-white">{page}</span> of{' '}
                  <span className="font-semibold text-white">{pages}</span>
                </span>
                <button
                  disabled={page >= pages}
                  onClick={() => setPage((p) => Math.min(pages, p + 1))}
                  className="px-2.5 py-1 rounded-lg border border-gray-700 bg-navy hover:border-gray-600 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* Add Transaction Modal */}
      {addModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="bg-navy-light border border-gray-700 rounded-2xl p-6 shadow-2xl w-full max-w-md">
            <h3 className="text-white font-semibold text-lg">Add Transaction</h3>

            {/* Tabs */}
            <div className="mt-3 flex rounded-xl bg-navy p-1 border border-gray-700 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setAddTab('manual')}
                className={`flex-1 py-1.5 rounded-lg transition-colors ${
                  addTab === 'manual' ? 'bg-mint text-navy' : 'text-gray-400 hover:text-white'
                }`}
              >
                Manual Transaction
              </button>
              <button
                type="button"
                onClick={() => setAddTab('transfer')}
                className={`flex-1 py-1.5 rounded-lg transition-colors ${
                  addTab === 'transfer' ? 'bg-mint text-navy' : 'text-gray-400 hover:text-white'
                }`}
              >
                Account Transfer
              </button>
            </div>

            {actionError && (
              <div className="bg-coral/10 border border-coral/30 rounded-xl p-3 text-coral text-xs mt-3">
                {actionError}
              </div>
            )}

            {addTab === 'manual' ? (
              <form onSubmit={handleCreateTx} className="mt-4 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">Date *</label>
                    <input
                      type="date"
                      required
                      value={txDate}
                      onChange={(e) => setTxDate(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">Type *</label>
                    <select
                      value={txType}
                      onChange={(e) => setTxType(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                    >
                      <option value="debit">Debit (Expense)</option>
                      <option value="credit">Credit (Income)</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Description *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Swiggy, Netflix, Salary"
                    value={txDesc}
                    onChange={(e) => setTxDesc(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">Amount (₹) *</label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      placeholder="0.00"
                      value={txAmount}
                      onChange={(e) => setTxAmount(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">Merchant</label>
                    <input
                      type="text"
                      placeholder="Optional"
                      value={txMerchant}
                      onChange={(e) => setTxMerchant(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">Account</label>
                    <select
                      value={txAccountId}
                      onChange={(e) => setTxAccountId(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                    >
                      <option value="">Unassigned</option>
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">Category</label>
                    <select
                      value={txCategoryId}
                      onChange={(e) => setTxCategoryId(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                    >
                      <option value="">Auto-categorize</option>
                      {categories.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex justify-end gap-3 pt-3 border-t border-gray-800">
                  <button
                    type="button"
                    onClick={() => setAddModalOpen(false)}
                    className="bg-navy border border-gray-700 text-gray-300 px-4 py-2 rounded-xl text-xs"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="bg-mint hover:bg-mint-dark text-navy font-semibold px-4 py-2 rounded-xl text-xs transition-colors"
                  >
                    {actionLoading ? 'Saving...' : 'Add Transaction'}
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleCreateTransfer} className="mt-4 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">From Account *</label>
                    <select
                      required
                      value={transferFromId}
                      onChange={(e) => setTransferFromId(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                    >
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">To Account *</label>
                    <select
                      required
                      value={transferToId}
                      onChange={(e) => setTransferToId(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                    >
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">Amount (₹) *</label>
                    <input
                      type="number"
                      step="0.01"
                      required
                      placeholder="0.00"
                      value={transferAmount}
                      onChange={(e) => setTransferAmount(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-300 mb-1">Date *</label>
                    <input
                      type="date"
                      required
                      value={transferDate}
                      onChange={(e) => setTransferDate(e.target.value)}
                      className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Note / Description</label>
                  <input
                    type="text"
                    placeholder="e.g. Credit Card payment"
                    value={transferDesc}
                    onChange={(e) => setTransferDesc(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                  />
                </div>

                <div className="flex justify-end gap-3 pt-3 border-t border-gray-800">
                  <button
                    type="button"
                    onClick={() => setAddModalOpen(false)}
                    className="bg-navy border border-gray-700 text-gray-300 px-4 py-2 rounded-xl text-xs"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="bg-mint hover:bg-mint-dark text-navy font-semibold px-4 py-2 rounded-xl text-xs transition-colors"
                  >
                    {actionLoading ? 'Transferring...' : 'Execute Transfer'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Edit Transaction Modal */}
      {editTx && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="bg-navy-light border border-gray-700 rounded-2xl p-6 shadow-2xl w-full max-w-md">
            <h3 className="text-white font-semibold text-lg">Edit Transaction</h3>

            {actionError && (
              <div className="bg-coral/10 border border-coral/30 rounded-xl p-3 text-coral text-xs mt-3">
                {actionError}
              </div>
            )}

            <form onSubmit={handleEditTx} className="mt-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Date *</label>
                  <input
                    type="date"
                    required
                    value={txDate}
                    onChange={(e) => setTxDate(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Type *</label>
                  <select
                    value={txType}
                    onChange={(e) => setTxType(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                  >
                    <option value="debit">Debit (Expense)</option>
                    <option value="credit">Credit (Income)</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-300 mb-1">Description *</label>
                <input
                  type="text"
                  required
                  value={txDesc}
                  onChange={(e) => setTxDesc(e.target.value)}
                  className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Amount (₹) *</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={txAmount}
                    onChange={(e) => setTxAmount(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Merchant</label>
                  <input
                    type="text"
                    value={txMerchant}
                    onChange={(e) => setTxMerchant(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Account</label>
                  <select
                    value={txAccountId}
                    onChange={(e) => setTxAccountId(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                  >
                    <option value="">Unassigned</option>
                    {accounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-300 mb-1">Category</label>
                  <select
                    value={txCategoryId}
                    onChange={(e) => setTxCategoryId(e.target.value)}
                    className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-mint"
                  >
                    <option value="">Keep current</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-3 border-t border-gray-800">
                <button
                  type="button"
                  onClick={() => setEditTx(null)}
                  className="bg-navy border border-gray-700 text-gray-300 px-4 py-2 rounded-xl text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="bg-mint hover:bg-mint-dark text-navy font-semibold px-4 py-2 rounded-xl text-xs transition-colors"
                >
                  {actionLoading ? 'Updating...' : 'Update Transaction'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Quick Category Correction Modal */}
      {categoryCorrectionTx && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="bg-navy-light border border-gray-700 rounded-2xl p-6 shadow-2xl w-full max-w-sm">
            <h3 className="text-white font-semibold text-base">Quick Category Correction</h3>
            <p className="text-gray-400 text-xs mt-1 truncate">
              {categoryCorrectionTx.description}
            </p>

            <form onSubmit={handleCategoryCorrectionSubmit} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-300 mb-1">Select Category</label>
                <select
                  required
                  value={newCategoryId}
                  onChange={(e) => setNewCategoryId(e.target.value)}
                  className="w-full bg-navy border border-gray-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-mint"
                >
                  <option value="">Choose Category</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.category_type})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex justify-end gap-3 pt-2 border-t border-gray-800">
                <button
                  type="button"
                  onClick={() => setCategoryCorrectionTx(null)}
                  className="bg-navy border border-gray-700 text-gray-300 px-3 py-1.5 rounded-xl text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="bg-mint hover:bg-mint-dark text-navy font-semibold px-3 py-1.5 rounded-xl text-xs transition-colors"
                >
                  {actionLoading ? 'Saving...' : 'Apply Category'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        open={Boolean(deleteTx)}
        title="Delete Transaction"
        message={
          deleteTx
            ? `Are you sure you want to delete '${deleteTx.description}' for ${formatINR(deleteTx.amount)}? ${
                deleteTx.transfer_group_id
                  ? 'This transaction is part of a paired transfer; both legs will be removed.'
                  : 'This action cannot be undone.'
              }`
            : ''
        }
        danger
        confirmLabel={actionLoading ? 'Deleting...' : 'Delete'}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTx(null)}
      />
    </AppShell>
  )
}
