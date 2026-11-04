import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { APP_NAME } from '../config'

/*
The one shared shell for every logged-in page: persistent sidebar on
desktop, slide-down menu on mobile. Pages render their content as children
and no longer build their own headers.

Routes are (path, label, icon) triples; the active route is highlighted via
useLocation. The logged-in user's name/email comes from GET /auth/me.
*/

// One place to build nav-item class names for desktop + mobile menus, so
// active/hover styling can't drift between the two.
function navLinkClass(active) {
  return `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors ${
    active ? 'bg-navy-light text-mint font-semibold' : 'text-gray-400 hover:text-white hover:bg-navy-light/60'
  }`
}

function DashboardIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" className={className} aria-hidden="true">
      <rect x="3" y="3" width="6" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="11" y="3" width="6" height="5" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="3" y="13" width="6" height="4" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="11" y="10" width="6" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}

function InvestmentsIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" className={className} aria-hidden="true">
      <path d="M3 15l4.5-5 3.5 3 6-7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M13 6h4v4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function HistoryIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" className={className} aria-hidden="true">
      <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 6.5V10l2.5 2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', Icon: DashboardIcon },
  { to: '/investments', label: 'Investments', Icon: InvestmentsIcon },
  { to: '/history', label: 'History', Icon: HistoryIcon },
]

/* Brand wordmark - inline SVG, mint on navy, reused in the shell and landing. */
export function Wordmark({ compact = false }) {
  return (
    <span className="flex items-center gap-2.5">
      <svg viewBox="0 0 24 24" className="w-7 h-7 shrink-0" aria-hidden="true">
        <rect x="1" y="1" width="22" height="22" rx="6" fill="#1a2133" stroke="#7de3d1" strokeWidth="1.5" />
        <path d="M6 16.5V7.5h4.2a3 3 0 0 1 0 6H8.5v3" stroke="#7de3d1" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        <circle cx="15.5" cy="15.5" r="1.4" fill="#f5a3c7" />
      </svg>
      {!compact && <span className="text-white font-semibold text-lg tracking-tight">{APP_NAME}</span>}
    </span>
  )
}

export default function AppShell({ children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [user, setUser] = useState(null)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function fetchUser() {
      try {
        // api() attaches the token. A 401 (expired/bad token) redirects to
        // /login inside api(); any other failure just leaves the skeleton,
        // since the shell still works without a name.
        const data = await api('/auth/me')
        if (!cancelled) setUser(data)
      } catch {
        // Non-fatal: the shell still works without a name; each page's own
        // fetch handles real auth failures.
      }
    }
    fetchUser()
    return () => {
      cancelled = true
    }
  }, [])

  function handleLogout() {
    localStorage.removeItem('token')
    navigate('/login')
  }

  const displayName = user?.full_name?.trim() || user?.email || ''
  const initial = displayName ? displayName[0].toUpperCase() : null

  return (
    <div className="min-h-screen bg-navy flex flex-col md:flex-row">
      {/* ---- Desktop sidebar ---- */}
      <aside className="hidden md:flex flex-col w-60 shrink-0 border-r border-gray-800/70 px-4 py-6 sticky top-0 h-screen">
        <div className="px-2 mb-8">
          <Wordmark />
        </div>

        <nav className="flex flex-col gap-1" aria-label="Main navigation">
          {NAV_ITEMS.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setMenuOpen(false)}
              className={navLinkClass(location.pathname === to)}
            >
              <Icon className="w-5 h-5 shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* User block pinned to the bottom of the sidebar */}
        <div className="mt-auto pt-6 border-t border-gray-800/70">
          {user ? (
            <div className="flex items-center gap-3 px-2 py-1">
              <span className="w-9 h-9 shrink-0 rounded-full bg-mint/15 text-mint flex items-center justify-center text-sm font-semibold">
                {initial || '·'}
              </span>
              <div className="min-w-0">
                <p className="text-sm text-white font-medium truncate">{displayName}</p>
                <p className="text-xs text-gray-500 truncate">{user.email}</p>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3 px-2 py-1">
              <span className="w-9 h-9 shrink-0 rounded-full bg-navy-light" />
              <div className="space-y-1.5">
                <div className="h-3 w-24 bg-navy-light rounded animate-pulse" />
                <div className="h-2.5 w-32 bg-navy-light rounded animate-pulse" />
              </div>
            </div>
          )}
          <button
            onClick={handleLogout}
            className="mt-3 w-full text-left text-gray-400 hover:text-white text-sm rounded-xl px-3 py-2 hover:bg-navy-light/60 transition-colors"
          >
            Log out
          </button>
        </div>
      </aside>

      {/* ---- Mobile top bar ---- */}
      <header className="md:hidden sticky top-0 z-40 bg-navy/95 backdrop-blur border-b border-gray-800/70">
        <div className="flex items-center justify-between px-4 py-3">
          <Wordmark compact />
          <button
            onClick={() => setMenuOpen((o) => !o)}
            className="text-gray-300 hover:text-white p-2 -mr-2 transition-colors"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
          >
            {menuOpen ? (
              <svg viewBox="0 0 20 20" fill="none" className="w-6 h-6" aria-hidden="true">
                <path d="M4 4l12 12M16 4L4 16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            ) : (
              <svg viewBox="0 0 20 20" fill="none" className="w-6 h-6" aria-hidden="true">
                <path d="M3 5.5h14M3 10h14M3 14.5h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            )}
          </button>
        </div>

        {menuOpen && (
          <nav className="px-4 pb-4 flex flex-col gap-1 border-t border-gray-800/70 pt-3" aria-label="Mobile navigation">
            {NAV_ITEMS.map(({ to, label, Icon }) => (
              <NavLink
                key={to}
                to={to}
                onClick={() => setMenuOpen(false)}
                className={navLinkClass(location.pathname === to)}
              >
                <Icon className="w-5 h-5 shrink-0" />
                {label}
              </NavLink>
            ))}

            <div className="mt-2 pt-3 border-t border-gray-800/70">
              {user && (
                <div className="flex items-center gap-3 px-3 py-1.5">
                  <span className="w-8 h-8 shrink-0 rounded-full bg-mint/15 text-mint flex items-center justify-center text-sm font-semibold">
                    {initial || '·'}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm text-white font-medium truncate">{displayName}</p>
                    <p className="text-xs text-gray-500 truncate">{user.email}</p>
                  </div>
                </div>
              )}
              <button
                onClick={handleLogout}
                className="w-full text-left text-gray-300 hover:text-white text-sm rounded-xl px-3 py-2.5 hover:bg-navy-light/60 transition-colors"
              >
                Log out
              </button>
            </div>
          </nav>
        )}
      </header>

      {/* ---- Page content ---- */}
      <main className="flex-1 min-w-0 px-4 py-8 md:px-8">{children}</main>
    </div>
  )
}
