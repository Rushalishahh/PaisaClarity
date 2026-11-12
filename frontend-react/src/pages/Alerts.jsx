import { useState, useEffect, useCallback } from 'react'
import AppShell from '../components/AppShell'
import { Card, Skeleton, EmptyState } from '../components/UI'
import { api, ApiError } from '../api'

const SEVERITY_STYLES = {
  critical: {
    bg: 'bg-rose-500/10',
    border: 'border-rose-500/30',
    badge: 'bg-rose-500 text-white',
    icon: '🚨',
  },
  warning: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    badge: 'bg-amber-400 text-navy font-bold',
    icon: '⚠️',
  },
  info: {
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30',
    badge: 'bg-blue-500 text-white',
    icon: 'ℹ️',
  },
}

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [evaluating, setEvaluating] = useState(false)

  // Filter: 'active', 'unread', 'critical_warning', 'dismissed'
  const [filterTab, setFilterTab] = useState('active')

  // Preferences modal
  const [prefModalOpen, setPrefModalOpen] = useState(false)
  const [prefs, setPrefs] = useState({
    budget_alerts: true,
    recurring_alerts: true,
    unusual_spending_alerts: true,
    goal_alerts: true,
    large_expense_threshold: '5000.00',
  })
  const [prefLoading, setPrefLoading] = useState(false)
  const [prefMessage, setPrefMessage] = useState(null)

  const fetchAlerts = useCallback(async () => {
    try {
      setError(null)
      const isDismissed = filterTab === 'dismissed'
      const isRead = filterTab === 'unread' ? false : undefined
      const severity = filterTab === 'critical_warning' ? 'warning' : undefined

      let query = `?is_dismissed=${isDismissed}`
      if (isRead !== undefined) query += `&is_read=${isRead}`
      if (severity) query += `&severity=${severity}`

      const res = await api(`/alerts${query}`)
      setAlerts(res.items || [])
      setUnreadCount(res.unread_count || 0)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load alerts')
    } finally {
      setLoading(false)
    }
  }, [filterTab])

  useEffect(() => {
    fetchAlerts()
  }, [fetchAlerts])

  // Fetch preferences
  async function handleOpenPreferences() {
    try {
      setPrefMessage(null)
      const res = await api('/alerts/preferences')
      setPrefs({
        budget_alerts: res.budget_alerts,
        recurring_alerts: res.recurring_alerts,
        unusual_spending_alerts: res.unusual_spending_alerts,
        goal_alerts: res.goal_alerts,
        large_expense_threshold: String(res.large_expense_threshold),
      })
      setPrefModalOpen(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load preferences')
    }
  }

  // Save preferences
  async function handleSavePreferences(e) {
    e.preventDefault()
    try {
      setPrefLoading(true)
      const payload = {
        budget_alerts: prefs.budget_alerts,
        recurring_alerts: prefs.recurring_alerts,
        unusual_spending_alerts: prefs.unusual_spending_alerts,
        goal_alerts: prefs.goal_alerts,
        large_expense_threshold: Number(prefs.large_expense_threshold) || 5000,
      }
      await api('/alerts/preferences', {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      setPrefModalOpen(false)
      fetchAlerts()
    } catch (err) {
      setPrefMessage(err instanceof ApiError ? err.message : 'Failed to save preferences')
    } finally {
      setPrefLoading(false)
    }
  }

  // Evaluate alerts manually
  async function handleEvaluate() {
    try {
      setEvaluating(true)
      await api('/alerts/evaluate', { method: 'POST' })
      fetchAlerts()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to evaluate alerts')
    } finally {
      setEvaluating(false)
    }
  }

  // Mark single alert as read
  async function handleMarkRead(id) {
    try {
      await api(`/alerts/${id}/read`, { method: 'POST' })
      fetchAlerts()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to mark read')
    }
  }

  // Mark all as read
  async function handleMarkAllRead() {
    try {
      await api('/alerts/read-all', { method: 'POST' })
      fetchAlerts()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to mark all read')
    }
  }

  // Dismiss alert
  async function handleDismiss(id) {
    try {
      await api(`/alerts/${id}/dismiss`, { method: 'POST' })
      fetchAlerts()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to dismiss alert')
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-3">
              <span>Financial Alerts</span>
              {unreadCount > 0 && (
                <span className="bg-rose-500 text-white text-xs px-2.5 py-0.5 rounded-full font-bold">
                  {unreadCount} unread
                </span>
              )}
            </h1>
            <p className="text-sm text-gray-400 mt-1">
              Deterministic real-time warnings for budgets, bills, unusual spending, and goal deadlines.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleEvaluate}
              disabled={evaluating}
              className="px-3.5 py-2 bg-navy-light text-mint border border-mint/30 font-semibold text-xs rounded-xl hover:bg-mint/10 transition-colors disabled:opacity-50"
            >
              {evaluating ? 'Evaluating...' : '↻ Check Now'}
            </button>

            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="px-3.5 py-2 bg-navy-light text-gray-300 hover:text-white font-semibold text-xs rounded-xl hover:bg-navy transition-colors border border-navy/60"
              >
                ✓ Mark All Read
              </button>
            )}

            <button
              onClick={handleOpenPreferences}
              className="px-3.5 py-2 bg-mint text-navy font-semibold text-xs rounded-xl hover:bg-mint/90 transition-colors shadow-sm"
            >
              ⚙ Preferences
            </button>
          </div>
        </div>

        {error && (
          <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-sm">
            {error}
          </div>
        )}

        {/* Filter Tabs */}
        <div className="flex items-center gap-2 border-b border-navy/60 pb-2">
          <button
            onClick={() => setFilterTab('active')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
              filterTab === 'active' ? 'bg-mint text-navy' : 'text-gray-400 hover:text-white'
            }`}
          >
            Active Alerts
          </button>
          <button
            onClick={() => setFilterTab('unread')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 ${
              filterTab === 'unread' ? 'bg-rose-500 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            <span>Unread</span>
            {unreadCount > 0 && (
              <span className="bg-white/20 text-white text-[10px] px-1.5 py-0.2 rounded-full font-bold">
                {unreadCount}
              </span>
            )}
          </button>
          <button
            onClick={() => setFilterTab('dismissed')}
            className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
              filterTab === 'dismissed' ? 'bg-navy-light text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            Dismissed History
          </button>
        </div>

        {/* Alerts List */}
        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 rounded-2xl" />
            <Skeleton className="h-20 rounded-2xl" />
            <Skeleton className="h-20 rounded-2xl" />
          </div>
        ) : alerts.length === 0 ? (
          <Card>
            <EmptyState
              title={
                filterTab === 'unread'
                  ? 'All Caught Up!'
                  : filterTab === 'dismissed'
                  ? 'No Dismissed Alerts'
                  : 'No Active Alerts'
              }
              description="Your finances look healthy! No active budget breaches, overdue subscriptions, or unusual spending anomalies detected."
            />
          </Card>
        ) : (
          <div className="space-y-3">
            {alerts.map((a) => {
              const style = SEVERITY_STYLES[a.severity] || SEVERITY_STYLES.info
              const formattedDate = new Date(a.created_at).toLocaleString('en-IN', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              })

              return (
                <div
                  key={a.id}
                  className={`rounded-2xl p-4 border transition-all ${style.bg} ${style.border} ${
                    !a.is_read ? 'shadow-md ring-1 ring-mint/20' : 'opacity-85'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <span className="text-xl mt-0.5">{style.icon}</span>
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="font-semibold text-white text-sm">{a.title}</h4>
                          <span className={`text-[10px] uppercase px-2 py-0.2 rounded-full font-bold ${style.badge}`}>
                            {a.severity}
                          </span>
                          {!a.is_read && (
                            <span className="w-2 h-2 rounded-full bg-mint" title="Unread" />
                          )}
                        </div>
                        <p className="text-xs text-gray-300 mt-1 leading-relaxed">{a.message}</p>
                        <span className="text-[11px] text-gray-500 mt-2 block">{formattedDate}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      {!a.is_read && (
                        <button
                          onClick={() => handleMarkRead(a.id)}
                          className="px-2.5 py-1 text-xs text-mint hover:bg-mint/10 rounded-lg transition-colors font-medium"
                        >
                          Mark Read
                        </button>
                      )}
                      {!a.is_dismissed && (
                        <button
                          onClick={() => handleDismiss(a.id)}
                          className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-navy/60 transition-colors text-xs"
                          title="Dismiss"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Preferences Modal */}
        {prefModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-navy-light border border-navy/60 rounded-2xl max-w-md w-full p-6 shadow-2xl">
              <div className="flex items-center justify-between pb-3 border-b border-navy/60">
                <h3 className="text-lg font-bold text-white">Alert Preferences</h3>
                <button onClick={() => setPrefModalOpen(false)} className="text-gray-400 hover:text-white">✕</button>
              </div>

              <form onSubmit={handleSavePreferences} className="py-4 space-y-4">
                {prefMessage && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-xs">
                    {prefMessage}
                  </div>
                )}

                <div className="space-y-3">
                  <label className="flex items-center justify-between p-3 rounded-xl bg-navy/60 border border-navy/40 cursor-pointer">
                    <div>
                      <div className="text-sm font-semibold text-white">Budget Warnings & Caps</div>
                      <div className="text-xs text-gray-400">Alert when spending nears or exceeds limits</div>
                    </div>
                    <input
                      type="checkbox"
                      checked={prefs.budget_alerts}
                      onChange={(e) => setPrefs({ ...prefs, budget_alerts: e.target.checked })}
                      className="rounded bg-navy border-navy/60 text-mint focus:ring-0 w-4 h-4"
                    />
                  </label>

                  <label className="flex items-center justify-between p-3 rounded-xl bg-navy/60 border border-navy/40 cursor-pointer">
                    <div>
                      <div className="text-sm font-semibold text-white">Upcoming Recurring Bills</div>
                      <div className="text-xs text-gray-400">Remind 3 days before a recurring bill is due</div>
                    </div>
                    <input
                      type="checkbox"
                      checked={prefs.recurring_alerts}
                      onChange={(e) => setPrefs({ ...prefs, recurring_alerts: e.target.checked })}
                      className="rounded bg-navy border-navy/60 text-mint focus:ring-0 w-4 h-4"
                    />
                  </label>

                  <label className="flex items-center justify-between p-3 rounded-xl bg-navy/60 border border-navy/40 cursor-pointer">
                    <div>
                      <div className="text-sm font-semibold text-white">Savings Goal Pace Alerts</div>
                      <div className="text-xs text-gray-400">Alert when a goal is off-pace before target date</div>
                    </div>
                    <input
                      type="checkbox"
                      checked={prefs.goal_alerts}
                      onChange={(e) => setPrefs({ ...prefs, goal_alerts: e.target.checked })}
                      className="rounded bg-navy border-navy/60 text-mint focus:ring-0 w-4 h-4"
                    />
                  </label>

                  <label className="flex items-center justify-between p-3 rounded-xl bg-navy/60 border border-navy/40 cursor-pointer">
                    <div>
                      <div className="text-sm font-semibold text-white">Large Unusual Spending</div>
                      <div className="text-xs text-gray-400">Alert on single transactions over threshold</div>
                    </div>
                    <input
                      type="checkbox"
                      checked={prefs.unusual_spending_alerts}
                      onChange={(e) => setPrefs({ ...prefs, unusual_spending_alerts: e.target.checked })}
                      className="rounded bg-navy border-navy/60 text-mint focus:ring-0 w-4 h-4"
                    />
                  </label>

                  {prefs.unusual_spending_alerts && (
                    <div className="pt-2">
                      <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1">
                        Large Expense Alert Threshold (₹)
                      </label>
                      <input
                        type="number"
                        step="100"
                        min="500"
                        value={prefs.large_expense_threshold}
                        onChange={(e) => setPrefs({ ...prefs, large_expense_threshold: e.target.value })}
                        className="w-full bg-navy border border-navy/60 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-mint"
                      />
                    </div>
                  )}
                </div>

                <div className="pt-4 flex justify-end gap-3 border-t border-navy/60">
                  <button
                    type="button"
                    onClick={() => setPrefModalOpen(false)}
                    className="px-4 py-2 text-sm font-semibold text-gray-300 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={prefLoading}
                    className="px-5 py-2 bg-mint text-navy font-semibold text-sm rounded-xl hover:bg-mint/90 transition-colors disabled:opacity-50"
                  >
                    {prefLoading ? 'Saving...' : 'Save Preferences'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  )
}

