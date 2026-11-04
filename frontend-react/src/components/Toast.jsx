import { useCallback, useMemo, useRef, useState } from 'react'
import { ToastContext } from './ToastContext'
import { AlertIcon, CheckIcon, XIcon } from './Icons'

/*
Minimal toast system - no external library, matching the app's existing
dark card aesthetic. Wrap the app (or a page) in <ToastProvider> and call
`const toast = useToast(); toast.success("Saved")` from anywhere below it
(useToast lives in ToastContext.jsx). Toasts auto-dismiss after 4 seconds
and stack in the bottom-right corner.
*/

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idCounter = useRef(0)

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (message, kind) => {
      const id = ++idCounter.current
      setToasts((prev) => [...prev, { id, message, kind }])
      setTimeout(() => dismiss(id), 4000)
    },
    [dismiss],
  )

  // Memoized so the object identity is stable - effects that list `toast`
  // in their dependency arrays won't re-run just because the provider
  // re-rendered to show a new toast.
  const toast = useMemo(
    () => ({
      success: (message) => push(message, 'success'),
      error: (message) => push(message, 'error'),
      info: (message) => push(message, 'info'),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={toast}>
      {children}
      {/* Fixed-position stack; pointer-events only on the toast itself so it
          never blocks clicks on the page behind it. */}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-[calc(100vw-2rem)] pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={`pointer-events-auto flex items-center gap-2.5 rounded-xl px-4 py-3 shadow-lg border text-sm transition-opacity ${
              t.kind === 'error'
                ? 'bg-navy-light border-coral/40 text-coral'
                : t.kind === 'info'
                  ? 'bg-navy-light border-gray-700 text-gray-200'
                  : 'bg-navy-light border-mint/40 text-mint'
            }`}
          >
            {t.kind === 'success' && <CheckIcon className="w-4 h-4 shrink-0" />}
            {t.kind === 'error' && <AlertIcon className="w-4 h-4 shrink-0" />}
            <span>{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              className="ml-2 text-gray-500 hover:text-white transition-colors"
              aria-label="Dismiss notification"
            >
              <XIcon className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

/* ---- inline icon components live in Icons.jsx ---- */
